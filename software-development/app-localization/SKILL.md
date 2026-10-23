---
name: app-localization
description: Use when translating app UI strings and docs to a locale.
license: MIT
metadata:
  version: "1.0.0"
  category: software-development
---

# App Localization

Scope: shipping a complete non-English locale for an existing codebase — Android string resources, docs site, READMEs. Not for building/translation software.

## Always-on rules

- Before translating a file that may already have a translation, check for it. A request to "translate the README" often means an existing one is stale, not that the file is missing. Compare structure parity (line count, heading count, fence count, table rows) and confirm no source-script characters leak outside code blocks before deciding to redo any work.
- Confirm locale and register with the user before dispatching: neutral Latin American Spanish, `tú` (no voseo) unless told otherwise. One answer covers every file.
- Never edit the base-language resource files. Translation goes into new locale directories/files only.
- Fan out with `delegate_task` — one subagent per chunk — rather than translating inline. A 1400-entry string file plus 5 docs is 10 parallel units; inline it overflows context and loses the validation pass.
- The parent owns merge + validation. Subagents only write their own output file and report a count. Never trust a subagent's "verified" claim: re-run the checks in `scripts/verify_locale.py`.
- A green build is NOT proof the locale shipped. `resConfigs` strips locales at packaging time, so a wrong locale dir merges cleanly, builds cleanly, and never reaches the device. Always run `scripts/verify_apk_locale.py` against the built artifact before telling the user the translation works.
- **A 100% coverage number only proves the keys in the resource files are translated — it says nothing about text that never became a key.** UI strings written as literals in code (`Text("…")`, `Toast.makeText(ctx, "…")`, `AlertDialog(title = "…")`, a `data class` whose property is display text) bypass every locale and every coverage tool, because the string was never in `strings.xml` to begin with. A fully-green gate and a screen that renders in the wrong language are the same state. See `references/ui-literals-gate.md`, which also covers the failure classes a gate cannot see: entity tails welded to a word, `\uXXXX` Android renders literally, and untranslated values that read as identical-to-English.
- **A placeholder checker must not treat prose percentages as format specs.** `%` followed by a space and a letter (`100% of`, `100 % del`) is read by a naive `%\w` regex as a spec (`% o`, `% d`), so the gate demands a matching spec in the translation and reports divergence where there is none. A real specifier cannot contain a space between its flags and its conversion letter — reject specs containing whitespace, and reject a spec whose `%` is itself preceded by `%`.
- **Only extract literals the user can actually see.** A screen with 31 inline strings and zero `Log` calls is pure UI; the same count mixed into logging is not a translation backlog. Classify each site by whether it renders, and exclude logs, tests, and third-party/upstream trees — re-merging those rewrites the fork on every update.
- **A coverage gate proves nothing about strings that were never made keys.** It counts what is in `strings.xml`; a screen rendering hardcoded `Text("…")` is invisible to it. When auditing an existing locale and the user reports screens in the wrong language, check for a detector that scans source for literals before reporting the locale as complete. The gate needs to exist, and it needs to exclude logs/tests/vendored or its hit count is noise.
- **Adding a detector is separate from fixing what it found.** Ship the detector in its own commit, leave it in report-only mode while the backlog exists, and only turn it into a blocking `--gate` once the count reaches zero — otherwise it fails CI on the very backlog it was written to surface.
- **A coverage gate and a literal gate measure disjoint sets; both green is still not a localized app.** Wiring only the first into CI is the default state of most projects and it cannot catch a screen rendered in the wrong language. When a literal gate is added to CI, extend the workflow's `paths:` trigger to include the source files it scans — a trigger listing only the resource XML never fires on a code change, and the gate looks present while being dead weight.
- **Report what the tooling did not cover.** A green pair of gates plus a verification of the installed artifact is a claim about files and one build. Behaviour that only a person can observe — a screen read aloud by TalkBack, key-repeat behaviour, a layout at a font scale — is unverified no matter how many gates passed. Name it as the remaining check instead of letting "verified" imply more than was tested.
- **Measure a lookup table before keying one entry per row, and measure with the boundary rule you will ship.** A literal count says nothing about the real key count for generated tables. Split values into `PREFIX@@category@@`, count how many entries share each suffix, and key only the suffixes used more than once — one-offs do not pay for a key. Leaving those in the source language keeps the table internally consistent instead of half-translated, and saying so in the commit message makes it a decision rather than an omission. Only split where the source script **actually separates tokens** (a real space): in a script without word spaces, "ends with a known suffix" matches mid-word and yields plausible-looking nonsense. Print ten converted pairs and read them as sentences before writing hundreds of edits, and quote the count your shipped rule produces. See `references/ui-literals-gate.md`.
- **Present the cost of the remaining coverage instead of silently choosing for the user.** When a measurement says most entries cannot be compressed (compound terms, one-off suffixes), stop and lay out the options with real numbers — key everything, key the frequent subset, or stop and ship the consistent partial — because "all translated" and "translated where it pays" are different products and the tradeoff is the user's, not a default to assume.
- **Never add a `Context` parameter to a non-`@Composable` object to reach `getString`.** If the object already resolves a context anywhere, add a `str(@StringRes, vararg args)` helper beside it and change zero signatures. A new parameter named `context` shadows every existing `context.getString(...)` in that function and breaks the build in 30+ unrelated places, while also forcing edits to call sites you do not own. `vararg args: Any` also rejects `String?` — write `str(res, e.message ?: "")`.
- **Never copy a resource value out of the source string you just replaced.** The Kotlin original carries `${...}` interpolation, so the resource ends up with zero placeholders while the call site still passes arguments: green build, green gate, `MissingFormatArgumentException` on screen. Hand-write `%1$s`/`%2$d` per locale and diff placeholder *sets* across all three locales for every new key — a placeholder divergence is a hard failure, never a warning.
- **After extraction, re-point logic that compared the old literal.** `startsWith("(")`, `contains(...)` and regexes written against a now-translated string stop matching in every locale but the source one, producing wrong counts rather than crashes. Match on the resource key instead, then grep for the old literal's ASCII fragments to find the ones you missed. Any separator between two localized values is itself a localized value — ship `joinToString("、")` as a key.
- **Do not ship pre-formatted display text across a producer/consumer boundary.** A `data class` property, `emit(...)` argument or `StateFlow<T>` that holds a finished `String` freezes the locale at the producer. Carry the raw data (numbers, ids, flags) and let the consumer format it.
- **Classify every remaining literal by destination before queueing it: person, model, log, or parser.** System prompts (including `echo`-adjacent heredocs), `Log.*` calls, and protocol identifiers the code matches on (`TASK_ADD`, `command`) are legitimately untranslated and translating them either changes model behaviour or breaks matching. A shell `echo` whose output flows back into a UI card *is* user-facing — classify by where the string lands, not by how it looks.
- **Never let fan-out subagents run Gradle while siblings build.** Concurrent Gradle runs corrupt the shared KSP/incremental cache and yield `StreamCorruptedException: unexpected EOF` with zero Kotlin errors, which agents read as their own breakage and start "fixing" working code. Brief them to verify statically instead, and build once alone at the end with `--no-build-cache`.
- **Audit the residuals by reading them; a small remaining count is not a clean bill of health.** When the scan gets low, the pull is to summarize why the remainder "is all prompts/logs". That summary is usually wrong in a specific way: a `String` label field left beside the new `@StringRes` one and still read by another screen, a locale-specific separator left next to now-localized items, or a second literal in a branch of a function you already fixed. Converting a label field is finished when grep finds no reader of the old one. Everything mechanically checkable is already checked by this point, so the manual read is where the last real defects are. See `references/ui-literals-gate.md`.
- **Run aapt2 directly when resources fail with zero Kotlin errors.** `Can not extract resource from ParsedResource@…` with no `e:` lines means the XML parses but AAPT rejects it — usually an unescaped apostrophe or a value starting with whitespace. ElementTree cannot see it; `aapt2 compile --dir app/src/main/res` reports file and line in a second. Quoting a whole value is not a valid workaround for the apostrophe.
- **One agent restoring a resource file with `git checkout` deletes its siblings' keys.** A crash mid-`write` leaves the file at HEAD, so every key appended by another agent is gone while their Kotlin still references it. Write resource files via `tempfile.mkstemp` + `os.replace()`, and after any restore sweep the whole tree for `R.string.X` names absent from every string file in the locale (include sibling resource files, and skip `SharedR.string.x`, which comes from another module).
- **Audit the residuals by reading them; a small remaining count is not a clean bill of health.** When the scan gets low, the pull is to summarize why the remainder "is all prompts/logs". That summary is usually wrong in a specific way: a `String` label field left beside the new `@StringRes` one, a locale-specific separator (`joinToString("、")`) left next to now-localized items, or a second literal in a branch of a function you already fixed. Converting a label field is finished when grep finds no reader of the old one; any separator between two localized values is itself a localized value. Everything mechanically checkable is already checked by this point, so the manual read is where the last real defects are. See `references/ui-literals-gate.md`.
- **Run aapt2 directly when resources fail with zero Kotlin errors.** `Can not extract resource from ParsedResource@…` with no `e:` lines means the XML parses but AAPT rejects it — usually an unescaped apostrophe or a value starting with whitespace. ElementTree cannot see it; `aapt2 compile --dir app/src/main/res` reports file and line in a second. Quoting a whole value is not a valid workaround for the apostrophe.
- **One agent restoring a resource file with `git checkout` deletes its siblings' keys.** A crash mid-`write` leaves the file at HEAD, so every key appended by another agent is gone while their Kotlin still references it. Write resource files via `tempfile.mkstemp` + `os.replace()`, and after any restore sweep the whole tree for `R.string.X` names absent from every string file in the locale (include sibling resource files, and skip `SharedR.string.x`, which comes from another module).

