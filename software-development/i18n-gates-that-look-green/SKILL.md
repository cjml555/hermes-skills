---
name: i18n-gates-that-look-green
description: Use when a gate reports zero but defects are known.
---

# A gate reporting 0 is a claim, not evidence

## The rule
A detector that says "0 findings" may be **measuring nothing**. This bit three times in one
session on the same repo, and each time the tool was confidently wrong:

1. A literal-detector filter for "short identifiers" discarded every string without spaces.
   Chinese has no spaces, so **every CJK literal was silently dropped** and the report said
   "0 Chinese remaining" while 51 were on screen.
2. The translation-coverage gate only checked `strings.xml` ↔ `strings.xml`. Hardcoded
   literals bypass it entirely, so it stayed green over 130 untranslated strings.
3. After fixing #1, the detectors were regexes over *call names* (`Text(`, `Toast.makeText(`,
   `setTitle(`). The most common Compose shape — a value assigned then passed on — matched
   none of them: `val name = "FTP 服务"`. The gate said 0 while one file held 979 UI strings
   in Chinese.

## How to check a gate before trusting it
**Inject a real defect and confirm the gate goes red.** This is the only reliable test.
Re-add the literal you removed; if the gate stays green, the gate is the defect.
A gate that has never failed has not been tested.

Also run it **green and red in the same session, against the same tree**, when a check
you wrote is the thing under suspicion. Confirming it catches an injected defect while
never seeing it pass is half a test.

A subtler variant of "green for the wrong reason": a check whose expected baseline is
committed in the repo will keep passing if the code moves but the baseline file is
updated in the same commit. When a count rises, the only legitimate responses are
translating the new text or fixing the detection — not raising the baseline to make
the number fit. That makes the gate a ratchet, and a ratchet that you adjust yourself
stops being a gate.

## Prefer invariant detectors over pattern lists
Pattern-matching *call names* only covers the shapes you already saw. Prefer an **invariant**
that cannot have blind spots — e.g. "any string literal containing CJK is translatable text"
beats "literals passed to `Text(...)`". Chinese/emoji never appear in identifiers, paths,
MIME types, or commands, so that invariant is sound and needs no maintenance as code evolves.
Always include negative controls (paths, `pm install`, class names) and confirm they are NOT
flagged, or you have just built a detector nobody will trust.

## Report the real number, and its provenance
When a gate's scope is narrower than the problem, say so explicitly and quantify the gap
("979 in this file, 2124 across 43"). A scoped-down zero presented as a project-wide zero is
worse than no measurement.

## Adjacent failure mode
"Bulk-translated N strings with a model and the gate validated it" is not verification.
Coverage gates check that a key *exists* in each locale, not that the translation is *correct*
— nothing catches a mistranslation. Bulk work needs spot-checking by a reader, and
safety-critical text (warnings, destructive-action prompts) needs individual review.

## Reproduce a gate in the mode CI actually runs

A tool can expose several modes behind different flags, and the mode decides what a
non-zero exit means. A regression gate (fail only when the count *rises* above a
committed baseline) and a zero-tolerance gate are different instruments wearing the
same name. Running the wrong one and reporting its failure trains the reader to ignore
you — the run really was red, for a question nobody asked.

Read the CI workflow file to see which flag it passes, and reproduce that exact
invocation. Confirm the exit code separately from the pipeline: `cmd >/dev/null 2>&1;
echo $?` — the status of a `| tail` or `| grep` pipeline is the *last* command's, not the
gate's.

## A coverage gate cannot see which language a value is in

Coverage checks presence and placeholders. It cannot see that a value written for one
locale landed in another. Writing a batch of N locales from one
`(en, es, zh)` tuple with an off-by-one in the index — or a comprehension that unpacks
the wrong tuple length and dies mid-loop — puts Chinese text into the Spanish file and
leaves the earlier locales correct. Every key is present, every placeholder matches,
`check_translations --gate` returns 0.

Sweep each *non-target* locale for source-script characters after any multi-locale
write, and assert the expected per-locale key count. Report the count per file: a bare
"2083 CJK found" is unreadable until you know which file. Note that a comprehension
raising halfway leaves earlier locales written and later ones untouched, so the sweep is
the only thing that catches it.

## A green compiler is not a green runtime path

Changing a value from a hardcoded string to a resource lookup only fails where the code
*runs*, so `compileDebugKotlin` passing means nothing about it. In a JVM unit test
`android.jar` is stubbed and `Context.getString` throws `"not mocked"`; if that call sits
inside a `launch` / `Handler.post`, the throw is swallowed and the observable effect is
that nothing ever happens. A test that polls for an async condition then reports a
**timeout** and never names the cause, which reads like flakiness rather than a defect.

Run the test suite, not just the compiler, whenever a batch changes a value read at
runtime — enum labels, permission names, any error string routed through a coroutine.
Prefer making the resolver fall back to a plain default over reverting the translation:
that is also the production behaviour you want when resource resolution fails inside a
security or confirmation flow.

## Sibling pattern beyond i18n
Same shape appeared twice in shell tooling: `grep -q` + `pipefail` returning 141 (SIGPIPE)
made an installed app look absent, and `deploy.sh` printing `installerPackageName=null` after
an arrow where the signature was expected — a correct decision made on the wrong datum. Both
were "the check appeared to work." When a check's output feeds a decision, confirm the value
means what the label claims.

## Kotlin/Android mechanics

Enum labels cannot be `stringResource`, `Context` has to be threaded into
string-returning helpers, and `plugin/` files carry a BOM that silently defeats
`^`-anchored patches — see `references/android-resource-lookup-pitfalls.md`.
