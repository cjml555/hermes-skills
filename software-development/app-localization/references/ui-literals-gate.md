# UI literals: the blind spot a coverage gate cannot see

A resource-coverage tool answers "does every key in `values/` have a
translation in `values-es/`?". It cannot answer "is everything the user reads
translated?" — because text written directly in the source never became a key.
A project can report 100% coverage in every locale and still render a whole
screen in the wrong language.

This is the only i18n failure mode that is invisible from the resource files,
so it has to be checked against the source tree separately.

## Symptom

The user opens the app in their language and a screen renders in a third
language. The coverage gate is green the whole time. Nothing in
`values/`, `values-es/` or `values-zh-rCN/` is wrong.

## Detection

Scan the source for UI call sites taking a bare string literal. The shapes that
reach the user:

| Source | API |
|---|---|
| Compose | `Text("…")`, `TextField(label = "…")`, `placeholder = "…"` |
| Feedback | `Toast.makeText(ctx, "…")`, `SnackbarHelper.show(ctx, "…")` |
| Dialogs | `AlertDialog(title = "…")`, `.setTitle("…")` |
| A11y | `contentDescription = "…"` (read aloud by TalkBack — still user-facing) |
| View-model / engine return | `SkillExecutionResult(true, "…")`, `emit(Event("…"))`, a `data class` whose property is display text |
| Shell `echo` inside a generated script | the line's output flows back into a UI card, so it renders |
| Card / result fields | `title = "…"`, `description = "…"`, `summary = "…"`, `output = "…"` |

Two cheap refinements that cut the noise dramatically:

- **Skip log lines.** `Log.d/v/i/w/e(…)` is invisible to the user. Filtering
  lines matching `Log\.[dviwe]\s*\(` removed most of a 330-hit grep.
- **Flag CJK separately from the count.** `Text("还没配置")` and `Text("Hello")`
  are the same bug, but the first is what makes it obvious the gate is lying.
  Report total and CJK separately so the reader sees severity at a glance.

## Decide what NOT to report — by asking who receives the string

The classification that generalizes: **does the string reach a person, or does it
reach a model, a log, or a parser?** Four categories are legitimately untranslated:

| Category | Example | Why leave it |
|---|---|---|
| System prompts | `msgs.add(OpenAiMessage("system", teacherSys))`, a `"""…"""` block fed to a model, a prompt embedded via `cat << 'EOF'` | translating it changes model *behaviour*, not language — the most damaging thing you can do in an i18n pass |
| Logs | `Log.i(TAG, "…")`, `Log.e`, `Log.d` | invisible to users; translating it only breaks grep |
| Protocol identifiers compared as keys | `TASK_ADD`, `RUN_COMMAND`, `command`, `title`, a `SkillType` name | the model emits the token and the code matches on it; a translated value stops matching |
| Machine-readable output | `"[D]"`, `"[F]"`, `"[?]"`, `"[OK]"`, `[id: …]` | parsed or column-aligned, not prose |

The `echo` case is the subtle one and cuts the other way: a shell `echo` whose
output is parsed back into a UI card **is** user-facing and should be
translated, while a prompt written into a heredoc in the same script is not.
Classify by destination, not by the shell.

Classify by **destination, not by appearance** — a CJK string inside a `"""` block
may be either a prompt (leave) or a display template (translate), and only the
consumer tells you which.

## Remediation order

1. Add the detector in report-only mode, committed.
2. Extract by screen, worst first — rank by literal count and by how much of
   that screen is untranslated.
3. Give every subagent one file group plus the same rule block: default
   resource file is the base language (never a third language), target locales
   match the project's existing ones, placeholders use `%1$s` positional form
   with original order preserved, and interpolation is applied in code, never
   left as `${…}` inside the resource.
4. After each group: compile, run the coverage gate, and re-run the literal scan
   to confirm the count fell by exactly the number you fixed.
5. Only then flip `--gate` on.

Reusing the project's own risk/permission classification rather than inventing
one applies here too: pick prefix names that match what already exists
(`ai_`, `plugin_`, `oobe_`) so the resource file stays navigable.

## The fourth blind spot: a noise filter that excludes the script it was written to find

A detector's own filters are code, and they fail like code. The one that costs
the most here is a "this short, space-free literal is probably an identifier,
not text" heuristic. It is reasonable for Latin script and **wrong for every
language that does not put spaces between words**:

| Value | Latin heuristic says | Reality |
|---|---|---|
| `navScale`, `topBarBg` | identifier — skip | correct, animation label |
| `复制` (copy) | identifier — skip | **UI text, button label** |
| `端口` (port) | identifier — skip | **UI text, form field** |
| `密码` (password) | identifier — skip | **UI text, form field** |

So the filter silently discarded **every CJK literal in the project** — the one
language the detector was built to find. A report claiming "zero untranslated
Chinese" was the filter talking, not the app.

Two rules that fall out:

- **Test a detector against the exact input it exists to find.** Inject the
  literal by hand (`contentDescription = "开发者头像"`), confirm the gate goes
  red and names it, then restore. A filter validated only against Latin samples
  is untested for the case that motivated it.
- **Put the script check before any length/space heuristic.** `if CJK.search(s):
  return True` costs nothing and closes the hole. Order the guards so the
  discriminating condition runs first.

When fixing it, expect the count to jump. The hidden population was larger than
the reported one — here the honest count went from a reported 34 to an actual
85, and 51 of the newly-visible ones were real CJK UI text, concentrated in
`contentDescription` (copy/cut/rename/delete/port/user/password). **A detector
reporting a suspiciously clean number is a reason to distrust it, not to
declare victory.**

## False positives: Compose animation labels are not UI

`label = "…"` is heavily overloaded in Compose. On a transition it is an
identifier for the animation inspector and is never rendered:

```kotlin
val topBarAlpha by animateFloatAsState(
    targetValue = scrollFraction,
    label = "topBarAlpha"        // not text
)
```

Distinguish by looking **backwards**: the label sits *after* the call, which can
span six lines, so scan a window of preceding lines for `animationSpec`,
`transitionSpec`, `animate*`, `AnimatedContent`, `fadeIn/Out`, `togetherWith`,
`RepeatMode`. Checking only the current line caught roughly half of them; a
line-lookback caught more, and an 8-line window caught all. Here this alone was
33 of 75 reported hits.

The other deliberate exclusions, each with its reason recorded next to it so the
next reader does not re-add them:

| Excluded | Why |
|---|---|
| `contentDescription = "Termux Agent"` | brand name, identical in every locale |
| `"StackTraces"` in a logger | goes to a log file, not the screen |
| `"$doneRounds/$total"`, `"#${index + 1}"` | pure formatting over already-translated values |

Document exclusions as a named list with reasons rather than as scattered
`if` statements — otherwise the next person cannot tell a deliberate skip from an
oversight and "fixes" it back in.

## Bulk extraction breaks compilation in predictable ways

Replacing literals mechanically breaks the build in a small number of
predictable shapes. Each round of `compileDebugKotlin` after a batch surfaces
one class, so budget for several rounds and treat the error list as a
work order rather than a surprise. On a ~50-literal batch this took four rounds:
36 errors, then 24, then 4, then 0.

| Failure | Cause |
|---|---|
`Unresolved reference 'stringResource'` | the file never imported Compose's `stringResource` — it had no resource calls before |
`Unresolved reference 'R'` | `com.termux.R` not imported; some files share a package with the resources and some do not |
`Unresolved reference 'getString'` / `'string'` | the call site is inside `setContent`, where the composable `stringResource(id)` is correct and the Activity method `getString(id)` is not reachable |
`Syntax error: Unexpected tokens` | a multi-argument `Text("literal")` rewritten to `Text(stringResource(...), ...)` lost or gained a closing paren |
| `Functions which invoke @Composable functions must be marked @Composable` | a `@Composable` helper was given a `Context` parameter, which makes it a non-composable function that then calls `stringResource` |
| `Unresolved reference 'context(...)' expected` | a parameter named `context` shadows a function named `context()` — see below |

Two rules that follow:

- **Pick the accessor by the surrounding scope, not by what the original file
  used elsewhere.** `getString` inside a `setContent` lambda is a compile
  error, and it is the single most common failure in an Activity that mixes
  programmatic and Compose UI.
- **Check parens on the rewritten call, not just the arguments.** These are
  mechanical edits; a wrapper call added around an existing argument list is
  where the balance goes wrong, and each break costs a full compile round.

Reuse an existing key when the text already matches rather than minting a near
duplicate — the failures above shrink with every edit that does not touch a
call signature.

## In a non-`@Composable` object, add a helper — never add a `Context` parameter