- **A locale that packages is not a locale that renders.** After the artifact check, switch the device and read the screen: `adb shell cmd locale set-app-locales <pkg> --locales <loc>`, `am force-stop <pkg>`, relaunch, then `uiautomator dump` and confirm the `text=` values come back in the target language. A wrong directory, a `resConfigs` filter and a base-language fallback are indistinguishable in a green build. The per-app locale stays pinned on the device — reset it with `--reset` or tell the user you left it set.
- **The base resource file must be pure base language; normalizing stray target-language values back is part of the job.** "Never edit the base file" protects translations from being overwritten — it does not license a default `values/` that still holds Spanish or Portuguese leftovers. Those values render in the wrong language in every locale that lacks an override, and they make the default look already-translated. Fixing them is a deliberate base-file edit: do it, and say so in the commit.
- **An in-app language selector is a separate deliverable from the locale files, and it can destroy runtime state.** Adding `values-es` changes what the app *can* render; a selector changes the Activity lifecycle. Read `references/android-language-selector.md` first — the two failure modes are a system-initiated Activity recreate that drops loaded native models, and a UI rebuild that loses the current tab.
- **Canvas-drawn controls publish nothing to the accessibility tree.** A custom `View` that draws its labels in `onDraw` yields no `text=` nodes for that region: the control is present and every gate is green while `uiautomator dump` shows nothing. Verify placement and state with a screenshot, and never read a missing node as "did not render".
- **Key a selected label's colour to the thumb, not to the brand colour.** Reusing `primary` for text on a `primary`-coloured thumb makes the active option unreadable in dark theme, with a green build and no runtime error. Pick the foreground from the thumb's luminance instead.
- **A segmented control that claims the touch on ACTION_DOWN traps page scrolling and can switch the language mid-scroll.** Calling `requestDisallowInterceptTouchEvent(true)` on DOWN stops the parent ScrollView, so dragging the settings page from anywhere on the switch does not scroll; a slightly diagonal swipe also slides the thumb into the next segment and silently changes the locale (the language you were testing flips back and looks like a persisted-preference bug). Claim the gesture only once `|dx| > |dy| + touchSlop`, and on `ACTION_CANCEL` restore the real index instead of snapping to wherever the finger stopped.

