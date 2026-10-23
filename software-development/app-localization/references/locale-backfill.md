# Backfilling a partially-translated locale

For topping up a locale that already has a `values-xx/` directory. Not for
shipping a brand-new locale — see SKILL.md for that.

## Why the audit number lies

A coverage tool reports "missing" by comparing key names across files. That
number conflates two very different jobs:

1. Keys never translated (base value in English, or in some third language).
2. Keys already written in the target language but sitting in the BASE
   locale directory, because someone translated them in the wrong file and
   never duplicated them.

Group 2 needs a copy, not a translation. On a real backfill the tool reported
98 missing and only 48 needed translating — the other 44 were already correct
Chinese sitting in the default file.

## Triage

Split the reported gaps by inspecting the base value for target-language
characters before dispatching any subagent:

```python
import re, xml.etree.ElementTree as ET
cjk = re.compile(r'[\u4e00-\u9fff]')          # per target script

def vals(p):
    r = ET.parse(p).getroot()
    return {c.get("name"): (c.text or "") for c in r if c.tag == "string"}

D = vals("app/src/main/res/values/strings.xml")
Z = vals("app/src/main/res/values-zh-rCN/strings.xml")
missing = [k for k in D if k not in Z]

already = [k for k in missing if cjk.search(D[k])]          # copy verbatim
todo    = {k: D[k] for k in missing if not cjk.search(D[k])}  # translate
```

Dispatch only `todo`. Copy `already` straight across — but read each value
first: the group also contains proper nouns that must NOT be copied blindly.

## Before adding any key

Coverage tools normally compare ONE file against the default. Grep the entire
locale directory for the key name across all string files:

```bash
grep -rn 'name="KEYNAME"' app/src/main/res/values-xx/
```

If it already exists in a sibling file, the correct action is nothing. Adding
it to the main file fails the build at `mergeDebugResources` with
`Duplicate resources`.

## Non-translatable keys

Language names (`Python`, `Perl`, `Ruby`, `Java`), tool names, and
contributor handles are identical in every locale. Mark them in the base file:

```xml
<string name="pkg_cat_python" translatable="false">Python</string>
```

Audit scripts that count by key name ignore this attribute and keep listing the
keys. That is expected and does not block a gate.

## Verifying the merge

Placeholders must match the base value as an ordered sequence, not just a count:

```python
ph = lambda s: re.findall(r'%(?!%)\d*\$?[sd]', s)
bad = [k for k in todo if ph(D[k]) != ph(translated[k])]
```

Line breaks may legitimately differ — Chinese is more compact than English and
often replaces an English line break plus 8-space indent with an explicit break.
Compare meaning and structure, not raw newline counts.

## Reuse another branch's tooling

If a sibling branch already ships a coverage script or scaffold generator,
`git checkout <ref> -- tools/i18n/` to adopt it instead of writing your own, then
run it against your work. It may be stricter than your manual check and will
catch what you missed.