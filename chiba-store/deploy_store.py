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
    secrets=[
        modal.Secret.from_name("chiba-store-key"),
        modal.Secret.from_name("chiba-github-token"),
    ],
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

    # ── The fast read layer ────────────────────────────────────────────────
    #
    # A Modal Volume is a NETWORK filesystem: ~120 ms per small file. Chiba
    # touches LanguageCompanion constantly (memory, skills, the ladder), and one
    # chat turn against the Volume measured 115 s.
    #
    # So do not fetch the FILES — fetch the REPO. GitHub serves the whole of
    # jp-companion as one tarball in 2.9 s; extracted to the container's own
    # disk, every read after that is ~0 ms. And the repo is already the truth,
    # so this removes a copy rather than adding one.
    #
    # Deliberately ONE repo. jp-study is 7.3 MB and takes 157 s to fetch (most
    # of it Diary sticker PNGs Chiba never opens), and it is read rarely — an
    # occasional lesson note. Those reads fall through to the Volume at ~1 s,
    # which is fine for something asked for by hand. Pulling it eagerly would
    # trade a 3 s cold start for a 160 s one to speed up a read that happens
    # a few times a day.
    import io
    import shutil
    import tarfile
    import time
    import urllib.request

    LOCAL = Path("/local")
    FAST_REPO = ("jp-companion", "LanguageCompanion")
    _fetched_at = 0.0
    FETCH_TTL = 300.0

    def fetch_fast_layer(force: bool = False) -> None:
        """Pull jp-companion from GitHub into container-local disk."""
        nonlocal _fetched_at
        repo, folder = FAST_REPO
        dest = LOCAL / folder
        if not force and dest.exists() and (time.time() - _fetched_at) < FETCH_TTL:
            return
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return  # no token: everything falls through to the Volume, just slower
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/HelyeFab/{repo}/tarball/main",
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                blob = r.read()
            staging = LOCAL / f".staging-{repo}"
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
                tf.extractall(staging)
            # GitHub wraps the tree in {owner}-{repo}-{sha}/ — unwrap it.
            inner = next(staging.iterdir())
            # Swap in only once the new copy is complete, so a failed fetch
            # never leaves a half-extracted tree being served as the truth.
            tmp = LOCAL / f".new-{folder}"
            shutil.rmtree(tmp, ignore_errors=True)
            inner.rename(tmp)
            shutil.rmtree(dest, ignore_errors=True)
            tmp.rename(dest)
            shutil.rmtree(staging, ignore_errors=True)
            _fetched_at = time.time()
        except Exception as e:  # noqa: BLE001 — never fail a request over the cache
            print(f"fast-layer fetch failed ({e}); falling back to the Volume")

    def read_path(rel: str) -> Path:
        """Where to READ from: the fast layer if it has this path, else the Volume.

        An overlay, not a replacement — the Volume still holds everything, and
        anything written since the last GitHub fetch lives there and only there.
        """
        fetch_fast_layer()
        p = (LOCAL / rel.lstrip("/")).resolve()
        lroot = LOCAL.resolve()
        if (p == lroot or lroot in p.parents) and p.exists():
            return p
        return resolve(rel)

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
        p = read_path(path)
        if not p.is_file():
            raise HTTPException(404, "not found")
        return Response(p.read_bytes(), media_type="application/octet-stream")

    @api.get("/ls")
    async def list_dir(path: str = ""):
        p = read_path(path)
        if not p.is_dir():
            raise HTTPException(404, "not a directory")
        return {"entries": sorted(
            ({"name": c.name, "dir": c.is_dir()} for c in p.iterdir()),
            key=lambda e: e["name"],
        )}

    @api.get("/stat")
    async def stat(path: str):
        p = read_path(path)
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
        body = await request.body()
        # Volume first (durability), then the fast layer if this path lives
        # there — otherwise the very next read would serve the pre-write copy.
        p = resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        vault.commit()
        fast = (LOCAL / path.lstrip("/")).resolve()
        if LOCAL.resolve() in fast.parents and (LOCAL / path.split("/")[0]).exists():
            fast.parent.mkdir(parents=True, exist_ok=True)
            fast.write_bytes(body)
        return {"ok": True, "bytes": len(body)}

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
        fetch_fast_layer()
        vault.reload()
        return {
            "status": "healthy", "service": "chiba-store",
            "volume": sorted(c.name for c in ROOT.iterdir()) if ROOT.exists() else [],
            "fast_layer": sorted(c.name for c in LOCAL.iterdir()) if LOCAL.exists() else [],
            "fast_age_s": round(time.time() - _fetched_at, 1) if _fetched_at else None,
        }

    @api.get("/")
    async def root():
        return {
            "service": "chiba-store",
            "usage": "GET/PUT/DELETE /f?path= · GET /ls · GET /stat · POST /mv · POST /mkdir",
            "auth": "X-API-Key required",
        }

    return api