## Procedure

1. Inventory: list `res/values*/` and every `<string>` per file; list docs dirs and `.md` files. Note existing locales — an existing `values-zh-rCN` is your format template. Check whether a translation already exists for each target file before queueing it for translation.
2. Split the big file by element, not by line: regex `<string name="...">.*?</string>` (DOTALL) and emit one entry per line into `$SCRATCH/tr/strings_N.xml`. Chunks of ~230 entries translate well in a single subagent turn.
3. Dispatch one subagent per chunk with the same rule block: translate only visible text; keep `name=`, placeholders (`%1$s`, `%d`, `%1$.1f`, `%%`), `\n` and `\'` literal; do NOT translate commands, paths, package names, setting keys, XML tags, author handles; escape `&` as `&amp;`. One output file each.
4. Dispatch docs separately from strings — a doc file is its own unit, and README is its own unit again (never a partial README).
5. Normalize every chunk's shape before merging. A chunk is a FRAGMENT (bare `<string>` elements, no wrapper); some subagents return a whole file with `<resources>` already attached, and concatenating those adds a second wrapper that fails the merger with `Can't determine type for tag`. Assert `text.count('<resources>') == 0` on each fragment, and strip a wrapper if present.
6. Merge: header + all chunks + `</resources>`, write to `res/values-es/` (or the requested locale dir). Copy over any sibling string file that also holds UI text (e.g. `avnc_strings.xml`).
7. Parse each chunk individually with ElementTree BEFORE merging, then the merged file — a per-chunk parse pinpoints which unit to repair, a merged parse does not.
8. Run `scripts/verify_locale.py <base> <translated>`; fix every reported mismatch before replying.
9. Rebuild (see `android-build-troubleshooting`) — a malformed resource file only fails at `:app:processDebugResources`.
10. If `resConfigs` is present in the build script, check whether it already lists the new locale and add the full qualifier if not. Then prove the locale is in the artifact: `scripts/verify_apk_locale.py <apk> <locale> "<sample string>"`.
11. If the locale came with a docs site, wire the selector and check every generated link with `scripts/check_layout_links.py <docs_dir>` — see `references/docs-site-i18n.md`. For a selector inside the Android app itself, see `references/android-language-selector.md`.
12. Add per-locale Open Graph metadata (`og:locale` et al.) and in-page language cards on each landing page — see `references/docs-seo-per-locale.md`. Do NOT change `lang:` in `_config.yml`: it names the language served at `/`, which is the maintainer's call.
13. Pushing, reconciling an overlapping branch, or fixing commit authorship mid-task — see `references/git-history-and-verification.md`.

## Generating the locale file instead of hand-merging chunks

When the locale fits one agent (roughly under ~600 short entries), skip the
fan-out: accumulate translations in a `{key: translation}` dict, then regenerate
the locale file from the base with a regex pass — match
`<string name="([^"]+)">([^<]*)</string>`, look up the dict, fall back to the
base value for anything missing. Two wins over chunk-merging: re-running the
generator after new keys are added keeps the locale in sync with zero drift, and
the fragment-merge failure mode (double wrapper, truncated tail) cannot happen.
Before writing, diff the placeholder *sets* per key between base and translation
(`%(?:\d+\$)?[sd]|%%`) and refuse on any divergence. The fan-out rule above
targets 1000+ entry files where a single context overflows; below that one dict
is cheaper and safer.

