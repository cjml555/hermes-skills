#!/usr/bin/env python3
"""Validate a translated Android strings file against its base version.

Usage: verify_locale.py res/values/strings.xml res/values-es/strings.xml
Exits non-zero and prints each mismatch class found.
"""
import re
import sys
import xml.etree.ElementTree as ET

NAME_RE = re.compile(r'<string name="([^"]+)"')
PLACEHOLDER_RE = re.compile(r'%[\d$sd.f]*')


def entries(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    ET.fromstring(text)  # raises ParseError with line number
    return (
        text,
        NAME_RE.findall(text),
        PLACEHOLDER_RE.findall(text),
        text.count("\\n"),
    )


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    base_text, base_names, base_ph, base_nl = entries(sys.argv[1])
    new_text, new_names, new_ph, new_nl = entries(sys.argv[2])

    ok = True
    if base_names != new_names:
        ok = False
        print(f"FAIL names/order differ: {len(base_names)} base vs {len(new_names)} translated")
        for a, b in zip(base_names, new_names):
            if a != b:
                print(f"  first divergence: base={a!r} translated={b!r}")
                break
    if base_ph != new_ph:
        ok = False
        print(f"FAIL placeholders differ: {len(base_ph)} vs {len(new_ph)}")
        for i, (a, b) in enumerate(zip(base_ph, new_ph)):
            if a != b:
                print(f"  first divergence at #{i}: base={a!r} translated={b!r}")
                break
    if base_nl != new_nl:
        ok = False
        print(f"FAIL newline markers differ: {base_nl} vs {new_nl}")

    leftover = re.findall(r'[\u4e00-\u9fff]', new_text)
    if leftover:
        print(f"WARN {len(leftover)} CJK chars remain - source text left untranslated")

    print("OK" if ok else "FAILED", f"({len(new_names)} entries)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())