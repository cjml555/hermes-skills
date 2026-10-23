---
name: codebase-bug-audit
description: "Audit a codebase for bugs; verify before reporting."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, bug-hunting, security, audit, static-analysis]
    related_skills: [requesting-code-review, systematic-debugging, android-build-troubleshooting]
---

# Codebase Bug Audit

Scope: finding real defects in a codebase you did not write, and fixing them so
each change is proven. Not for reviewing your own pending diff — use
`requesting-code-review` for that (it is diff-scoped and pre-commit).

## When to Use

- User asks to "check the repo", "find bugs", "audit", "review the code", or
  "verify this is bug-free" — as opposed to reviewing a diff you just wrote.
- A codebase is too large to read in one pass and needs triaging into real
  bugs, false positives, and by-design behaviour.
- Security-relevant sweeps: injection sinks, exported components, permission
  checks, hardcoded credentials, data-loss scripts.

Skip for: reviewing your own uncommitted changes (that is
`requesting-code-review`), or a single known failure with a stack trace (that is
`systematic-debugging`).

## Always-on rules

- **Verify every finding before you report it, however it was found.** Grep hits,
  subagent output, and your own recollection are all hypotheses. Check the actual
  type of the value, the actual `.gitignore`, the actual call site. Reporting an
  unverified finding costs more credibility than the bug was worth, and the user
  will act on it.
- **A grep hit on a dangerous API is not a bug.** `exec("sh","-c","kill $pid")`
  is not injection if `$pid` is an `Int`. Trace the value's type and origin back
  to the UI or config before calling it exploitable. Expect a large false-positive
  rate and pre-filter with type checks, not with intuition.
- **Reproduce the bug before fixing it, and show the "before" number.** Run the
  destructive command against a throwaway copy and quote what it did (1406 lines
  → 4). A fix you cannot demonstrate was previously broken is a fix you cannot
  claim works.
- **Any test harness needs a positive control.** Run the unescaped input first
  and confirm it DOES exploit; only then does the escaped run's survival prove
  anything. A harness where the control also "passes" is testing nothing — that
  failure mode burns several attempts silently because the output looks clean.
- **A green mock run proves branches are reachable, not that behaviour is right.**
  A stub of an external tool emits a couple of lines where the real thing emits
  thousands, so volume-dependent bugs stay invisible: a mock-driven run of a
  whole deploy flow was clean, and the first run against real hardware reported
  a package it had installed as absent. Before trusting a mock-green result on
  anything destructive, re-run it against the real system. When the real system
  contradicts the mock, suspect the mock's fidelity before editing the code.
- **Verify in batches, then commit each batch.** Compile/build after each
  logical group of fixes, commit, move on. One commit for twelve unrelated fixes
  is unreviewable and unrevertable.
- **Fix your own regressions in the batch that caught them, and say so.** A
  defect you introduce mid-audit is a finding like any other: name it, fix it,
  keep the evidence, do not quietly re-run until the failure disappears.
- **When the user answers "do your recommendation", commit to one path and
  carry it through.** They have delegated the choice; a follow-up question
  re-opens a decision they already handed over. Present the recommendation,
  act, and flag only what genuinely cannot proceed without them.
- **A user eyeballing the output finds what your tooling called clean — treat
  that as a gate defect, not a nitpick.** When someone reports a specific
  broken string your check passed, the fix has two parts: repair the instances
  *and* extend the check to that class. Patch only the symptom and the same
  report arrives again next round.
- **A verification script is itself a test, and can be wrong.** When you assert
  an outcome from a small program, confirm it measures the thing you mean before
  believing its verdict. During one session a check comparing two install
  timestamps printed "REINSTALLED (data lost)" when the values showed a clean
  update, because an update leaves the first-install timestamp fixed and moves
  only the last-update one — the two had to be compared against each other, not
  for equality. Run the check against a case whose answer you already know
  before trusting it on the case you are unsure about.
- **Gate the gate.** A CI check that can exit 0 while auditing nothing is worse
  than no check, because it looks like protection. After fixing one, run it with
  deliberately wrong input and confirm it goes red.
- **Parameterize a hardcoded path while you are already in the file.** An
  absolute path baked into a script is both a portability bug and a config that
  cannot be tested; fix it in the same batch as the logic bugs rather than
  leaving it for later.
- **Do not use blind search-and-replace across a file.** A scripted replace that
  matches 15 sites will happily hit a site in a different function where the
  variable does not exist. Scope the replacement, then compile immediately.
