"""
chiba-store — Chiba's vault, on a Modal Volume, behind a small HTTP filesystem.

Chiba reads and writes the vault from ~100 call sites. Vercel has no persistent
filesystem, so those calls have to reach somewhere. lib/fsx.ts is the seam on
the client side; this is the other end of it.

    GET    /f?path=…     read a file          -> bytes
    PUT    /f?path=…     write a file         (body = bytes)
    DELETE /f?path=…     delete a file
    GET    /ls?path=…    list a folder        -> [{name, dir}]
    GET    /stat?path=…  exists/size/mtime    -> {exists, size, mtime_ms, dir}
    POST   /mv           rename               {"from": …, "to": …}

DELIBERATELY DUMB. No business logic lives here. Chiba's rules — the Grammar
Garden being read-only, sentences/ and memory/ write-blocked to the generic
tools, deletes going to .trash/ rather than unlink — all stay in lib/vault.ts
where they are already tested. Duplicating them here would give two places to
disagree about what is allowed, and the one further from the tests would win by
accident.

Deploy:  modal deploy deploy_store.py
"""

import modal

app = modal.App("chiba-store")

# The vault working copy. A Volume rather than the container filesystem: it
# survives container recycling, which is what makes uncommitted writes safe
# between git pushes.
vault = modal.Volume.from_name("chiba-vault", create_if_missing=True)
VAULT = "/vault"

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]", "uvicorn"
)


@app.function(
    image=image,
    volumes={VAULT: vault},
    timeout=300,
    min_containers=0,
    # Chiba does many small reads per turn, so a cold start per call would be
    # unusable. Ten minutes keeps a conversation on one warm container.
    scaledown_window=600,
    secrets=[modal.Secret.from_name("chiba-store-key")],
)
@modal.asgi_app()
def serve():
    import os
    from pathlib import Path

    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware

    api = FastAPI(title="chiba-store", version="1.0.0")
    API_KEY = os.environ.get("CHIBA_STORE_KEY")
    ROOT = Path(VAULT).resolve()

    class Auth(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.url.path in ("/health", "/"):
                return await call_next(request)
            if request.headers.get("X-API-Key") != API_KEY:
                return JSONResponse(
                    {"error": "Unauthorized"},
                    status_code=401,
                )
            return await call_next(request)

    api.add_middleware(Auth)

    def resolve(rel: str) -> Path:
        """Resolve a client path inside the vault, or refuse.

        THE security boundary. Every path arrives from a caller that is trusted
        for nothing — resolve fully, then confirm the result is still under the
        root, which catches `..`, absolute paths and symlink escapes alike.
        Same reasoning as resolveInVault() in lib/vault.ts, at the network edge.
        """
        if not rel:
            raise HTTPException(400, "path required")
        p = (ROOT / rel.lstrip("/")).resolve()
        if p != ROOT and ROOT not in p.parents:
            raise HTTPException(403, "path escapes the vault")
        return p

    # --- reads -------------------------------------------------------------
    # reload() picks up commits made by other containers. Without it a warm
    # container would serve its own stale snapshot indefinitely.
    @api.get("/f")
    async def read_file(path: str):
        vault.reload()
        p = resolve(path)
        if not p.is_file():
            raise HTTPException(404, "not found")
        return Response(p.read_bytes(), media_type="application/octet-stream")

    @api.get("/ls")
    async def list_dir(path: str = ""):
        vault.reload()
        p = resolve(path)
        if not p.is_dir():
            raise HTTPException(404, "not a directory")
        return {"entries": sorted(
            ({"name": c.name, "dir": c.is_dir()} for c in p.iterdir()),
            key=lambda e: e["name"],
        )}

    @api.get("/stat")
    async def stat(path: str):
        vault.reload()
        p = resolve(path)
        if not p.exists():
            # Not a 404: "does this exist" is a legitimate question with a
            # legitimate negative answer, and fsx.access() needs to ask it
            # without treating the answer as an error.
            return {"exists": False}
        st = p.stat()
        return {
            "exists": True,
            "size": st.st_size,
            "mtime_ms": int(st.st_mtime * 1000),
            "dir": p.is_dir(),
        }

    # --- writes ------------------------------------------------------------
    # commit() after every mutation. Modal Volume writes are container-local
    # until committed, so skipping it means another container — or the next cold
    # start — silently never sees the write.
    @api.put("/f")
    async def write_file(path: str, request: Request):
        p = resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(await request.body())
        vault.commit()
        return {"ok": True, "bytes": p.stat().st_size}

    @api.delete("/f")
    async def delete(path: str):
        p = resolve(path)
        if not p.exists():
            return {"ok": True, "existed": False}
        if p.is_dir():
            import shutil

            shutil.rmtree(p)
        else:
            p.unlink()
        vault.commit()
        return {"ok": True, "existed": True}

    @api.post("/mkdir")
    async def mkdir(path: str):
        p = resolve(path)
        p.mkdir(parents=True, exist_ok=True)
        vault.commit()
        return {"ok": True}

    @api.post("/mv")
    async def move(body: dict):
        src = resolve(body.get("from", ""))
        dst = resolve(body.get("to", ""))
        if not src.exists():
            raise HTTPException(404, "source not found")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        vault.commit()
        return {"ok": True}

    # --- meta --------------------------------------------------------------
    @api.get("/health")
    async def health():
        vault.reload()
        top = sorted(c.name for c in ROOT.iterdir()) if ROOT.exists() else []
        return {"status": "healthy", "service": "chiba-store", "top_level": top}

    @api.get("/")
    async def root():
        return {
            "service": "chiba-store",
            "usage": "GET/PUT/DELETE /f?path= · GET /ls · GET /stat · POST /mv · POST /mkdir",
            "auth": "X-API-Key required",
        }

    return api
