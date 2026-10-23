#!/usr/bin/env python3
"""Render a Jekyll layout for every page and check that each link resolves.

Catches language-selector hrefs pointing at URLs Jekyll will never
generate (e.g. assuming /<ref>/ when non-index pages actually live
under /<lang>/<ref>/).

Usage:
    check_layout_links.py <docs_dir> [layout_rel_path]

Requires: pip install python-liquid
"""
import os
import re
import sys

PERMALINK_RE = re.compile(r"^permalink:\s*(\S+)", re.M)
LANG_RE = re.compile(r"^lang:\s*(\S+)", re.M)
REF_RE = re.compile(r"^ref:\s*(\S+)", re.M)
FM_RE = re.compile(r"^---\n(.*?)\n---", re.S)
HREF_RE = re.compile(r'(?:href|src)="(/[^"#?]*)"')


def build_url_map(docs):
    """Replicate the URL Jekyll will generate for each .md under docs/."""
    urls = {}
    for root, dirs, files in os.walk(docs):
        dirs[:] = [d for d in dirs
                   if not d.startswith((".", "_")) and d != "assets"]
        for f in files:
            if not f.endswith(".md"):
                continue
            path = os.path.join(root, f)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            m = FM_RE.match(text)
            fm = m.group(1) if m else ""
            perm = PERMALINK_RE.search(fm)
            if perm:
                url = perm.group(1)
            else:
                rel = os.path.relpath(path, docs)[:-3]
                url = "/" + rel + "/"          # permalink: pretty
            lang = LANG_RE.search(fm)
            ref = REF_RE.search(fm)
            urls[url] = {
                "lang": lang.group(1) if lang else None,
                "ref": ref.group(1) if ref else None,
                "src": os.path.relpath(path, docs),
            }
    return urls


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    docs = os.path.abspath(sys.argv[1])
    layout_rel = sys.argv[2] if len(sys.argv) > 2 else "_layouts/default.html"
    layout_path = os.path.join(docs, layout_rel)
    if not os.path.isfile(layout_path):
        print(f"layout not found: {layout_path}")
        return 2

    try:
        from liquid import Environment
    except ImportError:
        print("SKIP python-liquid not installed (pip install python-liquid)")
        return 0

    env = Environment()
    # GitHub Pages injects baseurl; emulate an empty one.
    env.add_filter("relative_url", lambda v: "/" + str(v).lstrip("/"))
    with open(layout_path, encoding="utf-8") as fh:
        template = env.from_string(fh.read())

    pages = build_url_map(docs)
    valid = set(pages) | {"/okr/"}
    for root, _, files in os.walk(os.path.join(docs, "assets")):
        for f in files:
            valid.add("/" + os.path.relpath(os.path.join(root, f), docs))

    ok = True
    for url, meta in sorted(pages.items()):
        try:
            out = template.render(page=meta, content="",
                                  site={"description": ""})
        except Exception as exc:                      # noqa: BLE001
            ok = False
            print(f"FAIL {url}: render error: {exc}")
            continue
        broken = sorted({h for h in HREF_RE.findall(out) if h not in valid})
        marker = out.count('aria-current="page"')
        flag = ""
        if broken:
            flag = "  BROKEN: " + ", ".join(broken)
        if "langsel" in out and marker != 1:
            flag += f"  (active-language markers: {marker}, expected 1)"
        if flag:
            ok = False
        print(f"{'OK  ' if not flag else 'FAIL'} {url}{flag}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