- **Expect to introduce bugs while fixing bugs.** After every scripted edit,
  re-read the changed region and compile. The most common self-inflicted defects
  are a dropped string separator, an over-indented block, and a replacement
  that leaked across function scope.
- **A subagent's broken code is your broken code, and its edit needs the same
  post-edit check.** Delegated bulk rewrites fail the same way scripted edits
  do, and they fail it more often: a literal-to-`stringResource` conversion
  across a multi-line `listOf(` dropped every separator, so Kotlin silently read
  each line as a chained call on the previous result (`Cannot infer type for 'T'`
  + `Unresolved reference 'stringResource' on receiver of type 'String'`).
  A subagent reporting `BUILD SUCCESSFUL` on a tree that does not compile means
  its verification never ran. Compile the merged tree yourself before committing,
  and read the diff of a scripted bulk edit rather than trusting the count.
- **Read back every explanatory comment and commit message you write.** Long
  prose in a file whose surrounding language differs from yours is the single
  most frequent self-inflicted corruption: stray tokens, a half-translated word,
  or two languages spliced mid-sentence (`un script`, `allowía`, `partly`,
  `Now hay`, a Chinese clause inside a Spanish sentence). It compiles fine and
  ships fine, so nothing but a re-read catches it. After writing a comment, read
  the exact bytes back and check for mixed-script words before moving on; run
  the same check on `git commit -m` text, which nobody re-reads at all.
- **One instance means a class — go find the rest before reporting.** When you find a defect a grep cannot see (a broken escape welded to a word, a hardcoded absolute path, a permission check with no call sites), treat the first hit as a detector rather than the finding, and sweep for the pattern before writing it up. A single user-reported instance here was one of five, and none of the five was visible to the tool that had been reporting green. Sweep first, then report the count — the user gets one fix instead of one symptom at a time.
- **When the user reports something your tooling called fine, the defect is in the tooling.** Their manual pass found a string the coverage gate had been green on indefinitely. Re-read your own check and ask what class of breakage it structurally cannot see, then add that class. Do not patch the single symptom and do not defend the green result.

## Procedure

1. **Size the surface before reading.** Count lines by language and list the
   largest files. A 130k-LOC repo cannot be read line by line, and the audit
   budget goes to your own code first (see step 2).
2. **Separate vendored/upstream code from code under change.** For a fork, the
   diff against the upstream base commit is where your bugs live. Auditing the
   vendored tree wastes the whole budget. `git log --reverse` shows where the
   fork's own commits start.
3. **Sweep for the dangerous-API classes with a text search first**, to find hot
   spots rather than to conclude findings: shell/exec sinks, WebView + JS
   bridges, file-path joins, `startsWith` path containment, SQL string building,
   HTTP cleartext, crypto/TLS overrides, exported manifest components.
4. **Fan out readers by subsystem, not by file count.** Give each subagent a
   subsystem and the specific bug classes to look for. Subagent findings are
   leads, never conclusions — re-verify each one yourself (see always-on rules).
   Expect some fan-out members to die mid-run (rate limit, provider error); when
   one does, do that scope yourself inline rather than re-dispatching, since a
   re-dispatch hits the same limit. If the fan-out cannot cover the repo, audit
   the highest-risk subsystem yourself rather than reporting unverified subagent
   output as fact.
5. **Triage into: confirmed / false positive / by-design.** Say explicitly which
   is which, and name the ones you deliberately left alone with the reason. A
   finding you investigated and cleared is a result worth reporting.
6. **Rank by impact, fix by risk cluster.** Data-loss and injection first, then
   exported surfaces and hardcoded credentials, then false-success and resource
   leaks. Group related bugs in one file into one commit.
7. **Fix each cluster with its own verification.** Reuse the reproduction from
   step 3 as the regression check, and prove the "after" state.
8. **Re-run the full build and any existing gates** before the final commit.

## Reporting

Give the user: findings ranked by severity with `file:line`, which you verified
yourself and which came from a subagent, what you changed with the evidence for
each, and an explicit list of what you did NOT fix and why. Call out any finding
that requires a decision only they can make (rotating a leaked key, changing a
product default) instead of quietly treating it as done.

When the user then asks you to explain one of the unfixed findings, trace its full
call chain and report the explanation as a result — the grant call, the bypassing
caller, and the caller that does it correctly for contrast. State the author's
rationale even when you think the behaviour is wrong: a skipped consent dialog
that saves a deliberate click is a defensible friction tradeoff, and saying so
makes the recommendation credible instead of reflexive. Close with a concrete
offer to change it and one question, then stop — an explanation request is not
authorisation to edit, and fixing it unasked spends trust on the one change most
likely to be rejected.