## In-app language selector (Android)

Shipping `values-<loc>` only changes what the app *can* render. A selector that switches at runtime is a
different change with its own failure modes — full recipe in `references/android-language-selector.md`.
The short version:

1. Add `locale|layoutDirection` to the Activity's `android:configChanges`. Without it the system recreates
the Activity on a locale change and every native engine loaded at startup (LLM, diffusion model) dies.
2. `LocaleManager.applicationLocales` (API 33+) sets the per-app locale; below 33 fall back to
`resources.updateConfiguration` plus a manual rebuild. Keep the 33+ call in its own method so the
`LocaleManager` class is never resolved on older devices.
3. Rebuild the view tree from `onConfigurationChanged`, comparing `newConfig.locales` against the last one
you built with — rebuilding unconditionally wipes the chat on every rotation.
4. Seed the selector from the **effective** locale (`LocaleManager` on 33+, the stored preference below),
not only from the preference: a locale set through system Settings or `adb` is real but was never written
to your prefs, so the selector reports the wrong option.
5. Verify with the app **stopped**: `am force-stop <pkg>` → `cmd locale set-app-locales <pkg> --locales es` →
   launch → re-read `cmd locale get-app-locales <pkg>`. Setting the locale under a running process, or
   launching a process that was already alive, can leave the old value in place; re-check after launch
   instead of assuming it stuck. Then re-dump the tree and confirm the tab you were on survived the rebuild.

## Extracting literals from code into resources

Turning existing hardcoded UI text into localized resources is remediation, not
translation — see `references/ui-literals-gate.md` for detection and the order of
work. When you fan out one subagent per file group:

- **Give every subagent the full rule block inline**: base resource file holds
  the base language only, target locales match the existing ones, placeholders
  use positional `%1$s` with original order, interpolation is applied in code
  rather than left as `${…}` inside the resource, and paths/commands/package
  names/emoji are not translated.
