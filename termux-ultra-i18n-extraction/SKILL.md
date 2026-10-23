---
name: termux-ultra-i18n-extraction
description: Extract hardcoded Termux-Ultra UI literals to strings.xml.
---

# Termux-Ultra i18n literal extraction

The repo has an i18n gate (`tools/i18n/check_translations.py --gate`) that only checks
*strings.xml ↔ strings.xml* consistency. It is blind to hardcoded literals in `.kt` files,
so it stays green while the UI shows Chinese to English/Spanish users. Always verify with a
separate literal scan (below), not the gate alone.

## Locale rules
- `values/strings.xml` = **English** only. Never put Chinese there.
- `values-es/` = neutral Latin American Spanish, `tú` form, no voseo.
- `values-zh-rCN/` = natural Simplified Chinese.
- Key naming: snake_case English, lowercase, prefixed by screen —
  `oobe_`, `about_`, `nav_`, `remote_`, `pkgdetail_`, `pkgmgr_`, `res_`, `crash_`,
  `fm_`, `main_`, `log_`, `terms_`, `risk_`.
- Placeholders: Android `%1$s` / `%2$d`, preserve order. No `${...}` interpolation in resources.
- Keep emoji inside the value. Never translate paths, commands, packages, URLs, identifiers.
- Literal identifiers used for *matching* (e.g. `RiskType.displayName` compared against
  `"dd 磁盘写入"`) are keys, not UI text — leave them and document the decision.

## Highest-value first
Many strings already exist translated in all 3 locales but the Kotlin hardcodes Chinese
instead of referencing them. **Grep the existing keys and reuse them** rather than adding
new ones — e.g. `storage_*`, `risk_command_*`, `overview_*`, `common_select_all`.

## Composable vs non-composable context
- Inside `@Composable` → `stringResource(R.string.x)`.
- Inside `LaunchedEffect` / `onClick` / plain functions with `Context` → `context.getString(...)`.
- Inside a `LazyListScope` / `ColumnScope` builder (non-`@Composable` lambda) →
  **hoist** the string into a `val` in the enclosing composable first, then use it.
- A plain `enum` whose labels feed another file can't just become `stringResource`.
  Options, in order of preference: (1) keep the property name and resolve via a cached
  application context; (2) convert to `@StringRes` ids + getter. Check every consumer file
  before changing a signature — a `data class` property may be read from files you don't own.

## Concurrent agents
Other agents edit the same `strings.xml` files and `plugin/` / vendored `gaurav/avnc` code.
A read-modify-write of the whole file will silently clobber their keys. Use an **idempotent
heal step** (check if key exists, append only if missing) re-run right before verification.
Build failures in files you don't own are transient — re-run before assuming you broke it.

## Escaping
Android resources must escape apostrophes and double quotes (`Agent\'s`, `&quot;`) or the
resource fails to flatten. Existing files already do this (`diskpart\'s`).

A value whose **text starts or ends with a space must be wrapped in quotes**, or AAPT silently
trims it and a marker like `" ◀ current"` comes out as `"◀ current"` — no build error, wrong
output: `<string name="eng_marker_current">" ◀ current"</string>`.

## Refactoring a Kotlin string template into a resource
Splitting `"$username@$host:$port" + if (unlimited) "" else "（点击卡片以连接）"` into two
resources (`eng_ssh_conn_addr`, `eng_ssh_conn_addr_tap`) keeps the branch outside the resource.
Pass the handle as `ts.mHandle.toString()` and `ts.isRunning.toString()` so `%s` never receives a
numeric; reserve `%d` for real `Int`s (ports, counts) or `getString` throws at runtime.

## Verify
When other agents build concurrently, **do not use Gradle** — a shared KSP cache corrupts and
produces fake failures (`StreamCorruptedException`, `unexpected EOF`). Verify statically instead:
1. `xml.etree.ElementTree.parse` on every `values*/strings.xml` you touched.
2. Every `R.string.X` in your functions exists in `values/`, `values-es/`, `values-zh-rCN/`.
3. `%\d+\$[sd]` sets are identical across the 3 locales for your new keys.
4. No `[\u4e00-\u9fff]` in `values/`.
5. No CJK string literal left in your own functions.

Then still run the gate (it is strings.xml-vs-strings.xml only, so it stays green while Kotlin
hardcodes Chinese — never treat a green gate as proof):
```
python3 tools/i18n/check_translations.py --gate
```
With Gradle when the build is yours alone:
```
./gradlew :app:compileDebugKotlin --console=plain 2>&1 | grep -E '^e: |BUILD'
```

## Run aapt2 directly — ElementTree passes what aapt2 rejects

When `mergeDebugResources` fails with `Can not extract resource from
ParsedResource@...` and there are **zero** `e:` errors, the XML is well-formed but
AAPT-invalid. `xml.etree` will not tell you. Get the real message (it names file
and line):
```
aapt2=$(find ~/.gradle/caches -name aapt2 -path '*linux*' | head -1)
"$aapt2" compile --dir app/src/main/res -o /tmp/res.zip   # rc 0 = resources valid
```
Two things it catches that parsing does not: an **unescaped apostrophe** (Android
requires `\'`; `<string name="x">', '</string>` fails even though the XML is fine —
quoting the whole value is NOT a valid workaround), and a value that **starts with
whitespace or a newline**. Run this before Gradle whenever you appended entries by hand.

## A truncated strings.xml destroys every other agent's work

If an agent crashes mid-`write` and restores the file with `git checkout --`, every
key the *other* agents had added is gone while their Kotlin still references them.
Sweep for unresolved references across the whole tree afterwards:
```python
en = {e.get('name') for f in glob('app/src/main/res/values/*.xml')
              for e in ET.parse(f).getroot() if e.tag == 'string'}
for f in glob('app/src/main/java/**/*.kt', recursive=True):
    missing |= {k for k in re.findall(r'R\.string\.(\w+)', src) if k not in en}
```
`SharedR.string.x` keys live in `termux-shared/src/main/res` — include that path or
you will chase false positives. Write resource files via `tempfile.mkstemp` +
`os.replace()` so a crash cannot truncate one.