## Pitfalls

- **A subagent's "verified" claim is a self-report.** Re-run its own check before
  it becomes your finding. During one audit a subagent reported a leaked local
  config file that was in fact correctly gitignored; reporting it unverified
  would have sent the user chasing a non-issue.
- **An `exported="true"` component is not automatically a bug.** Check for an
  `intent-filter` and its purpose first: a share-target receiver is exported on
  purpose, and un-exporting it breaks the feature it exists for. The
  same-shaped finding with no filter and no external caller is the real bug.
- **Removing something from version control does not un-expose it.** Deleting a
  committed key from `build.gradle` leaves it in git history. The mechanical move
  to secrets is worth doing, but say plainly that rotation is a separate human
  decision, and do not let the diff imply the exposure is closed.
- **When the user accepts a security finding as a deliberate tradeoff, write the
  decision down instead of leaving your warning comment standing.** Once they say
  "this stays, it's an open-source project", the exposure is a decision, not a
  pending bug — but the code comment you wrote earlier still reads like an
  oversight and will get "fixed" by the next person. Correct that comment to
  state the tradeoff and its threat model, and add a doc page covering: what the
  exposure does and does not permit, the real cost of fixing it, and the
  alternative that removes the need for a secret at all (reproducible builds for
  a public signing key). Give the concrete rotation steps for the day it is
  needed, including the cost that stops them today — here, that installed apps
  signed with the old key cannot be updated, only reinstalled.
- **Do not add `set -e` reflexively to a script whose greps are expected to
  fail.** A `grep` with no matches exits 1 and that is a valid answer, not an
  error. Make the load-bearing checks explicit instead.
- **`grep -q` in a `set -o pipefail` pipeline returns 141 (SIGPIPE), not 0, when
  it finds a match**, so every `if cmd | grep -q` guard reads "not found" for
  something that IS there. Invisible until the input is large enough for the
  producer to lose the race — a stub does not reproduce it. See
  `references/hardening-and-scripts.md`.
- **Python's `rpartition` returns `(head, SEPARATOR, tail)` — the separator is
  the MIDDLE element.** Writing `head + tail` silently drops the delimiter, so
  splicing a template back together loses its closing tag.
- **Hardening one control can raise the risk of a path you left unfixed.** After
  you tighten a gate, re-check the findings you deliberately did not fix: the one
  you waved through as \"product decision\" may have been merely bad before your
  change and become exploitable after it. A filter that stops being bypassed by a
  root permission makes a second code path that grants that permission silently
  a much bigger problem than it was during triage. When you report such a finding,
  say explicitly that your own earlier fix changed its weight.
- **A sub-process stream closed without `finally`, and a `Process` never
  destroyed, leak on every exception path.** When a screen polls a command on an
  interval this accumulates; consolidate into one helper rather than patching
  each call site.
- **A discarded result object makes a function always report success.**
  `executeShellCommand(...)` followed by a literal `true` shows the user "ok"
  when the command failed or was denied. Propagate `.isSuccess`.
- **A grant function that hands out permissions from untrusted input needs its
  own gate, and the gate must read the project's existing risk table.**
  Installing an artifact and immediately calling `enablePlugin` means whatever
  the artifact's own manifest declares is granted verbatim — including
  `ROOT_EXECUTE`. When the artifact is machine-generated (an LLM wrote that
  manifest, so its permission list may be hallucinated) this is the highest-
  severity path in the system, and a comment explaining the shortcut is not a
  control. Gate on the risk map the project already ships rather than a list you
  invent: reusing `permissionRiskMap` means a permission the project considers
  low stays low, and only its HIGH tier interrupts. Reuse the existing consent
  dialog too — a permissions screen already exists in the admin surface, and
  the fast path is the only thing that needs a new branch.
- **A fast path that skips a gate needs a compensating control on the
  artifact side.** The legitimate version of the shortcut above is: no
  distribution channel, the user asked for it, and low-risk permissions only.
  Say explicitly what makes it legitimate rather than only removing the
  shortcut.
- **Cursor-style incremental reads break against a capped buffer.** When the
  underlying transcript is truncated at a row limit and the read offset is
  absolute, the offset ends up past the end and the function returns empty
  forever. Detect the truncation and re-anchor.

## References

- `references/finding-verification.md` — commands and reasoning for confirming
  or clearing a candidate before it becomes a reported finding.
- `references/hardening-and-scripts.md` — fix recipes for the recurring classes:
  shell-escaping user paths, false-success returns, incremental reads against
  capped buffers, weak command filters, and testing a script that drives a
  device or daemon.