- **Partition by file and say so explicitly**, including which paths another
  agent owns, so two agents do not both rewrite the same `strings.xml` region.
  Three agents editing one XML file concurrently is a merge conflict at best.
- **Anchor replacements on content, never on line numbers.** With N agents on
  one `.kt`, line numbers shift under you and a line-range replacement silently
  no-ops with no error. Recompute function spans from content (brace matching on
  the function name) and assert the expected replacement count before writing —
  a count of 0 means your anchors went stale, not that the work was unnecessary.
- **Tolerate fan-out deaths and finish that scope yourself.** Rate limits take
  out parallel agents mid-run; re-dispatching hits the same limit. A
  subagent's "keys referenced but missing from every XML" report is usually a
  snapshot of a race with a sibling — re-verify yourself after the batch instead
  of acting on it.
- **Re-run the detector after the batch.** The literal count must fall by
  exactly the number you fixed — a smaller drop means a subagent skipped a file,
  and it is cheaper to catch that than to discover it when the user complains.

## Backfilling a locale that already exists

Topping up a partially-translated locale is a different job from shipping a new one, and the audit number lies. Triage before dispatching anything — see `references/locale-backfill.md`.

- **A "missing" count is not a translation count.** Split the reported gaps: keys whose BASE value is already in the target language (they were written in the wrong file and only need copying) versus keys whose base value is in some third language (those need translating). On a real backfill this was 98 reported vs 48 actually needing translation. Dispatch only the second group.
- **Grep the whole locale dir before adding a key.** Coverage tools typically compare one file (`strings.xml`) against the default and never look at sibling files like `avnc_strings.xml`. A key reported missing may already be translated in a sibling, and adding it in the main file fails the build with `Duplicate resources`.
- **Proper nouns get `translatable="false"` in the base file, not a translation.** Language names, tool names and contributor handles are identical across locales. Note that audit scripts that count by `name` ignore the attribute and will keep listing them; that is expected, not a regression.
- **Preserve a bug in the source string rather than silently fixing it.** If the English says "Failed to enable" in a disable-only message, translate the English as written and note it in the commit message. Fixing it is a separate, user-visible decision.

## Pitfalls