The instinct when a plain object or engine function has no `Context` is to add
one as a parameter so it can call `getString`. **This is the single most
expensive mistake in a bulk extraction**, and it has been made and reverted more
than once.

If the object already resolves a context anywhere — an `appContext` field set by
an `init()` from the Activity, a `context()` accessor — add a `str()` helper
beside it and change **zero** signatures:

```kotlin
private fun str(@StringRes res: Int, vararg args: Any): String {
    val c = context() ?: return "-"
    return if (args.isEmpty()) c.getString(res) else c.getString(res, *args)
}
```

Why the parameter version fails: it **shadows** any local or member named
`context` in the same function, so every existing `context.getString(...)` inside
resolves to the new parameter instead of the real context — 30+ errors across
unrelated lines, in files you were not trying to touch. It also forces edits to
every call site, including ones owned by other people or agents.

Two Kotlin facts about the helper:

- `vararg args: Any` does **not** accept `String?`. Write `str(res, e.message ?: "")`.
  Every nullable (`.message`, a lookup result, a `when` with an unmatched branch)
  needs the elvis or the batch fails to compile with `Argument type mismatch`.
- `vararg args: Any` widens every argument, so `%d` on a `Boolean` or a
  pre-formatted `Long` renders wrong or throws. Pass `.toString()` for handles;
  reserve `%d` for real `Int`s.

Return a short fallback (`"-"`) instead of throwing when the context is not yet
initialized — these run in progress and logging paths where an exception kills
the whole session.

If you already added the parameter and are deep in errors, `git checkout --` the
touched files and redo it with the helper. Reverting cost less than pushing
through.

## Never derive a resource value by copying the literal out of the source

The obvious shortcut when writing a resource is to reuse the string you just
replaced. It silently carries the **source language's interpolation syntax**:

```kotlin
"第 ${thisIdx}/$targetRounds 轮：开始"   // Kotlin template, 2 runtime args
```

```xml
<string name="trainer_round_start">第 ${thisIdx}/$targetRounds 轮：开始</string>
```

That resource has **zero** placeholders while the call site still passes two
arguments. The build is green, the coverage gate is green, and the app throws
`MissingFormatArgumentException` the first time that line renders — on a
progress line, mid-training.

Write the `%1$s` / `%2$d` form by hand, per locale, and then diff the
placeholder *sets* across all three locales for every new key. A gate that only
checks "does the key exist" cannot see this; a gate that compares placeholder
sets against the base catches it immediately. Treat a placeholder divergence as a
hard failure, never a warning.

## After extraction, logic that compared the old literal silently breaks

Moving a string to a resource removes the constant that neighbouring code was
matching against. The breakage is rarely a crash — it is a wrong number:

```kotlin
// before: the notice is a Chinese literal, the prefix comparison works
if (msg.startsWith("(命令")) { /* count it as an empty result */ }

// after: in en/es the notice comes from a resource, the prefix never matches,
// so the empty-result line is counted as a real result
```

Sweep for every `startsWith` / `contains` / `trimStart` / regex that referenced a
now-translated string and re-point it at the **resource key**, not at translated
content. Then grep for the old literal's ASCII fragments to catch the ones you
missed. A Chinese-prefix comparison that still "works" in `values-zh-rCN` is the
most dangerous case: it passes every manual check in the source locale and is
wrong everywhere else.

The same grammar trap in the other direction: a hardcoded `" "` between two
resources is wrong for languages that do not separate words with spaces. Split
into two whole keys instead of concatenating a separator.

## Do not ship pre-formatted text across a producer/consumer boundary

When a producer (engine, ViewModel, event bus, flow) hands the consumer a
finished `String`, the locale is baked in at the producer and the consumer cannot
re-localize it:

```kotlin
data class EtaUpdated(val remainingRounds: Int, val avgRoundMs: Long)          // localizable
data class EtaUpdated(val remainingRounds: Int, val avgRoundMs: Long, val etaText: String)  // not
```

Carry the raw data and let the consumer that knows the context format it. Look
for this shape anywhere a `data class` property, an `emit(...)` argument, or a
`StateFlow<T>` holds display text — those are the seams where a locale gets
frozen. Fixing it is a signature change to a type other files consume, so check
every consumer first, and expect the compile error to point at the producer.

## Parallel extraction: the four ways it goes wrong

Fan out per file or per function. Every one of these has happened:

1. **Concurrent builds corrupt the shared KSP/incremental cache.** Multiple
   `gradlew` runs against one repo produce
   `java.io.StreamCorruptedException: unexpected EOF in middle of data block`
   and `kspDebugKotlin` failures with **zero** Kotlin errors. Agents read this as
   their own breakage and start editing working code to "fix" it. Tell subagents
   up front: **do not run Gradle while siblings are building**; verify statically
   (parse each touched `values*/strings.xml` with ElementTree, assert every
   `R.string.X` referenced in your functions exists in all locales, compare
   placeholder sets, assert no CJK in the base locale). Build once, alone, at the
   end with `--no-build-cache`.
2. **Line-number anchors rot.** With N agents editing one `.kt`, line numbers
   shift under you and replacements by line range silently no-op — a count of 0
   with no error. Recompute function spans from content (brace matching on the
   function name) and assert the expected replacement count before writing.
3. **Partitions must be disjoint and stated.** Give each agent its function list
   *and* the sibling ranges it must not touch, or agents helpfully translate
   outside their scope and clobber each other.
4. **A subagent reporting "keys referenced but missing from every XML" is a
   snapshot of a race**, not a finding — a sibling had rewritten the `.kt` lines
   before its XML append landed. Re-verify yourself after the batch rather than
   acting on the report.

Also worth telling subagents explicitly: report out-of-scope findings instead of
fixing them. Several reported "these other functions still have CJK, not mine"
and that list became the next dispatch's worklist.

## The second blind spot: translated text that is structurally broken

A coverage gate also cannot see damage *inside* a translated value. This is the
other state where the gate is green and the screen is wrong.

The shape: the base string contains an XML entity (`Tips & Agent`), the
translator renders the connector as a word (`y`), and the entity's tail is left
attached to it — producing `Consejos yamp; agente`. The `&` is gone; only `amp;`
remains, welded to the surrounding word.

Nothing catches it: the XML is valid, the placeholder set is unchanged, the key
exists in every locale, and the sentence is still readable. It reaches the
screen exactly like that.

The detection rule has to key on the **absent `&`**, not on `&amp;`. Both forms
are legal and must be told apart:

| Value | Verdict | Why |
|---|---|---|
| `Colores yamp; fuentes` | **broken** | entity tail with no `&`, glued to a word |
| `Backup &amp; Restore` | fine | valid escape, renders `&` |
| `todo &amp; ir a la config` | fine | same, spaces around it |
| `a&amp;b` | fine | valid escape inside a word |

A first attempt that searches for `&amp;` glued to a word finds nothing — the
`&` is precisely what is missing. Match an entity name preceded by a letter and
*not* preceded by `&`, and cover `quot|apos|lt|gt` alongside `amp`.

Two follow-ups when you add this to a gate:

- **Expect a cluster.** One reported instance is a class, not an instance; here
  four more shared the pattern and were found only after the detector existed.
- **Give the new failure class its own counter.** Folded into an existing
  `hard_failures` total, the gate reported the failure as "placeholder
  divergente" — true that the build was blocked, wrong about why, and it sends
  the next person to debug the wrong place. Report the escape failures first,
  with the concrete before/after in the message, then placeholders.

The user's eye found this one during a manual pass over the translations. A
human reading values still catches things a percentage cannot — worth saying
so rather than implying the tooling covered it.

## The third blind spot: `\uXXXX` in a resource, which Android does not decode

The same "green gate, wrong screen" state has a second cause, and this one is
silent in a different way: **it produces no error at all, anywhere.**

`strings.xml` is XML, not JSON. Android does **not** interpret `\u00ed` in a
resource value — it renders the backslash and the digits as text:

| Value | Screen shows | Verdict |
|---|---|---|
| `Todav\u00eda` | `Todav\u00eda` | **broken** |
| `Todavía` | `Todavía` | fine |
| `\u0020＞\u0020` | ` ＞ ` | fine |

So a machine translation (or a translation tool that JSON-escapes its output)
can fill a whole locale with values that are internally consistent, have valid
placeholders, and are 100% covered — and every accented character reaches the
user spelled as an escape. It compiles, it installs, and the only evidence is
the screen itself.

Detection is one regex over the resource files: `\\u[0-9a-fA-F]{4}`. Sweep
**every** `values*/` directory, not just the target locale — the base file gets
the same damage.

Two refinements, both learned from a false positive:

- **Only flag escapes that produce a *visible* character.** Space and
  non-printable escapes are legitimate and used on purpose — a breadcrumb
  separator is literally `\u0020＞\u0020` in a vendored add-on. Decode the code
  point and skip `char.isspace()` and `char.isprintable() is False`. Without
  that filter the gate goes red on pre-existing upstream code you must not touch.
- **The check belongs in the same coverage gate**, as its own counter with its
  own message, for the reason above: folding it into the placeholder total
  sends the next reader to the wrong file.

Write the explanatory comment with the decode rule, not just the regex — the
next person will assume JSON semantics and "fix" correct values.

## Compressing a lookup table before keying it

A large generated table (extension→description, MIME map, country list) can hold
hundreds of near-identical entries. Measure before keying one-per-entry — the
literal count says nothing about the real key count.

Split each value into `PREFIX@@category@@` and key only the **repeated** parts.
The reuse test is mechanical: count how many distinct descriptions share each
suffix, and key only suffixes used more than once. One-off suffixes do not pay
for a key.

Here this turned 535 unique descriptions into 68 keys covering 254 of them,
because many descriptions end in the same word (`ZIP 压缩`, `RAR 压缩`,
`Gzip 压缩`). Names the frequency ordering so later additions do not renumber
anything.

### The split point must be a real token boundary, not "ends with a known suffix"

This is the failure mode that makes the compression technique go wrong silently,
and it is specific to scripts that do not separate words with spaces.

The mechanical split — "take the longest known category the value ends with,
everything before it is the prefix" — produces **garbage in every locale**,
because the match lands *inside* a word:

| Value | Naive split | Result |
|---|---|---|
| `JPEG 文件交换格式` | ends with `格式` | `JPEG 文件交换@@格式@@` → "JPEG file exchange **format**" (compounds a noun phrase) |
| `GIF 动图` | ends with `图` | `GIF 动@@图@@` → "GIF anim**ated image**" |
| `位图图像` | ends with `图像` | `位图@@图像@@` |
| `设备无关位图` | ends with `位图` | `设备无关@@位图@@` |

None of these compile-break. Each yields a plausible-looking key, a valid
resource in all three locales, and a wrong description on screen.

**Only split where the source actually separates tokens** — a space, or a
character class boundary you have verified. `GIF 动图` has a real space before
`动图`; `文件交换格式` has none, so it is a single compound and must not be
split at all.

Two rules:

- **Gate the split on a delimiter.** `val.rsplit(" ", 1)` and require the tail to
  be an exact key in your category table. Anything else is left whole.
- **Spot-check the output before writing 700 edits.** Print ten converted pairs
  and read them as sentences. Machine-plausible is not the bar; a human reading
  "GIF anim ated image" would have caught this in one line.
- **Expect a big drop in coverage after the delimiter rule.** That drop is the
  truth, not a regression.

### Measure with the rule you will ship with

Count the convertible entries using the **same** boundary predicate as the
conversion. A suffix-frequency count taken over naive token splits reports
hundreds of convertible entries where the delimiter-safe rule finds a few dozen.
Quoting the inflated number to the user is the failure: it reads as "708 of 921
done" when the real answer was "48 of 921", and it sets an expectation the work
cannot meet.

Report the count the shipped rule produces, and say plainly how many entries are
left in the source language and why. If the honest number makes the technique
look unprofitable, that is the finding — it is still the right thing to report,
and it is the user's call whether to buy the remaining coverage with a
synonym table.

Two consequences to plan for:

- The resolver needs a small lookup from the source-language category to the
  resource id, plus a fallback for a category with no key. Keep the fallback
  visible — it is what tells you the table has an uncovered entry.
- **Leaving the one-off suffixes in the source language is the right call**, and
  worth stating in the commit message: the map stays internally consistent (every
  entry with a shared suffix is translated in all locales, everything else is
  uniformly untranslated) instead of half-translated.

## The final audit pass: a residual count is a claim, not a backlog

When the literal scan reaches a small number, the temptation is to report it as
"what remains, by design". Resist it. Classify every residual literal by
destination (person / model / log / parser) and name the file, because **a
non-trivial share of "obviously fine" residuals is real UI you misjudged** — the
count is a hypothesis about your own work, and the only way to close it is to
read each one in context.

That pass on 519 residuals across 13 files found three genuine bugs, all of
which had passed every automated check:

- **A legacy `String` field left behind beside the new `@StringRes` one.** An
  enum had been converted to carry both `label: String` (Chinese) and
  `labelRes: Int`, with a `display(context)` helper added. The type compiled and
  the helper was correct — but two screens still read `it.label` directly, so a
  dialog rendered in the source language inside an otherwise localized card.
  Converting a label field is not done when the resolver compiles; it is done
  when **grep finds no reader of the old field**. Leave the old field only if
  something still needs it, and check that something is not UI.
- **A locale-specific separator hardcoded next to the joined values.**
  `joinToString("、")` — the CJK ideographic comma — stayed while the items it
  joined became localized. Correct for `zh-rCN`, wrong for every other locale.
  The general rule from the space-concatenation trap is the same one: **any
  separator between two localized values is itself a localized value.** Ship it
  as a key (`, ` for en/es, `、` for zh) rather than hardcoding the common case.
- **A progress callback on a branch the scan's earlier rounds had covered once.**
  A second `onProgress(...)` call in a sibling branch of the same function still
  held a literal. Same function, same commit, missed. When you touch a function,
  grep every literal in it rather than trusting your first inventory of it.

So the audit is not a formality before reporting: it is where the last real
defects are, because everything mechanically checkable has already been checked.
Report the classification *and* the fixes, not a reassuring summary of why the
remainder is acceptable.

## When a resource build fails with zero Kotlin errors, run aapt2 yourself

`mergeDebugResources` can fail with

```
Can not extract resource from com.android.aaptcompiler.ParsedResource@…,
Can not extract resource from com.android.aaptcompiler.ParsedResource@…
```

and **no `e:` lines anywhere**. The XML is well-formed, Kotlin is fine, and the
Gradle message names no file and no line — so `xml.etree` cannot help, because
the file parses. AAPT rejects on rules the XML spec does not have. Get the real
diagnostic by invoking the binary the build already downloaded:

```bash
aapt2=$(find ~/.gradle/caches -name aapt2 -path '*linux*' | head -1)
"$aapt2" compile --dir app/src/main/res -o /tmp/res.zip   # rc 0 = resources valid
```

It prints file and line for each fault. Run this **before** Gradle whenever you
appended resource entries by hand — it takes a second and it is the only tool
that answers the question the Gradle error poses.

What it catches that parsing does not:

| Fault | Why XML parsing accepts it |
|---|---|
| unescaped apostrophe | `<string name="x">', '</string>` is well-formed XML; Android requires `\'` |
| value starting with whitespace or a newline | legal XML, invalid resource; AAPT strips or rejects it |

On the apostrophe: **quoting the entire value is not a valid workaround.**
Wrapping a value in `"` preserves edge spaces but does not escape an interior
apostrophe, and it is a common wrong turn because the two AAPT rules are usually
learned together. Escape the apostrophes.

## One agent's crash can delete every other agent's keys

Resource files are edited by many agents at once, and a crash mid-`write` plus a
`git checkout --` restore leaves the file byte-identical to HEAD — which means
every key a *sibling* had already appended to it is gone, while their Kotlin
still references those keys. The symptom is a build that fails on missing
resources with no visible cause, and an agent report that says its own keys are
present.

Defend at write time (`tempfile.mkstemp` + `os.replace()`, never a truncating
`open(path, "w")`), and audit at recovery time with a whole-tree sweep:

```python
en = {e.get('name') for f in glob('app/src/main/res/values/*.xml')
              for e in ET.parse(f).getroot() if e.tag == 'string'}
missing = {k for f in glob('app/src/main/java/**/*.kt', recursive=True)
                  for k in re.findall(r'R\.string\.(\w+)', read(f)) if k not in en}
```

Include **every** string file in the locale, not just `strings.xml` — keys
living in a sibling resource file read as missing otherwise. Keys referenced as
`SharedR.string.x` come from the shared library module, so a naive sweep
reports them as broken; check the import qualifier before treating a hit as real.

## The lesson

Do not report a coverage number as evidence that an app is localized. It is
evidence about the resource files. To claim the app is localized you need a
source-level literal scan *and* the built-artifact locale check.

And when both gates are green and the artifact checks out, the remaining
unknown is behaviour only a person can observe: whether a `contentDescription`
is actually announced well, whether a key repeats when held, how a layout
survives a large font scale. Say that plainly rather than letting "verified"
stand in for it.
