#!/usr/bin/env python3
"""
Moon+ position -> KOReader XPath and EPUB CFI.

Reads a Moon+ `.po` triple (chapter entry, characters into that chapter) and
produces the two coordinate systems the other devices speak: the XPath the
CrossPoint sync server stores, and the EPUB CFI that ReadAny's foliate-js
reader uses.

Four traps this encodes. Every one of them produces a plausible-looking wrong
answer rather than an error, which is why each is checked against a real device
screenshot rather than against reasoning:

  1. Moon+'s chapter number indexes the **EPUB 3 navigation document when the
     book ships one**, and the NCX only when it does not. The two disagree:
     a nav document lists subsections that the NCX omits. TM351 is EPUB 3 and
     its nav has 22 entries against the NCX's 10, so "chapter 14" is a real
     subsection in the nav and out of range in the NCX.
  2. The chapter number is never the spine index. Front matter sits in the
     spine and not in the table of contents, so the two diverge by however much
     front matter there is.
  3. A nav entry points at an **element**, not a file: the fragment in
     `u001_s003.xhtml#d0e1272` is the position. The character offset is
     measured from that element, not from the top of the file.
  4. A CFI step counts **element children**, not paragraphs, and publisher
     EPUBs wrap a chapter in nested <div>s. Walking only the body's children
     finds one element, never reaches the offset, and silently reports the
     start of the chapter. Every level of nesting is its own CFI step.

Do NOT trust the percentage in the `.po` to locate anything. It is not computed
over the text: for A Game of Thrones it matches a raw-file-size model to within
0.04%, and for a 312 MB OU book with embedded media it disagrees with the real
position by more than 30 points. It is fit for a progress bar and nothing else.

Verified against three cases, each confirmed by what the device actually showed:

  A Game of Thrones  `*6@0#14627:4.3%`  -> /6/20!/4/74       "Dany had no agents"
  TM358 block 0      `*4@0#0:54.6%`     -> /6/16!/4/2/2/2    "4 Using datasets"
  TM351 part 3 2025  `*14@0#0:83.7%`    -> /6/14!/4/2/2/30/2 "3.3 Limiting the
                                                              display of the
                                                              result data"
"""

import hashlib
import sys
import zipfile
from urllib.parse import unquote
from xml.etree import ElementTree as ET

BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li", "pre"}


