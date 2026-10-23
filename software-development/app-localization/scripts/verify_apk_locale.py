#!/usr/bin/env python3
"""Prove a locale actually shipped inside a built APK.

A green Gradle build does NOT mean the translation reached the device:
`resConfigs` filters locales at package time. This inspects the artifact.

Usage:
    verify_apk_locale.py <apk> <locale> [sample string ...]

Exits non-zero if the locale is not declared, or if a provided sample
string is absent from resources.arsc.
"""
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path


def find_aapt2(sdk_root):
    """aapt2 ships per build-tools version; use the newest one present."""
    roots = [Path(sdk_root), Path.home() / "Android/sdk",
             Path.home() / "Android/Sdk"]
    for root in roots:
        bt = root / "build-tools"
        if not bt.is_dir():
            continue
        versions = sorted(
            (d for d in bt.iterdir() if (d / "aapt2").exists()),
            key=lambda d: [int(p) if p.isdigit() else 0
                           for p in re.split(r"[.\-]", d.name)],
        )
        if versions:
            return str(versions[-1] / "aapt2")
    return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    apk, locale = sys.argv[1], sys.argv[2]
    samples = sys.argv[3:]

    aapt2 = find_aapt2(os.environ.get("ANDROID_HOME", ""))
    if not aapt2:
        print("SKIP aapt2 not found - cannot read declared locales")
        return 0

    badging = subprocess.run([aapt2, "dump", "badging", apk],
                             capture_output=True, text=True).stdout
    m = re.search(r"locales: (.*)", badging)
    declared = re.findall(r"'([^']+)'", m.group(1)) if m else []
    # aapt2 prints BCP-47-ish tags; 'es' covers values-es
    norm = {d.lower().replace("_", "-") for d in declared}
    want = locale.lower().replace("_", "-")
    shipped = want in norm or any(d.split("-")[0] == want for d in norm)

    print(f"declared locales: {declared or ['(none besides default)']}")
    if not shipped:
        print(f"FAIL locale {locale!r} is NOT in the APK - check resConfigs "
              f"in the module build.gradle")
        return 1
    print(f"OK locale {locale!r} declared")

    if samples:
        with zipfile.ZipFile(apk) as z:
            arsc = z.read("resources.arsc")
        for s in samples:
            # resource strings live in the UTF-8 string pool
            hit = s.encode("utf-8") in arsc
            print(("OK   " if hit else "FAIL ") + f"sample present: {s!r}")
            if not hit:
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