- **A hardcoded tab/page index range silently drops the newest tab on every rebuild.** `if (restoreTab in 0..3)` enumerates the tabs that existed when it was written; add a fifth tab and switching theme or language from it bounces the user to the first page with no error. Grep `in 0..N` and `<= N` over tab indices whenever a screen is added, and re-test the rebuild path from the last tab.
- **A subagent truncates the final line of its chunk** (drops `</string>`), producing valid-looking text that breaks the whole file at merge time. Per-chunk parse, then repair.
- **Anchor replacement on the broken line is fragile.** Match on `repr(s[-120:])` of the tail, append the missing `</string>`, re-parse. Guessing at whitespace around a truncated tail wastes a loop.
- **Count parity is not content parity.** Verify `name=` list equality AND placeholder-sequence equality AND `\n` count — a dropped `%1$s` is a crash at runtime, not a diff nit.
- **Scan for leftover source-script characters** (`[\u4e00-\u9fff]` for CJK) after merge. If the base file itself has stray untranslated rows, they show up here and you must decide: translate them from the base or leave them.
- **Jekyll/docs frontmatter**: translate the YAML values, never the keys, and never the code fences — code blocks, CLI flags, routes and image paths stay verbatim.
- **`resConfigs` is a silent locale filter.** `resConfigs "en", "zh", "zh-rCN"` drops `values-es` at packaging: merge, compile and package all report success and the locale is simply absent from the APK. Match on the FULL qualifier — on AGP 9.x `"es"` covers `values-es` but nothing carries `values-es-rUS` automatically. See `references/resconfigs.md`.
- **A Jekyll site on GitHub Pages injects `baseurl` itself.** Since Jekyll 3.3 Pages sets `site.url`/`site.baseurl` to the repo name when they are undefined, so `relative_url` already emits `/<repo>/…`. Writing `baseurl:` by hand duplicates the prefix and 404s the entire site. Check the deployed site before adding one.
- **Non-index pages rarely carry a `permalink`.** Under `permalink: pretty` a file at `zh/manual.md` with no frontmatter permalink is served at `/zh/manual/`, not `/manual/`. Assuming a uniform prefix across locales silently breaks the language selector. Derive the real URL map from the files before generating hrefs.
- **Pages that skip Liquid have no `relative_url`.** A standalone `.html` in the docs tree is copied verbatim, so `{{ }}` renders as literal text. Use document-relative links (`../en/`) there; they survive both a subpath deploy and a later custom domain.
- **Coverage tooling is scoped to one file and will report keys that are already done.** Treat its output as a worklist to verify, not as truth. One missing-key report led to a `Duplicate resources` build failure because the key already existed in a sibling string file.
- **A permanent nonzero coverage count means the tool is wrong, not the translation.** When every locale reads "N missing" forever, the denominator or the scope is broken — read the tool before translating anything. Two recurring defects: it reads only `strings.xml` (missing the sibling files) and it counts `translatable="false"` keys by name. Fix the tool and the coverage goes to 100% with no new translations.
- **The correct denominator includes every string file in the locale.** Comparing `strings.xml` alone understates the total (1403 vs the real 1647 once `avnc_strings.xml`'s 244 keys are counted). A coverage percentage computed against a partial denominator is wrong even when it reads high.
- **Fix the audit tool's scope in BOTH directions.** Merging sibling files into the locale read without also merging them into the default turns every already-translated sibling key into a false "orphan". Patch both sides or you trade one wrong number for another.
- **After editing a gate, prove it still fails on real regressions.** Inject each failure class it claims to catch (desynced placeholder, broken XML, locale missing from `resConfigs`), confirm the exit code flips to 1, then restore. A gate that has been edited is unverified until you have watched it fail on purpose.
- **Repo URLs in READMEs may legitimately differ from `git remote`.** Before "fixing" a badge or doc link to match the remote, check whether the deployment lives on the other account — `curl -sI` both. A fork used for CI can have its Pages site on the upstream repo, and repointing the links breaks a working badge.
- **Parallel branches touching the same files: reconcile by file, not by merge.** When another branch overlaps your work, `git checkout <ref> -- <paths>` to take its files individually and keep your own version of contested ones. Decide per file which side is better and say so in the commit message; a blind merge of two divergent translations loses one of them.
- **Before deleting a branch you partially adopted, prove it is fully absorbed.** `git log main..origin/<branch>` still lists commits after a history rewrite (every SHA changed), so that output is not evidence. Compare content per file instead — `git diff --name-only main...origin/<branch>` then `git diff --quiet main:<f> origin/<branch>:<f>` — and expect the files you deliberately did NOT adopt to differ. Those are your kept version, not lost work.
- **Ask which target the user wants BEFORE re-translating an existing translation.** A "translate the README" request may refer to a translation that already exists and is stale, not a missing file. See the first always-on rule for the parity checks to run before redoing any work.
- **Site-level default language is a product decision, not a cleanup.** `lang:` in `_config.yml` names the language served at `/`. Changing it to make the site "more multilingual" makes the root announce the wrong locale to every crawler. Leave it and give the other locales in-page routes instead (selector plus descriptive cards on each landing page), then say who should own the default.
- **Inserting markup by "line after the first `# `" heading picks the wrong anchor.** Long docs have many `# ` headings; the first one is often a mid-document section. Anchor on a unique nearby string (a specific badge line) and re-read the surrounding context after inserting to confirm it landed where intended.
- **A "translate X" request may name a file that is already fully translated.** Verify first: check for an existing translation, compare structural parity, and confirm zero source-script characters leak outside code blocks. If it is complete, report that and audit it rather than queueing it for retranslation. A sibling file the request never named may still be untranslated — audit the whole set, not just the one named.
- **"Identical to English" is not the same as "untranslated".** Before changing such a value, ask whether the term is even the same word in the target language, and whether neighbouring translations already fixed a convention. Leaving "Script" alone is correct when the rest of the file uses "script" untranslated; forcing a literal translation creates inconsistency and can pick the wrong sense ("guion" means screenplay, not program). Auditing such values and reporting that none needed changing is a valid outcome — say so explicitly instead of padding the diff.

## Reporting

Report counts (entries per file, docs), that XML validated, and any base-language string you chose to leave as-is. Name the exact files written. For Android, state the verified locale list from the built APK; for a docs site, state the link-check result. A build that passed is not the claim — the artifact check is.