def partial_md5(path: str) -> str:
    """KOReader's document id: 1024-byte samples at exponentially spaced offsets."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for offset in [0] + [(1024 << (2 * i)) & 0xFFFFFFFF for i in range(11)]:
            f.seek(offset)
            chunk = f.read(1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load(path: str):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = root.find(".//{*}rootfile").get("full-path")
    opf = ET.fromstring(z.read(opf_path))
    base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
    manifest = {i.get("id"): i.get("href") for i in opf.findall(".//{*}manifest/{*}item")}
    props = {i.get("id"): (i.get("properties") or "") for i in opf.findall(".//{*}manifest/{*}item")}
    spine = [r.get("idref") for r in opf.findall(".//{*}spine/{*}itemref")]

    # Prefer the EPUB 3 navigation document, because that is what Moon+ counts.
    # The NCX is the fallback for EPUB 2 books, which have nothing else.
    toc_href = next((manifest[m] for m, pr in props.items() if "nav" in pr), None)
    if not toc_href:
        toc_id = opf.find(".//{*}spine").get("toc")
        toc_href = manifest.get(toc_id) if toc_id else None
    return z, base, manifest, spine, toc_href


def toc_targets(z, base, toc_href):
    """Every table-of-contents entry, flat, in document order.

    Which document this reads matters more than it looks. Moon+ numbers its
    chapters over the EPUB 3 navigation document when the book ships one, and
    falls back to the NCX only when it does not -- and the two disagree, because
    a nav document lists subsections ("3.3 Limiting the display...") that the
    NCX leaves out. Read the wrong one and every chapter number past the first
    subsection is wrong, usually by enough to land in a different file.

    Keeps the fragment: a nav entry points at an element, not just a file.
    """
    root = ET.fromstring(z.read(base + toc_href))
    out = []
    if root.tag.endswith("ncx"):
        for point in root.findall(".//{*}navPoint"):
            content = point.find("{*}content")
            if content is not None:
                out.append(unquote(content.get("src", "")))
    else:  # EPUB 3 nav document
        for a in root.findall(".//{*}a"):
            if a.get("href"):
                out.append(unquote(a.get("href")))
    return out


def anchor_offset(body, anchor: str):
    """Characters of text before the element carrying `anchor`, in locate()'s
    accounting, or None when the id is not found."""

    def rec(el, acc, strict):
        for child in el:
            tag = child.tag.split("}")[-1]
            if strict and tag not in BLOCK_TAGS:
                continue
            if child.get("id") == anchor:
                return acc
            inner = rec(child, acc, strict)
            if inner is not None:
                return inner
            acc += len("".join(child.itertext()))
        return None

    return rec(body, 0, True)


def locate(body, char_offset: int):
    """Walk the block elements to the offset, descending through wrappers.

    Two things make the naive walk wrong on real books. Publisher EPUBs often
    wrap the whole chapter in a single <div>, so the paragraphs are not direct
    children of the body at all -- a walk over body's children sees one element,
    never reaches the offset, and falls off the end returning paragraph 0. And
    once you descend, a CFI is no longer one step: it is a step per level.

    Returns (steps, paragraph_number, hit) where `steps` is the child position
    at each level from the body down, 1-based, and `hit` names the element
    actually landed on -- a chapter often opens on a heading, not a <p>, and an
    xpath of `p[0]` is not a position, it is a bug wearing one.
    """

    def descend(el, remaining, para, hit):
        children = [c for c in el if c.tag.split("}")[-1] in BLOCK_TAGS]
        if not children:
            return None, remaining
        for child in el:
            tag = child.tag.split("}")[-1]
            if tag not in BLOCK_TAGS:
                continue
            text = "".join(child.itertext())
            if tag == "p":
                para[0] += 1
            if remaining < len(text):
                pos = list(el).index(child) + 1
                inner, remaining = descend(child, remaining, para, hit)
                if not inner:
                    same = [c for c in el if c.tag.split("}")[-1] == tag]
                    hit.update(tag=tag, nth=same.index(child) + 1)
                return ([pos] + inner) if inner else [pos], remaining
            remaining -= len(text)
        # Offset ran past everything here: clamp to the last block child.
        last = children[-1]
        ltag = last.tag.split("}")[-1]
        same = [c for c in el if c.tag.split("}")[-1] == ltag]
        hit.update(tag=ltag, nth=same.index(last) + 1)
        return [list(el).index(last) + 1], remaining

    para, hit = [0], {"tag": "p", "nth": 1}
    steps, leftover = descend(body, char_offset, para, hit)
    return steps or [1], para[0], hit


def convert(path: str, ncx_entry: int, char_offset: int):
    z, base, manifest, spine, toc_href = load(path)
    targets = toc_targets(z, base, toc_href)
    if not 1 <= ncx_entry <= len(targets):
        raise SystemExit(f"TOC entry {ncx_entry} out of range (book has {len(targets)})")

    target, _, anchor = targets[ncx_entry - 1].partition("#")
    hrefs = [manifest[i] for i in spine]
    spine_idx = next(
        (i for i, h in enumerate(hrefs) if unquote(h).split("/")[-1] == target.split("/")[-1]),
        None,
    )
    if spine_idx is None:
        raise SystemExit(f"NCX target {target!r} is not in the spine")

    doc = ET.fromstring(z.read(base + hrefs[spine_idx]))
    body = doc.find("{*}body")
    body_chars = len("".join(body.itertext()))

    # A nav entry points at an element; the offset is measured from there.
    base_offset = 0
    if anchor:
        found = anchor_offset(body, anchor)
        if found is None:
            raise SystemExit(f"anchor #{anchor} not found in {hrefs[spine_idx]}")
        base_offset = found

    overflow = base_offset + char_offset > body_chars
    steps, para_no, hit = locate(body, base_offset + char_offset)

    # /6/<spine> ! /4 <body> then one step per level down.
    tail = "".join(f"/{2 * s}" for s in steps)
    return {
        "doc_id": partial_md5(path),
        "spine_index": spine_idx,
        "file": hrefs[spine_idx],
        "anchor": anchor or None,
        "chapter_chars": body_chars,
        "paragraph": para_no,
        "steps": steps,
        "xpath": f"/body/DocFragment[{spine_idx + 1}]/body/{hit['tag']}[{hit['nth']}]",
        "cfi": f"epubcfi(/6/{2 * (spine_idx + 1)}!/4{tail})",
        "warning": (
            f"offset {base_offset + char_offset} exceeds the chapter's {body_chars} characters "
            "-- position clamped to the end, NOT trustworthy"
            if overflow else None
        ),
    }


if __name__ == "__main__":
    epub, entry, offset = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    result = convert(epub, entry, offset)
    warning = result.pop("warning")
    for k, v in result.items():
        print(f"  {k:14} {v}")
    if warning:
        print(f"\n  !! {warning}")
        sys.exit(2)
