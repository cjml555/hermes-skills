---
name: android-kotlin-refactoring
description: Refactor Android Activities into managers and verify wiring
---

# Android/Kotlin Activity Refactoring

Extract monolithic Activities into dedicated manager classes (SessionManager, CommandScanner, FileManager). Each manager holds pure logic with its own data classes. Integration in Activity is via delegation. Write unit tests for each manager using JUnit4, handling nullable types correctly.

Covers the whole class of Android/Kotlin refactoring work: splitting Activities
and Pages, deduplicating helpers and constants, extracting pure logic into
testable objects, and the verification gates (compile, tests, APK, device) that
every change must clear before it is committed.

## When to Use

Use this skill when the task is to **restructure an existing Android app**,
not to build a new one:

- Splitting a monolithic `Activity` or `Page` into managers, stores or
  host-interface-backed classes.
- Removing duplicated logic (helpers, constants, `coerceIn` chains, copied
  handlers) that has drifted between files.
- Extracting pure logic out of a UI class so it can be covered by plain JVM
  tests (no Robolectric, no device).
- Characterizing existing behaviour **before** touching it, so a refactor can
  be proven behaviour-preserving.
- Verifying a change on a real device over ADB, or unblocking a CI run that
  fails for a non-obvious reason.

Do NOT use it for: adding a feature, fixing a runtime crash in unrelated
code, or rewriting the app in another framework — for a "can we add X?"
question, read `references/tech-evaluation.md` first.

## Steps
1. List Activity blocks (persistence, commands, I/O, error handling).
2. Create manager files with data classes and pure logic.
3. Replace Activity implementations with manager calls.
4. Verify the manager is actually wired (see "Verify an Extraction Is Wired" below) before moving on.
5. Compile: ./gradlew :app:compileDebugKotlin --no-daemon -q
6. Test: ./gradlew :app:testDebugUnitTest --no-daemon -q
7. Commit each manager separately.

## Patterns

### ThemeManager Integration
- Create ThemeManager(context, onThemeApplied)
- Expose themeMode/pal via delegated properties
- ThemeManager holds: themeMode, pal, applyThemeInPlace(), onConfigurationChanged()
- Activity delegates: loadThemeMode(chatPrefs()), setThemeMode(context, mode) from UI
- setThemeMode(context, mode): persists to **the same prefs file the loader reads** (`chatPrefs()` → `"ponko"`; writing to a second file such as `"ponko_prefs"` makes the mode reset on every restart), sets mode, then triggers the rebuild
- The manager's `onThemeApplied` callback is frequently left empty, so `setThemeMode` alone resolves the palette and leaves the old colours on screen until a restart: the Activity's `applyThemeMode` must call its own `applyThemeInPlace()` immediately after. One extra line turns a dead switch into a live one.

### CommandScanner Integration (Example)
- Create CommandScanner.kt with DrawHit/TagReq/TagHit data classes
- Extract regex parsing logic: scanDrawCommand(), scanTagCommand()
- Activity delegates: button clicks trigger CommandScanner methods
- Example command pattern: "그림그려 xxx" → DrawHit(width, height, prompt)

### FileManager Integration (Example)
- Create FileManager.kt with FileRead/PendingFile data classes
- Extract file I/O: readAllCapped(), copyCapped(), decodeChatImage()
- Activity delegates: file selections call FileManager methods
- Pattern: file input → FileManager.readAllCapped() → process content

### org.json Is a Stub in JVM Tests — Add the Real One to the Test Classpath

`android.jar` ships `org.json` as a **stub**: every method throws
`RuntimeException: Method put in org.json.JSONObject not mocked`. Any extracted
manager that persists JSON (model sets, presets, chat history) therefore cannot
be covered by a plain JVM test until the real implementation is on the test
classpath:

```kotlin
// app/build.gradle.kts — testImplementation only
testImplementation("org.json:json:20240303")
```

- The stub failure is `not mocked`, **not** a compile error — the test compiles
  and fails at runtime, which reads like a bug in the code under test.
- Verify the dependency did **not** leak into the shipped app:
  `./gradlew :app:dependencies --configuration debugRuntimeClasspath | grep org.json`
  must print nothing. `testImplementation` never reaches the APK, so the APK
  size and behaviour are unchanged.
- A `SharedPreferences` fake is still needed for a manager that reads prefs
  (`android.content.SharedPreferences` is also a stub). Implement the whole
  interface — it has more methods than it looks: `registerOnSharedPreference-
  ChangeListener` / `unregisterOnSharedPreferenceChangeListener` are abstract and
  the compiler names them only after the first pass.
- A `SharedPreferences.Editor` fake must apply edits on `apply()` and `commit()`;
  the store reads the value back immediately after writing, so a no-op editor
  makes "write then read" tests fail for the wrong reason.

### JUnit4 Nullable Handling
- assertNull(result) / assertNotNull(result) for null checks
- Compare nullable values: result?.prop == true/false (not result?.prop)
- assertTrue order: message first, boolean expression second

### ChatParams Integration (Example)
- Create ChatParams.kt with companion object constants (KEY_*, DEF_*)
- Constructor takes `context` + `modelPathProvider: () -> String?` lambda (not direct Activity reference)
- Prefs scoped by model name: key(base) = "base" or "base#ModelName.gguf"
- Expose: ctx(), maxOut(), temp(), topK(), topP(), repPenalty(), budget(), seed(), thinkCheck()
- Derived: inputTokenBudget(), maxFileTokens(), thinkBudgetOrUnlimited()
- dirty flag: set true when params change for the loaded model (needs conversation rebuild)
- uiLoading flag: set true during programmatic UI updates (blocks saveChatParams)
- markModelLoaded(path)/markModelUnloaded() to track loaded model for dirty checks
- Activity delegates: saveChatParams() → chatParams.save(...), loadChatParamsIntoUi() → chatParams setters + getters
- resetChatParams() → chatParams.resetDefaults() then loadChatParamsIntoUi()

### Lambda Provider Pattern
- When manager needs current Activity state, pass `() -> T?` lambda at construction
- Avoids circular dependency (Activity ↔ manager)
- Manager calls lambda when needed: `modelPathProvider()?.let { ... }`
- Instantiate in Activity field: `private val chatParams = ChatParams(this) { modelPath }`
- Lambda captures `this` implicitly — no memory leak risk (same lifecycle)
- Use for any Activity field the manager needs: modelPath, current conversation, selected tab

### Manager-Controlled UI Flags
- Flags like uiLoading and dirty belong INSIDE the manager, not in Activity
- Manager exposes: setUiLoading(v), setDirty(v), isUiLoading, isDirty
- Activity no longer has `private var chatUiLoading` or `private var chatParamsDirty`
- LoadUI functions call `chatParams.setUiLoading(true/false)` around setText() calls
- saveChatParams() checks `if (chatParams.uiLoading) return` instead of Activity field
- markModelLoaded(path) / markModelUnloaded() called in toggleLoad/unloadModel

### CI/CD: GitHub Actions Build Pipeline

The Android project uses GitHub Actions for CI/CD. Key workflows:
- `.github/workflows/ci.yml` — Debug build + unit tests on every push/PR
- `.github/workflows/beta.yml` — Release APK + AAB on `beta*` tags
- `.github/workflows/release.yml` — Production release on `v*` tags

### GitHub Actions Version Pitfall

**Never guess which action versions are current — query the registry.** The GitHub API reports `actions/checkout@v7.0.1`, `actions/setup-java@v6.1.0`, `actions/upload-artifact@v7.0.2` and `softprops/action-gh-release@v3.0.3` as current. `@v4` is NOT the latest for checkout/setup-java/upload-artifact. A prior "fix" commit downgraded working `@v7`/`@v6` refs to `@v4` believing the newer tags did not exist; that made the workflows older, not safer.

Verify each `uses:` against the registry before editing:
```
curl -s https://api.github.com/repos/actions/checkout/releases/latest | grep tag_name
curl -s "https://api.github.com/repos/actions/checkout/tags?per_page=5" | grep name
```
Repeat for `actions/setup-java`, `actions/upload-artifact`, and any other `owner/action`. Pin the major the registry reports (`@v7`, `@v6`), not a guessed number.

**Impact:** A 404 at `Checkout repository` means the ref does not exist. A ref that exists but is older still runs green, so "the workflow passed" does not prove the version is current.

Native `externalNativeBuild` projects also need an explicit NDK install step in CI — see `android-build-troubleshooting` for the verified `nttld/setup-ndk` recipe.

### Workflow YAML Pitfalls

- **`${{ env.NAME }}` used in `path:` or an artifact name but never declared in the workflow's `env:` block silently expands to an empty string.** The step still runs and uploads to `/build/outputs/...` or an artifact named ` - - ...`. Grep each workflow for `env.` and confirm every key is defined at workflow or job level.
- **A trailing comma in a YAML scalar is part of the value, not a formality.** `path: app/build/outputs/apk/debug/*.apk,` uploads nothing because the glob ends in `,`. YAML has no trailing-comma convention outside flow sequences.
- Template leftovers ship silently: a copied workflow can keep a foreign `playstore_name` (e.g. a vendor/brand string) that only shows up in artifact names. Grep for the expected product name before committing.

### Patch Superposition Pitfall
- Multiple patches to same file can create duplicates if old_string matches already-patched code
- After each patch: read the file section to verify no duplicate lines
- Compile error on already-patched line → overlap detected → read file, fix manually
- Use replace_all=true for simple renames across the file

### Incremental Workflow Pattern
- Grep ALL references to removed functions BEFORE patching (minimizes compile-fix cycles)
- Build after each manager: `./gradlew :app:compileDebugKotlin --no-daemon -q`
- Test after extraction: `./gradlew :app:testDebugUnitTest --no-daemon -q`
- Commit separately: "refactor: extract [ManagerName] from MainActivity"
- Verify build success before extracting next manager

### Builder Pattern for Shared UI
- When multiple pages share duplicated UI code (e.g. API config blocks, settings areas), extract a **builder class** with constructor-injected lambda callbacks rather than duplicating the code in each Activity or Page.
- The builder receives only what it needs via constructor params (`activity`, `ui`, `palette`, `prefs`, callbacks) — NOT the full Activity — this prevents accidental access to engine, model, or session state.
- Define all functional callbacks in the constructor (`onToggle`, `onCopyAddress`, `onNewKey`, `onClearKey`, `onRefreshSurfaces`) and pass them from the calling Activity/Page.
- Use `dp()`, `matchWrap()`, `wrapWrap()` as private helpers in the builder instead of duplicating layout math; keep `UiWidgets` for the styled widget constructors.
- After extraction, replace the duplicated method with `builder.build(role, extraAfterAddress, extraNotes)` — this eliminates 100+ lines from the Activity per duplicated block.
- A builder that returns a data class of the built views  (`ApiBlockView(card, statusTv, addrTv, portEdit, keyTv, toggleBtn, statsTv)`) keeps the caller able to refresh each control later. The data class moves to the builder's own file; the Activity keeps no nested copy of it.

- **Scope guard:** the builder must stay within SHARED, PURELY-PRESENTATIONAL
  config (render + callbacks). If the extracted surface grows to READ or WRITE
  engine/session/network state (`ApiServer`, `ApiService`, the active
  `Conversation`, `llamaModel`), the coupling exceeds the host contract and
  the extraction will fight the Activity. Abandon the prototype before merging
  — keep only what the host interface already carries. The safe API-config split
  is a presenter that owns the surface widgets plus a thin callback; a second
  manager that re-models engine I/O is the coupling smell to cut.

### Pitfall: Do Not Duplicate the Theme Type
- The theme type already exists as a **data class** in the theme file (e.g. `YumenodeTheme` in `PonkoTheme.kt`) — **never redeclare it as an interface** in a new page/host/builder file.
- Redeclaring it as an interface causes a cascade of unresolved references (`warn`, `err`, `primarySoft`, `divider`, `fieldBg`, `idle`, `scrim`, `isDark`) because the real class exposes properties the new interface does not.
- Before creating a theme-related file, confirm the authoritative definition: `grep -rn 'data class YumenodeTheme\|interface YumenodeTheme' app/src/main/java/`. Exactly one definition must exist.
- A builder that needs the theme takes it as a constructor param typed with the **real** class; never introduce a parallel interface for the same concept.

### Constructor Lambdas Over Anonymous Inner Classes
- Prefer constructor-injected `() -> Unit` / `(T) -> Unit` lambdas over anonymous inner classes for callbacks in extracted classes.
- Constructor lambdas keep the extracted class self-contained and unit-testable without an Activity reference.
- A lambda passed from the Activity captures `this` implicitly with no memory leak risk (same lifecycle).
- If the callback needs the role/parameter, type it `(ApiServer.Role) -> Unit` and forward at the call site: `onToggle = { toggleApi(it) }`.

### ThemeManager Null Handling
- ThemeManager uses `checkNotNull` and `with` functions for null safety
- Theme changes trigger immediate UI updates via onThemeApplied callback
- Configuration changes maintain theme consistency with fallback defaults

### Theme switch: system bars and OLED

- Icon colour on the status/navigation bars follows their **contrast**, not `isDark`. Sample the colour actually behind the icons (`pal.statusBar`/`pal.navBar` below API 35, `pal.bg` on 35+) and set `APPEARANCE_LIGHT_STATUS_BARS` / `..._NAVIGATION_BARS` through `WindowInsetsController` (API 30+) or `SYSTEM_UI_FLAG_LIGHT_*` below it.
- Setting only `LIGHT_NAVIGATION_BAR` — the usual copy-paste — leaves white status icons on a light bar (`#F2F4F8`): invisible, with a green build and no runtime error.
- `targetSdk >= 35` ignores `window.statusBarColor` and draws edge-to-edge, so testing the bar colour you just assigned checks the wrong surface; evaluate the page background instead.
- An OLED variant is `dark().copy(bg = 0xFF000000, surface = 0xFF000000, …)` with borders and fields barely lifted (`#2A2A2A`, `#0A0A0A`). Lift the surfaces too, or a full-screen card keeps most of the display at the dark grey instead of at black. Prove it from a screenshot by counting the dominant pixel colour, not by eye.

### Integration Best Practices
- Use data classes within each manager (QaTurn/ChatSession in SessionManager)
- Maintain pure logic: no View/ui-context in managers
- Activity becomes UI-only container delegating to managers
- Each manager has single responsibility and is testable independently

### Moving a deeply coupled method as an extension

`doSend`/`runRound` (250–300 lines, ~30 Activity members) have a clean shape — a host interface — and a cheap one: move them out **unchanged as extensions on the Activity**.

```kotlin
// ChatSend.kt — same body, same state, zero call-site edits
internal fun MainActivity.doSend() { … }
internal suspend fun MainActivity.runRound(…): RoundOut { … }
```

The file shrinks and the flow gets its own home; the coupling remains, so treat it as a waypoint rather than real separation. The mechanical steps (opening only what the compiler names, the property/setter JVM clash, qualifying duplicated class names) are in `references/runtime-testing.md`.

## Git Workflow
- Before push: fetch origin, rebase origin/main if needed, then push
- **Another agent may commit to the same branch.** If `git log` shows commits
  you did not author, your working tree may have been swept into them and the
  tip may be a state neither you nor they tested (CI can be red on a commit
  that looks like a clean refactor). Re-read the log, re-derive which of your
  changes landed inside those commits, and re-run the gates on the **actual
  tip** before pushing — the earlier green run certifies a tree that no longer
  exists. See the `dispatching-parallel-agents` skill.

### Keep New Refactors on Their Own Branch

This user asks for the refactor work to be **landed on the integration branch
and the next work to continue on a separate branch**. The standing rule:

- **One branch per refactor group.** Do not pile a new extraction onto the
  tip of the branch that already carries the previous group. When the user
  says "haz el merge" (or "merge and keep new work apart"), the sequence is:
  merge the finished group into the integration branch, then
  `git checkout -b feat/<next>` **from the updated integration branch**.
- **Land a group only when the user asks.** Do not push a completed refactor
  group to the integration branch on your own initiative — a large
  `origin/beta` diff changes what the next build and the next review cover.
- **A branch-local fix that belongs to a shared problem must be ported to
  every branch that builds in CI** (a shared CI/workflow file exists in each
  branch's own copy). See the merge section above.
- The user's rule is **"new refactorizations apart"**, not "one commit per
  manager": a coherent group of related extractions can land together in one
  merge, and splitting it across several merges multiplies the CI runs
  without adding review value.

### Mid-Flight Imperatives and Status Replies

This user steers with short imperatives dropped into a running task
("ataca ya X", "implementala", "status"). They are steering commands, not
new topics to plan around.

- **Switch to it immediately** and drop the lower-priority thread. Do not
  finish the previous step first, do not ask whether to continue, and do
  not re-plan: the instruction is already the decision.
- **"Status" wants a compact table, not a recap.** Three rows: what is
  running (with its real state), what is done AND verified (with the
  evidence), what is still pending. One line each. No narration of the
  reasoning that led there — that was already reported.
- **Never report success you have not seen in output.** If a build is
  still compiling, say it is compiling; if a claim rests on a number read
  from a summary rather than from the tree, re-derive it before quoting it.
- A long native build is not dead time: it is the window to ask the
  scoping question for the next block, or to write the tests for the
  change already in flight.

## Android Kotlin Compilation Pitfalls

### Stale Incremental Cache (phantom `Unresolved reference` errors)
The Kotlin incremental compiler can reuse a stale symbol/ABI cache and report
`Unresolved reference` for names that DO exist in source (in this project the
`YumenodeTheme` members `softBtn`, `fieldBg`, `primarySoft`, `hint`, `mediaBg`,
`stop` showed up missing in `AttachmentHandler`/`DrawPage` for 17 sites).
These are NOT refactor bugs until proven otherwise:

1. Run a clean build first: `./gradlew clean assembleDebug`.
2. If still red, `git stash` and confirm the baseline fails identically — a matching
   failure proves the error is pre-existing, not caused by your extraction.
3. Green after `clean` => the cause was the incremental cache, not the source.

Editing source against a stale-cache error leaves the real cause hidden and adds
unrelated churn. Treat incremental-only `Unresolved reference` errors as cache
faults, not as the refactor's own defects.

### Import Paths (Common Mistakes)
- `android.view.Gravity` — NOT `android.graphics.Gravity`
- `android.view.View` — NOT `android.widget.View`
- `androidx.recyclerview.widget.RecyclerView` — NOT `android.widget.RecyclerView`

### Type Mismatches
- Literals like `0xFF3B82F6` (Long) passed to `Int` parameters → append `.toInt()`
- Function parameter types must match exactly: check signature before calling (e.g. `FileManager.readAllCapped(ins, cap: Int)` not `Long`)
- Return types: match nullable vs non-nullable (`ByteArray?` vs `ByteArray`)
- **A third-party `Pair` is not `kotlin.Pair`.** `net.ladenthin.llama.value.Pair` exposes `key`/`value` (Java `getKey()`/`getValue()`), not `first`/`second`; `it.first` fails with `Unresolved reference 'first' on receiver of type 'Pair<String, String>'`. Use `it.key`/`it.value`, and construct with the fully-qualified class or an import alias. Confirm the real shape with `javap -p` on the AAR's `classes.jar` under `~/.gradle/caches/.../transformed/` instead of assuming Kotlin semantics.
- Multimodal message parts need `import net.ladenthin.llama.value.ContentPart`; without it `ChatMessage.userMultimodal(ContentPart...)` is unreachable and the error is just `Unresolved reference 'ContentPart'`.

### Type Conflicts Between Duplicate Classes
- When splitting a monolithic file, classes with the same name (e.g. `ChatSession`, `QaTurn`) must not collide
- Move shared data classes to a shared file (`ChatState.kt`) with explicit `package com.litertchat.app`
- REMOVE nested duplicate classes from the Activity — do NOT use inheritance (`class ChatSession() : ManagerChatSession()`) as a workaround; it creates new type mismatches and "private-in-class type argument" errors
- Import shared classes directly: `import com.litertchat.app.QaTurn` — NOT `import com.litertchat.app.ChatState.QaTurn` (ChatState is a filename, not an object container)
- Always verify imports resolve after extraction: `grep -n "import" <file>` before compiling

### Verify an Extraction Is Wired
- After moving a block into a manager, confirm the Activity actually calls the manager's entry point. An injection method (`attachViews()`, `create()`, `init()`) that is declared but never called leaves the extracted logic dead: it compiles, it passes review, and it silently never runs.
- Detect by reference count — zero external references means nothing calls it:
  `grep -rn '\b<methodName>\b' app/src/main/java/ | grep -v <ManagerFile>.kt | wc -l`
- This is the single highest-value check after an extraction: it finds the bug that compilation cannot.

### Manager Constructed Before the Views It Needs Exist

Extracting a scroll/focus/attachment manager makes it depend on Views the Activity builds
later in `buildUi()`. If the manager is constructed with a direct `View` reference and that
call site runs before the `build*Bar()` / `build*Row()` function that assigns the
`lateinit` field, `onCreate` throws:

```
UninitializedPropertyAccessException: lateinit property inputEdit has not been initialized
```

The app then dies on the splash screen: black background, launcher icon centred, no visible
error, and the process is gone within a second.

- **Fix with a provider, not by reordering the build calls.** Change the constructor
  parameter to `private val inputEditProvider: () -> EditText` and expose
  `private val inputEdit: EditText get() = inputEditProvider()`; the Activity passes
  `{ inputEdit }`. Reordering is fragile because page builders legitimately read each
  other's fields, so the next refactor breaks the order again.
- **The same shape applies to any `lateinit var` view handed to a manager at
  construction** — dialog anchors, adapters, snackbar roots. Grep a newly extracted
  manager's constructor arguments for `lateinit` fields before compiling.
- **Diagnose it from the crash buffer, not the main log.**
  `adb logcat -d -b crash | tail -20` (or `--pid=$(adb shell pidof <pkg>)`) carries the
  `AndroidRuntime` trace; the default stream is mostly surface/HWUI noise and the app's own
  tags may never appear. The `Caused by:` line names the property and the exact `buildUi()`
  call site.
- Compilation cannot catch this: the field is declared and typed correctly, it is merely
  unassigned at the moment of use.

### Extracting a Page Class (host interface, not the Activity)

A 200–450 line `buildXxxPage()` is not a manager: it reads theme, prefs and other
page state. Do not pass the Activity in — declare a narrow contract and implement
it on the Activity:

```kotlin
interface SettingsHost {
    val activity: Activity
    val palette: PonkoTheme            // as a provider: { pal } — theme can rebuild
    val ui: UiWidgets
    val themeMode: Int
    val drawBusy: Boolean
    fun applyThemeMode(mode: Int)
    fun prefBool(key: String, def: Boolean): Boolean
    fun prefPutBool(key: String, value: Boolean)
}
class SettingsPage(private val host: SettingsHost) { fun build(): View = with(ctx) { … } }
```

- The interface is the point: the page then **cannot** reach `engine`, `llamaModel`,
  `genJob` or sessions, so the compiler enforces the boundary the refactor was for.
- Wrap the moved body in `with(ctx) { … }` so the `Context` extensions (`dp`,
  `matchWrap`, `wrapWrap`) resolve. `with` is **inline**, so a bare `return body`
  inside it still returns from the enclosing function — do not rewrite returns to
  `return@with`.
- Style builders that stay in the Activity can be injected as lambdas
  (`makeCard: () -> LinearLayout`, `makeHint: (String) -> TextView`); if several
  screens need them, move them to a `UiWidgets(activity, palette)` class instead.
- **After the mechanical move, four tokens survive and must be re-wired:**
  `this@MainActivity`, `chatPrefs()`, the `C_*` colour getters and `ui.*`. Grep the
  generated file for all four before compiling — they are the only things the new
  file cannot resolve on its own.
- Rewriting call sites wholesale is safe with a lookbehind that keeps dotted calls
  out: `(?<![\w.])card\(` → `ui.card(`. Lowercase names do not clobber CamelCase
  siblings, so `card(` never touches `sectionCard(`.
- Palette accessors belong on the page (`private val C_TEXT get() = pal.text`), fed
  by the injected `PonkoTheme`; a page that reads a stale captured palette leaves
  white blocks in dark mode after a theme switch.
- Move the display-only helpers with it (collapsible sections, link builders,
  formatters) and delete the originals from the Activity in the same commit; a
  leftover copy is dead code that the next reader will edit by mistake.

### Finding the Phone on the Network (the device gate is not optional)

When the device gate is pending, do not conclude "no device" from
`adb devices` being empty — a Wi-Fi device shows up only after `adb connect`.
Sweep the subnet for the ADB port before giving up:

```bash
# the phone's own IP is often NOT the gateway: check the host's own address
ip -4 addr show wlp2s0 | grep inet          # e.g. 192.168.1.241/24

# sweep the whole /24 on the ADB ports, in parallel
timeout 100 bash -c 'for i in $(seq 2 254); do for p in 5555 37099 41234; do \
  (timeout 1 bash -c "echo > /dev/tcp/192.168.1.$i/$p" 2>/dev/null && \
   echo "192.168.1.$i:$p ABIERTO") & done; done; wait'

adb connect 192.168.1.239:5555 && adb devices -l
```

- Testing only the **gateway** IP (`192.168.1.1` / `192.168.1.254`) is the
  common mistake — the phone is a *host* on the subnet, and the gateway
  refuses the connection ("Connection refused"), which looks like "nothing
  there".
- `adb mdns services` is unsupported on many adb versions ("mdns is not
  supported by this version of adb") — the port sweep is the reliable path.
- A full /24 sweep on three ports takes ~100 s in parallel; run it in the
  background while the build compiles instead of waiting for it.

### Verifying a Store Extraction on the Device

A file-catalogue refactor is verifiable on-device without any model load, by
planting a fixture in the app's private dir and reading it back through the UI:

```bash
# write a fixture as the app's own user (adb shell cannot write here)
adb push set.json /data/local/tmp/ && adb shell run-as <pkg> sh /data/local/tmp/put.sh
adb shell run-as <pkg> cat files/draw/sets/<id>/ponko-set.json
```

- **`adb shell run-as <pkg> sh -c '...'` does not pass the command reliably** —
  put the script in a file, `adb push` it, and run `run-as <pkg> sh /data/local/tmp/x.sh`.
  A heredoc inside `run-as` fails too ("can't create temporary file:
  Permission denied").
- Plant a fixture with **one relative slot and one absolute slot** — that is
  the pair the JSON round-trip has to get right, and the UI shows the result
  as a size: a 2-file set should read as the sum of both files.
- Read the app's own preferences back to prove the write path:
  `adb shell run-as <pkg> cat shared_prefs/ponko.xml` and grep for the key
  the store is supposed to set.
- Clean the fixture up afterwards (`rm -rf` the set dir) so the next run
  starts from a known state.

### A Gradle Daemon JVM Pin Breaks CI Intermittently

`gradle/gradle-daemon-jvm.properties` (generated by `updateDaemonJvm`) pins the
daemon to a specific JDK, downloaded from `api.foojay.io`. It works on the
developer's machine — the tarball is cached in `~/.gradle/jdks/` — and **fails
intermittently in CI**, where every run downloads it fresh:

```
Unable to download toolchain matching the requirements
{languageVersion=25, vendor=JetBrains, implementation=vendor-specific, ...}
from 'https://api.foojay.io/disco/v3.0/ids/.../redirect', due to:
Could not HEAD '...'. Received status code 400 from server: Bad Request
```

**Read the run durations — they name the bug.** The failing runs die at ~1 min
(aborting the download); the passing ones take 4-5 min (they downloaded the
JDK). "Fails sometimes, and the fast ones are the failures" is a download
being rate-limited, not a flaky test.

- The **HEAD** request is what fails. `curl -I` on the same URL often returns
  301, so a quick manual check says "the URL is fine" — the 400 only appears
  with Gradle's request. Verify by running the build, not by pinging the URL.
- **The pin is usually unnecessary**: the project compiles with
  `sourceCompatibility`/`targetCompatibility` 17 and the workflow already
  installs a JDK with `setup-java`. The pinned daemon JDK is decoration.
- **The fix is to delete the pin**, not to retry:
  - remove `gradle/gradle-daemon-jvm.properties`;
  - remove the `org.gradle.toolchains.foojay-resolver-convention` plugin from
    `settings.gradle.kts` (it exists only to resolve/download toolchains);
  - let Gradle use whatever JDK the machine has.
- **Reproduce CI locally before pushing**: download the same JDK the workflow
  installs and build with it —
  `JAVA_HOME=/path/to/jdk17 ./gradlew :app:compileDebugKotlin --no-daemon`.
  Then check the daemon actually switched: the log line
  `javaHome=..., javaVersion=17` in `~/.gradle/daemon/<ver>/*.log`.
- **The fix belongs on every branch that builds in CI** — `main` and `beta`
  keep their own copy of the file, so a fix on a feature branch does not
  protect the release workflow. Port it and push it separately.
- After pushing, **watch the real CI**: `gh run list --workflow ci.yml` and
  confirm the new run is green. A locally-green build does not prove the CI
  is fixed.

### The Equivalence Test: Pin the ORIGINAL Logic, Not Just the New One

When a refactor moves a decision out of the Activity into a manager, the risk
is not the new function — it is that the **call sites** changed meaning. The
strongest guard is a test that re-implements the ORIGINAL condition verbatim
and compares it with the extracted one across a matrix of states:

```kotlin
// the original, copied from the Activity before the move
private fun originalIsReady(engineLoaded: Boolean, loadedModel: String?, ...): Boolean {
    val readyForLoad = engineLoaded && loadedModel == wantModel && ...
    val errorIfNotReady = !engineLoaded || loadedModel != wantModel || ...
    check(readyForLoad != errorIfNotReady)
    return readyForLoad
}

// the extracted one
private fun newIsReady(...): Boolean =
    TaggerSelection(model, csv, gpu).isReadyWith(session)

@Test
fun newLogicMatchesTheOriginalInEveryState() {
    for (loaded in booleanArrayOf(true, false))
        for (model in listOf("a.onnx", "b.onnx", null))
            for (gpu in booleanArrayOf(true, false))
                assertEquals(originalIsReady(...), newIsReady(...))
}
```

- **Build the matrix from the interesting values only**: 2 bools x a few names
  x a null. 128 cases run in milliseconds; a 3x3x2x2x2x2 matrix is enough to
  cover every branch.
- **Copy the original from git**, not from memory:
  `git show <old-commit>:<file> | sed -n '/<function name>/,/^    }/p'`. The
  original may differ from what you remember.
- The `check(readyForLoad != errorIfNotReady)` inside the original
  re-implementation is deliberate: it proves the two original call sites
  agreed, so comparing against either one is sound.
- **Add the negative-control test** — assert that the *inverted* form of the
  new function gives the wrong answer for the obvious case. It documents the
  trap for the next reader and fails loudly if someone reintroduces the `!`.
- This is the only refactor guard that survives the fact that unit tests of
  the extracted function alone can all pass while the app is broken.

### Name a Boolean After the POSITIVE State, Not the Negative One

When two call sites must agree on a condition (does the engine already hold
the right model? is the tagger loaded with the right backend?), extracting the
condition into a shared function is right — but naming it negatively invites a
silent inversion:

```kotlin
// DANGEROUS: the caller must remember to invert it
fun needsReload(session: TaggerSession): Boolean = ...
if (!sel.needsReload(session)) return null      // ready
if (sel.needsReload(session)) return errorMsg    // not ready
```

One of those two negations is wrong, and the compiler accepts both. The
failure is silent: the app reloads a model that is already loaded, or it
reports "not ready" for a model that is.

**Prefer the positive form** so the two call sites read alike and there is
nothing to invert:

```kotlin
fun isReadyWith(session: TaggerSession): Boolean = ...
if (sel.isReadyWith(session)) return null       // ready
if (!sel.isReadyWith(session)) return errorMsg  // not ready
```

- The refactor is exactly where this bug appears: before extraction, each
  call site carried its own comparison; after, they share one function — and
  the shared function's polarity decides whether both are correct.
- **Re-read the extracted condition against every call site after the move.**
  Map each call site to its intended outcome ("here we want ready", "here we
  want not-ready") and check the polarity matches. A `!` you added while
  wiring is the most likely place for the bug.
- A **characterization test cannot catch this** if it only tests the extracted
  function in isolation: the function may be perfectly correct while the call
  site negates it. Test the *pairing* — the same session/selection against
  both "ready" and "not ready" outcomes — and state the expected outcome in
  the test name (`sameModelCsvAndBackendAreReady` vs
  `aDifferentModelIsNotReady`).
- This is the one class of refactor bug that compiles, passes every unit
  test, and still ships broken. It only shows up on-device, which is why the
  device gate is not optional for behaviour-changing extractions.

### A Catalogue Store Keeps the "Session > Saved > First" Rule

A file catalogue (LoRAs, models, presets) usually resolves "which one is
active?" with a three-level fallback. Extract it as a store and **pin every
level with a test** — the levels are where the bugs live:

```kotlin
class LoraStore(private val filesDir: File, private val prefs: SharedPreferences) {
    fun active(sessionSelection: File? = null): File? {
        val all = list()
        if (all.isEmpty()) return null
        val sel = sessionSelection
        // 1. the session choice wins, but only if the file is still there
        if (sel != null && sel.isFile && all.any { it.absolutePath == sel.absolutePath }) return sel
        // 2. the saved choice, matched BY NAME
        val saved = prefs.getString(KEY_SEL_LORA, null)
        if (saved != null) all.firstOrNull { it.name == saved }?.let { return it }
        return all.first()   // 3. otherwise the first one
    }
}
```

- **Save the NAME, not the absolute path.** The app's data directory can move
  (backup restore, different install path); the name is the only stable
  identifier. A path-keyed preference silently resets after a restore.
- **The session selection must be validated against the file list.** A user
  deletes the LoRA they had selected: the stale `File` object still points at a
  path, so without the `isFile` + membership check the app hands a
  non-existent file to the engine.
- **A test must cover the *fallback* path, not just the happy one**: the saved
  name points at a deleted file → the first one is used. That branch is the
  one that never runs in dev and breaks in the field.
- Keep the Activity's public API as delegating one-liners
  (`fun listLoras() = loraStore.list()`) so the call sites in the Activity do
  not change and the extraction stays reviewable as a pure move.
- **Sweep the newly-dead code before committing**: a method the Activity never
  called (`clearSelection()`) is dead the moment the store owns the state —
  delete it *and its test*, otherwise the test task fails to compile.

### Context Extensions Need an Explicit Receiver Outside an Activity

`Context.dp()`, `Context.matchWrap()`, `Context.toast()` resolve through the
implicit `this` **inside an Activity** (which IS a Context). In a plain class
that holds a `Context` field they do not:

```
Candidate 'fun Context.matchWrap(top: Int = ...)' is inapplicable because of
a receiver type mismatch.
```

- Fix by delegating through the held context — do not re-add a local copy:
  ```kotlin
  private fun matchWrap(topMargin: Int = 0) = with(activity) { matchWrap(topMargin) }
  ```
  `with(ctx) { ... }` is **inline**, so the extension resolves against `ctx`.
- The local copy is what you are trying to delete. Keeping it "because the
  extension does not resolve" re-creates the duplicate.
- `with` also works for a `Context` **extension** on a member function body:
  `with(activity) { matchWrap() }` inside a method of the class.
- The shared extension should be the **superset** signature. When one call
  site needs `leftMargin` and another does not, add the parameter with a
  default (`fun Context.wrapWrap(leftMargin: Int = 0)`) — that way the 13 call
  sites of the simpler variant do not have to change.
- The arithmetic behind an extension still needs its own pure home if it is
  to be testable: `Context.dp()` depends on `resources`, so the calculation
  belongs in a plain object (see the dp-to-px unification) and the extension
  just passes `resources.displayMetrics.density` to it.

### Identifying Placeholder Values by Shape, Not by Prefix

Code that ships sample data often needs to recognise "this value is a
placeholder, do not use it". The fragile way is to test a **prefix**:

```kotlin
// FRAGILE: a real hash starting with "a1b2" would be treated as a placeholder
if (expected.startsWith("a1b2") || expected.startsWith("b2c3")) return true
```

A SHA-256 is 64 hex chars, so a 4-hex prefix collides with 1 in 65.536 real
values — and when it collides, the whole verification is skipped, silently
accepting a file that was never checked.

**Match the exact shape instead**: the placeholder is literally
`"a1b2c3d4e5f6..."` (groups of 4 hex, dots, trailing `...`), so a full-string
regex is unambiguous:

```kotlin
private val PLACEHOLDER = Regex("^[0-9a-fA-F]{4}([0-9a-fA-F]{4}){2}\\.\\.\\.$")
fun isPlaceholder(s: String?): Boolean =
    PLACEHOLDER.matches(s?.trim().orEmpty())
```

- A full-string match cannot collide with a real value of a different shape.
- **Test the collision case explicitly**: assert that a real-looking hash
  beginning with the old prefix is NOT treated as a placeholder. Without that
  test, the fix can regress silently.
- Also test the *truncated* placeholder (`"a1b2c3d4e5f6"`, no dots): it is
  not the placeholder shape, so it must be verified rather than skipped.
- The same "shape not prefix" rule applies to any sentinel value: empty
  string, `null`, and whitespace-only all mean "absent" and should be
  handled explicitly.

### The API Contract Is a Public Surface: Extract and Pin It

A local HTTP API that advertises itself as OpenAI-compatible has a **public
contract**: Hermes, OpenWebUI, Continue and LangChain all depend on the exact
JSON shape. A silent change breaks agents that look fine in the app.

- Extract the contract into a pure object that only builds and reads JSON (no
  sockets) and pin the shape with JVM tests.
- **Unify the error bodies** in one helper and confirm the output is
  **byte-identical** (same key, same order) so no client sees a difference.
- **Name the error types** (`ErrorType.INVALID_REQUEST`) instead of repeating
  the wire literal.
- **A regex rewrite can rename identifiers it did not mean to** — map the
  snake_case wire value to the Kotlin constant name explicitly.
- **Verify against the real device**, not only the unit tests: the HTTP
  round-trip against the phone is the definitive check.

The object shape, the SSE bytes to look for and the `curl` commands are in
`references/runtime-testing.md`.

### When a Characterization Test Fails, Check the Expectation Before the Code

A characterization test pins **the current behavior**, so when it fails on the
first run, the default assumption ("my expectation is right, the code is
wrong") is usually backwards: you wrote the expectation from the *idea* of the
code, not from what the code *does*.

- **Print the real value and compare** instead of guessing. A throwaway test
  that prints the value settles it in one run:
  ```kotlin
  @Test fun probe() { println("CUT=[$cut] len=${cut.length}") }
  ```
  Run it with `-i` to see stdout, then delete the probe.
- **Do not "fix" production code to match a guessed expectation.** The
  characterization test's job is to record reality. If reality is wrong, that
  is a **separate** bug with its own commit and its own justification.
- The surprises are the value. In this codebase a budget calculation that
  looked like "one 12-token envelope per turn" actually charged **two**
  envelopes (one for the turn, one for the current message) — invisible in the
  code, obvious in the test. Assert the *number* explicitly, not a relation.
- Assert **concrete relations you are sure of** (`withoutLast < full`,
  `cut == text.substring(0, cut.length)`) instead of restating the
  implementation in the assertion. An assertion that mirrors the code proves
  nothing; one that pins a property catches a real change.

### Duplicated Clamps Are the Cheapest Extractions

The same `coerceIn(...)` chain repeated in two or three call sites is a pure
extraction waiting to happen — no manager, no host interface, no UI risk:

```kotlin
// Before: the same magic numbers written out three times
val steps = stepsEdit.text.toString().toIntOrNull()?.coerceIn(1, 150) ?: 20
val cfg    = cfgEdit.text.toString().toFloatOrNull()?.coerceIn(1f, 30f) ?: 7.0f
val w = (widthEdit.text.toString().toIntOrNull() ?: 512).let { (it / 64) * 64 }.coerceIn(64, 2048)

// After: one object, one definition per rule
object DrawParamsLogic {
    fun steps(raw: String?) = raw?.toIntOrNull()?.coerceIn(1, 150) ?: 20
    fun size(raw: String?) = ((raw?.toIntOrNull() ?: 512) / 64 * 64).coerceIn(64, 2048)
}
```

- **Find them with a grep, not by reading:** `grep -n "coerceIn" <file> | cut -c1-130`
  and count how many times each numeric bound repeats. Every bound that appears
  2+ times is a rule that should live in exactly one place.
- **Pure `object` over a class here** — the logic is stateless, so it needs no
  constructor, no context and no instance. A class with a `Context` would make
  the tests need Robolectric for no reason.
- **Extract the formulas too, not only the clamps.** The arithmetic that was
  inline (`0.15f + (strength - 0.05f) * (0.40f / 0.94f)`) is the part most
  likely to be wrong and is exactly what a characterization test should pin.
  A test that only re-asserts `coerceIn` bounds has low value; one that fixes
  the *mapping* (slider 0.05 → denoise 0.15, slider 0.99 → denoise 0.55) has
  real value.
- **After the swap, grep the old bounds again — they must be gone:**
  `grep -c "coerceIn(1, 150)" <file>` returning 0 proves the duplication is
  actually gone, not merely that new calls were added.
- Watch for the **duplicated anchor** when patching: two call sites with the
  identical line (`val steps = stepsEdit...`) make `old_string` match twice and
  the patch abort. Either include a distinguishing preceding line, or apply the
  replacement to **all** occurrences when every one of them gets the same change.

### Find the Duplicates by Name, Not by Reading

The cheapest extractions are the ones you did not know were there. A
function name repeated across files is a candidate; read only those to
confirm:

```bash
# which names appear in 2+ files?
grep -rhoE "(private |internal )?fun [a-zA-Z]+\(" app/src/main/java/com/<pkg>/*.kt \
  | sed 's/.*fun //;s/(//' | sort | uniq -c | sort -rn | head -12
```

- **Expect false positives and check each one.** `toast` and `setStatus`
  appearing 7 and 5 times is usually several *interface declarations* plus
  one implementation — not seven copies. Grep the definition itself before
  concluding duplication:
  `grep -rn "fun toast" app/src/main/java/ | cut -c1-130`.
- **Compare the bodies, not the names.** Two `fitTokens` with the same name
  can be byte-identical (a real duplicate) or differ in one branch (two
  conventions that must both be preserved — see `UiScale`, where one copy
  truncated and one rounded).
- **A duplicated name in a different package is not necessarily a duplicate
  either**: `Context.dp()` (extension) and a private `dp()` in a class are
  the same *concept*, and unifying them is the point, but the call sites
  differ in how the receiver is obtained.
- The same grep finds **dead code**: a name with exactly one hit (its own
  definition) is a candidate for deletion once the extraction lands.

### Extract Pure Logic First, Then the UI

The cheap wins are the value-level helpers: formatting, size/speed/ETA,
token estimation. They duplicate silently across Activity and manager, have no
Android dependency, and get real JVM tests without Robolectric. Unifying them
usually surfaces a genuine bug — e.g. `String.format("%h:%02d", …)` for hours,
where `%h` prints the argument's *hashCode*, so any value ≥ 1 h renders garbage
instead of `1:30`. Pin the fixed behaviour with a table-driven test before moving on.

### Extract the Data Class Too, Not Just the Manager

When the nested class moves out of the Activity, move it as a **file-level
class** and repoint every reference:

- `DrawPage.ModelSet` → `com.yumenode.ai.draw.ModelSet` (a new import in the
  Activity). A nested class referenced as `Outer.Inner` from another file
  cannot stay nested once the outer class is gone.
- A file-level class must live in a file whose name does not collide with an
  existing class. Two top-level classes with the same name in the same package
  is a `Redeclaration` error; a *nested* copy does not collide by itself, so
  grep the whole tree (`grep -rn '\bclass ModelSet\b' app/src/main/java/`) and
  delete every copy in the same commit.
- **One source of truth for the constants.** When the store takes over the
  persistence, the shared constants move with it (`KIND_SINGLE`, `KEY_SEL_SET`,
  `TAESD_MIN_BYTES`, …). The old owner keeps a `const val` that *points* at the
  new home (`const val KIND_SINGLE = ModelSetStore.KIND_SINGLE`) so existing
  call sites keep compiling, and the private duplicates that lost their last
  user are deleted. Two files writing the same preference key is how a
  preference silently resets on restart.

### Descargas por rangos: tres trampas que cuestan un dia

Implementar descarga por rangos (HTTP `Range`) parece simple y no lo es.
Estas tres cosas aparecen siempre:

1. **`HttpURLConnection` NO sigue los 308 (Permanent Redirect).** Sigue
   301/302/303/307, pero el mirror de HuggingFace (`hf-mirror.com`)
   responde **308** y redirige a `huggingface.co`. La descarga falla con
   "HTTP 308" sin empezar. Hay que seguir las redirecciones **a mano**:
   ```kotlin
   var current = url
   repeat(5) {
       conn = (URL(current).openConnection() as HttpURLConnection).apply {
           requestMethod = "GET"
           setRequestProperty("Range", range)
       }
       val code = conn.responseCode
       if (code !in setOf(301, 302, 303, 307, 308)) return conn
       val loc = conn.getHeaderField("Location") ?: return conn
       current = URL(URL(current), loc).toString()   // puede ser relativa
   }
   ```
   El sondeo decide por el **codigo**, no por `Accept-Ranges`: un `GET`
   con `Range: bytes=0-0` devuelve 206 si el servidor admite rangos y 200
   si los ignora. Un `HEAD` no sirve: muchos servidores no devuelven
   `Content-Length` en HEAD y el tamano queda desconocido.

2. **Un `RandomAccessFile` compartido entre hilos CORRUPTE el fichero.**
   Su puntero de escritura es UNO: el `seek()` de un hilo pisa la posicion
   del otro. Escribir en un offset exige `FileChannel` con escritura
   **posicional** (`channel.write(buf, position)`), que no toca el puntero
   y es segura entre hilos. Este bug no lo ve el compilador ni una
   descarga de un solo tramo: solo aparece con 2+ tramos en paralelo.

3. **El fichero preasignado PARECE completo.** Escribir en un offset exige
   que el fichero tenga ese tamano, asi que se preasigna al final: a medio
   descarga, `file.length()` ya da el tamano TOTAL. Cualquier comprobacion
   por tamano ("ya descargado", "incompleto") dira que esta bien. Hace
   falta un marcador aparte (p. ej. `modelo.gguf.parts`) que delate la
   descarga en curso, y consultarlo en `isModelDownloaded()`,
   `isIncomplete()` y en el chequeo de "ya existe" de `downloadModel`.
   Ademas, los reintentos NO deben borrar el fichero ni el marcador, o la
   reanudacion se pierde.

**Sondeo del servidor con rangos reales, no con un mock.** El test de
ensamblado tiene que comprobar el fichero **byte a byte** contra lo que
devuelve el servidor: un tramo en el offset equivocado da un fichero del
tamano correcto pero corrupto, y un test que solo mira el tamano pasa en
verde. Un `com.sun.net.httpserver.HttpServer` local basta; las cabeceras
hay que fijarlas **ANTES** de `sendResponseHeaders` (despues, el servidor
ya envio la cabecera de estado y se pierden).

### Green Gate Before Every Commit

An extraction does not count as done until every gate below is green, in order.
Run them in sequence; a red gate stops the pipeline, and you must fix it before
the next gate.

1. `./gradlew compileDebugKotlin --no-daemon -q`
   — source compiles. Run this first: the test task compiles `main` before any
   test runs, so a broken source set hides behind it.
2. `./gradlew assembleDebug --no-daemon -q`
   — APK builds.
3. `./gradlew testDebugUnitTest --no-daemon -q`
   — unit tests pass. **Never quote a pass count from memory or from an earlier
   session's summary** — read the real numbers from
   `app/build/test-results/testDebugUnitTest/TEST-*.xml` (sum the `tests=` and
   `failures=` attributes) or from the Gradle output. A test tree can be emptied
   between sessions, so a remembered count is a claim that may be false.
4. `adb` on device — UI behaviour verified when the extraction touches UI
   (layout, theme switch, plegable section folding, persistence).

All four must be green before the commit message is written. A green
`compileDebugKotlin` with red tests, or a working APK with red unit tests, is a
blocker, not a signal. Device checks when UI is touched: layout render, theme
switch, plegable collapse, persistence.

### Stray Brace Detection After Deleting a Function

When a function is removed from the middle of a class, a leftover `}` from its
body can silently close the class early. Symptoms:

- `this` is "not defined in this context" for fields the class should have;
- methods that previously compiled now report `Unresolved reference 'X'`;
- `android.databinding` or `lateinit` property faults surface later than the
  real cause.

Process: after deleting a function body, read the lines around the deletion
point and confirm the next method sits at the same indentation level as the
function's signature, not one level deeper. Re-run `compileDebugKotlin` before
moving to the next extraction — the compiler is least likely to surface a class
structure error early in the full build.

### this Capture in Kotlin Anonymous Objects (Host Contract Pattern)

When the host object is declared as `object : HostContract { ... }`, Kotlin's
unqualified `this` refers to the **anonymous object itself**, not the outer
Activity. An implementation that reads `onPickModel() = pickModelFile()` is
silently calling the contract's own method (missing, or self-recursive) instead
of `MainActivity.pickModelFile()`. Every cross-reference must be qualified:

```kotlin
override fun onPickModel() = this@MainActivity.pickModelFile()
override fun onToggleLoad() = this@MainActivity.toggleLoad()
override val palette: YumenodeTheme get() = this@MainActivity.pal
override val filesDir: File get() = this@MainActivity.filesDir
```

A grep for the plain `this` inside a host object — without a `@` qualifier —
finds the silent self-delegation before the compiler does.

### Missing Host Members: Resolve by Grep, Not by Guess

When the compiler reports `Class 'Activity' is not abstract and does not
implement abstract member`, do not hand-add methods one by one. Grep the
extracted class (or page) for every `host.` reference, list them up front,
and write all overrides against the interface in a single pass. The compiler
reports each missing member by name, so the fix is mechanical — but batching
the writes prevents the confusion of scattered, half-way implementations.

### Page Owns the Views: Delegate Activity Fields with Getters

When `buildXxxPage()` moves into a page class, the page creates the views but the
Activity keeps its `lateinit var savedContainer` / `private var drawProgress: T? = null`
declarations. Nothing assigns them any more, so the first refresh during `build()`
throws `UninitializedPropertyAccessException: lateinit property savedContainer has
not been initialized` and the app dies on the splash screen (stack points at
`refreshSavedModels` ← `switchModelsTab` ← `Page.build`).

Fix — keep one owner and make the Activity fields read-only delegates:

```kotlin
private lateinit var modelsPage: ModelsPage          // assign BEFORE build()
// buildUi(): modelsPage = ModelsPage(createModelsPageHost()); tabModels = modelsPage.build()

private val savedContainer: LinearLayout get() = modelsPage.savedContainer
private val drawProgress: ProgressBar?   get() = modelsPage.drawProgress
```

- Assign the page instance to the field *before* calling `build()`; the page calls
  `host.onSwitchXxxTab(0)` at the end of its own build, which re-enters the
  Activity and reads those views.
- `::field.isInitialized` guards break once a field stops being `lateinit`
  (`This declaration can only be called on a reference to a 'lateinit' property`).
  Retarget them at the page: `if (!::modelsPage.isInitialized) return`.
- Verify no other assignment exists before converting: `grep -nE "^\s+<name> = "`
  on the Activity. Zero hits means the delegate is safe.
- Convert both shapes: `private lateinit var` → `private val X: T get() = page.X`
  and `private var X: T? = null` → `private val X: T? get() = page.X` (upcast from
  the page's non-null `lateinit` is fine).

### A Filtered Test Run Poisons the Test Count

`./gradlew testDebugUnitTest --tests "SomeClass"` **replaces** the
`app/build/test-results/testDebugUnitTest/` directory with only that class's
XML. A script that sums `TEST-*.xml` right after a filtered run therefore
reports the *filtered* count, and writing that into the CHANGELOG ships a
wrong number.

The failure is silent: the glob succeeds, the sum succeeds, the number is
just wrong (e.g. `18/18` when the suite has 211 tests).

- **Derive the count only from a FULL run.** Sequence: run the whole suite
  (`./gradlew :app:testDebugUnitTest`), then read the XML directory. If you
  ran a filtered test in between, re-run the full suite before quoting.
- **Wipe the directory before a full run** so a stale XML from an earlier
  filtered run cannot be counted:
  `rm -rf app/build/test-results/testDebugUnitTest && ./gradlew :app:testDebugUnitTest`
- **Sanity-check the number against the test tree**: if the suite has 10 test
  classes and the count names 1, the count is filtered, not total.
- The same trap applies to `assembleDebug`: a filtered test run does not
  rebuild the APK, so a byte size quoted after it may be from the previous
  build.

### Merging a Refactor Branch Into the Integration Branch

When the user asks to land a feature branch ("haz el merge") and keep new
work on a separate branch, the sequence is:

1. `git checkout <integration>` then `git pull --ff-only origin <integration>`.
2. `git merge --no-ff <feature> -m "merge: <summary>"` — `--no-ff` keeps the
   group of refactor commits visible in the history instead of flattening
   them into the integration branch.
3. **Verify the merge dropped nothing**:
   `git diff <feature> HEAD --stat` must print **empty**. A non-empty diff
   means the merge resolved something silently — read it before pushing.
4. Re-run the gates on the merged tree (`compileDebugKotlin`,
   `testDebugUnitTest`, `assembleDebug`): the merge is a new tree, and the
   feature branch's green run does not certify it.
5. `git push origin <integration>` and confirm the remote moved
   (`git log --oneline origin/<integration> -1`).
6. **Create the next feature branch from the updated integration branch**
   (`git checkout -b feat/<next>`) so new work continues on top of what was
   landed, not on the old feature tip.

- **Port branch-local fixes to every branch that builds in CI.** A fix for a
  shared problem (a CI pin, a workflow) lives in each branch's own copy of
  the file; landing it on one branch does not protect the others. A merge
  that duplicates the same patch on two branches is expected — Git resolves it
  when the content matches.
- **Do not amend a merge commit's message repeatedly** — after a push, the
  message is history. Fix a typo in the merge message *before* pushing, with
  `git commit --amend -F <file>`.
- **Write the merge message to a file, not to `-m`.** A message that contains
  double quotes (`params_backend = "disk"`) is eaten by the shell, so git
  receives a stray argument and refuses the merge ("a - not something we can
  merge"). Use `git merge --no-ff <branch> -F /tmp/merge-msg.txt`.

### Changelog on Every Push (user rule)

This user wants a `CHANGELOG.md` in the repo updated **in the same push** as the
refactor, so change tracking lives next to the code. Format: Keep a Changelog
(`## [Unreleased]` → `### Refactor` / `### Added` / `### Fixed` / `### Verified`),
with the commit SHA and the on-device evidence (device, pid, crash-buffer count).
If the file does not exist, create it; then `git add CHANGELOG.md` alongside the
code in the same commit. Never push a refactor without its changelog entry.

**Write every claim in the entry from the tree, not from a summary.** A handoff
summary or a prior session's report can describe a tree that no longer exists —
it may name a function that has since been renamed or quote a test count that is
no longer real. Re-derive each fact before pushing: list the test-results
directory for counts, `ls` every file you name, `grep` every symbol you cite. A
wrong line in a pushed changelog costs its own follow-up correction commit,
which is worse than the verification it skipped.

### Characterizing a Streaming Parser (marker-based splitters)

A parser that watches for a marker in a stream of chunks (LLM reasoning vs answer, SSE frames, protocol headers) is pure logic and deserves the same treatment — but the marker can arrive **split across chunks**, which hides three bug classes: a marker that starts with whitespace searched in a trimmed string, buffer content deleted before it was emitted, and a retention predicate comparing mismatched quantities.

- **Write the characterization test first, and let it report the bugs.** The first run of such a test failed 4 of 18 — and all four failures were real defects in the parser, not wrong expectations. **Commit the failing expectations as the baseline** (with the current behavior asserted and the bug named in the test comment), then fix the parser in a second commit. That keeps "what it did" and "what it should do" as two reviewable steps.
- The three bug classes, the chunk-boundary test cases and the on-device check are in `references/runtime-testing.md`.

### Characterization-First for doSend()/runRound()

`doSend()` (and the `runRound()` agent loop it launches) orchestrate shared
state — `Conversation`, `llamaModel`, `engine`, `attachmentHandler` — so they
must **not** be moved as a unit without coverage. The safe increment is:

1. Identify the **pure, stateless** math inside the function: send-text
   composition (`if fileBlock.isEmpty() text else text + "\n\n" + fileBlock`),
   title fallback (`.take(18)`), `"|"`-split counting, localized-hint assembly.
2. Extract those to an `object XxxLogic` with explicit parameters (no `this`,
   no `Context` — pass already-localized strings in, e.g. `s_329` as a `String`
   so the unit test needs no `R`/Robolectric).
3. Write **JVM characterization tests** that pin the current branches (one test
   per branch) and run them green **before** touching the caller.
4. Only then replace the inline code in `doSend()` with calls to the object.
   Tests stay green ⇒ behavior preserved; the orchestration stays put.

This satisfies "don't extract doSend without characterization" while still
shrinking the function's inline logic. Keep `runRound()` untouched until it has
its own coverage.

### Patch Overlap Creates Duplicates
- When making multiple patches to the same file, patches can overlap if the old_string appears in already-patched code.
- ALWAYS read the file after patching to verify no duplicate lines were introduced.
- If duplicates found: use patch with the duplicated block as old_string and the single block as new_string.
- Compile errors referencing already-patched lines are a signal of overlap — check file content before adding more patches.

### Atomic Multi-Edit of One Large File

Several independent edits to the same file issued as parallel `patch` calls can
lose updates — a later write may clobber an earlier one. Apply a batch of edits
to one file in a single `execute_code` Python pass, all-or-nothing:

```python
import io
p = "app/src/main/java/com/yumenode/ai/MainActivity.kt"
s = io.open(p, encoding="utf-8").read()
edits = [(name, old, new), ...]
bad = [(n, s.count(o)) for (n, o, _) in edits if s.count(o) != 1]
if bad:                      # abort BEFORE writing; file stays pristine
    print("NO APPLY", bad); raise SystemExit(1)
for _, o, n in edits: s = s.replace(o, n, 1)
io.open(p, "w", encoding="utf-8").write(s)
```

- **Assert `count == 1` per edit.** `0` means whitespace/anchor drift; `2` means the
  anchor is not unique. Abort on either — a partial write is worse than none.
- **Use a unique multi-line anchor when a one-line anchor matches twice.** Two
  identical statements at different indentation (the same `setMarkdown(...)` in the
  success path and the cancelled path) both match; prepend the preceding unique
  line (`turn.answer = shown.trimEnd()`) so exactly one matches.
- **In Python, build `new` as a raw string (`r"""..."""`).** Kotlin source that
  contains a literal `\n` escape stays backslash-n; a normal Python string turns
  it into a real newline and corrupts the file.
- **`read_file` dedups per file, not per range.** After one read, a second
  `read_file` for a different line range answers "file unchanged since last read"
  with no content. Fetch the exact lines for `old` with
  `sed -n 'START,ENDP' <file>` in the terminal instead.

### Render-Time Annotations Are Clobbered by the Final Re-Render

Appending an annotation to a rendered `TextView` (a `≈N tok/s` footnote, a
"cached" badge) inside the streaming function is not enough: the caller usually
stores a clean model string and re-renders it at the end, overwriting the
annotation. Keep the persisted string clean, carry the annotation in a field,
and re-append it at the final render:

```kotlin
lastFootnote = foot                                    // set while streaming
markwonFull.setMarkdown(ai.answer, turn.answer + (lastFootnote ?: ""))  // final
```

Verify against the live view, not the code: a `uiautomator dump` of the bubble
either contains the footnote text or it does not.

### Hiding a Widget Does Not Disable It

`view.visibility = View.GONE` only stops drawing; `isChecked`, `text` and the
rest stay readable. If any path keeps reading `checkBox.isChecked`, the hidden
control still drives behavior (a hidden "thinking" toggle left checked kept
enabling reasoning for a non-reasoning model). Gate the *capability*, not just
the visibility — derive an effective value and use it at every read site:

```kotlin
private val thinkingActive: Boolean get() = modelSupportsThinking && thinkCheck.isChecked
// assumeThinking = thinkingActive; enableThinking = thinkingActive; ...
```

Reset the backing preference on model unload so a stale `true` does not leak
into the next model.

### CI: a Commit Step Must Also Push

A release step that runs `git commit` but not `git push` leaves the version bump
only in the ephemeral runner: the workflow reports success and the artifacts
carry the new version, but `origin/main` keeps the old one. Pair the commit with
a non-fatal push (`git push origin HEAD:main || echo "push skipped"`) and, after
any tag release, verify the branch actually moved:
`git fetch -q && git show origin/main:app/build.gradle.kts | grep -E 'versionCode|versionName'`.

The `|| echo` hides a specific and common loss: the runner checks out the **tag**
(detached HEAD), so if any commit landed on `main` after tagging, the push is
rejected non-fast-forward, the workflow still reports success, and the release
ships with the new version while the branch keeps the old one. After the run check
`git log --oneline HEAD..origin/main`; when the tree's `versionName` still reads
the previous release, set it by hand and commit.

### A Release Is the Downloaded File, Not the Green Run

Three rules that decide whether a published release actually matches the source:

- **The app's `versionCode` must equal the versionCode the tag derives.** The release workflow computes it from the tag (`1.4.0` → `major*10000 + minor*100 + patch` → `10400`). If the tree says something else, the published APK reports a version the source does not contain, and only a user comparing the install screen with the repo notices.
- **Verify the artifact you downloaded, not the build log.** `apksigner verify --print-certs` for the signature and `aapt2 dump badging` for `versionName`/`versionCode`. `gh release download` fails outside a git clone — take the asset URL from `gh release view --json assets` and `curl -sL` it.
- **Replace the auto-generated release body.** The default is a bare compare link; write the real notes with `gh release edit <tag> --notes-file <file>`, including the measured numbers and the diff link.

A release APK **will not install over the debug build** — the signing keys
differ, so `adb install -r` fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`.
Uninstall first, and say so when handing the artifact over.

The full tag → CI → download → verify → notes procedure lives in the
`android-build-troubleshooting` skill, under its release-publishing
reference.

### Dead Code Detection (before deleting anything)
- Count external references before deleting a property or method:
  `grep -rn '\b<symbol>\b' app/src/main/java/` then filter out the declaring file. Zero external references = safe to delete.
- **Zero *external* references is not zero references.** A member can be dead to
the rest of the tree yet still called by a *sibling* member of the same class —
deleting it then breaks that sibling. Before removing, grep the declaring file's
own body for the symbol too (ignoring the definition line). A shared layout helper
(`matchWrap`/`wrapWrap`) looked dead from outside, but `numField` called
`matchWrap(context)` internally, so removing it broke the build — inline the call
(`LinearLayout.LayoutParams(...)`) instead of deleting blind.
- **Assume a duplicated helper is triplicated.** Before treating a formatter as
single-source, `grep -rn '\bfmtSize(' app/src/main/java/` — the same function lived
in the Activity, a Page and a Handler at once. Consolidate to one owner and repoint
call sites with a lookbehind that keeps dotted calls out
(`(?<![\w.])fmtSize\(` → `UiHelpers.fmtSize(`).
- Typical finds: `Regex` properties left behind after parsing moved into a scanner; an encode/decode helper duplicated in the manager while the Activity already delegates to another class; a UI build that the manager and the Activity both implement (the Activity copy is the dead one).

### chatPrefs() Visibility
- When manager takes lambda provider for prefs, Activity's `chatPrefs()` may need to be `public` (or `internal` in Kotlin)
- Other managers (ApiService, ThemeManager) may also need access to the same prefs file
- Check existing access level before extraction: `grep -n "fun chatPrefs" MainActivity.kt`
- If private → change to internal/public before patching manager call sites

### Deduplicating UI Helpers (UiExt.kt)
- Extract shared helpers as `Context` extensions in one file: `Context.dp()`, `Context.toast()`, `Context.rounded()`, `Context.matchWrap()`, `Context.wrapWrap()`. Define each once instead of once per Activity/Page/Handler.
- Inside an Activity (a `Context` subclass) the extension resolves through the implicit `this`, so call sites stay `dp(16)` unchanged. In a SUBPACKAGE class the same call fails with `Unresolved reference 'dp' on receiver of type 'Context'` — add explicit imports (`import com.litertchat.app.dp`).
- A manager class holding a `context`/`activity` field must call it explicitly: `context.dp(...)`, `context.rounded(...)`.
- `GradientDrawable.cornerRadius` is in PIXELS. A shared `rounded(color, radiusDp, ...)` must multiply by `resources.displayMetrics.density`; a copy that passes the dp value straight through renders a far smaller radius than intended.
- When unifying two variants, prefer the superset signature: `matchWrap(top: Int = 0)` covers both the no-arg call sites and the ones passing a top margin.

### Audit the Native Runtime's Knobs — a Knob You Never Call Is Off

A native runtime ships tuning knobs (cache quantization, thread counts, GPU
layers, prefetch). If the app never calls the setter, the runtime silently
uses its own default. Before answering "is X active?", grep the app for the
**API call**, not for the feature name.

```bash
# what the app actually enables
grep -rn "setCacheType\|withCache\|setThreads\|setGpuLayers\|setKeep" app/src/main/java/

# what the runtime offers (an AAR is a jar of classes + a .so)
cd /tmp/aar && unzip -q -o <aar> && unzip -q -o classes.jar -d cls
javap -p cls/net/ladenthin/llama/parameters/ModelParameters.class | grep -i cache
```

What the llama.cpp binding (`net.ladenthin:llama-android`) exposes, and what
leaving it unset costs:

| knob | API | default when unset | cost of leaving it |
|---|---|---|---|
| prompt cache | `InferenceParameters.withCachePrompt(true)` | on | re-prefills the history every turn |
| KV cache quantization | `ModelParameters.setCacheTypeK/V(CacheType.Q8_0)` | **F16** | 2x the RAM of the KV cache — gigabytes at 32k context |
| threads | `setThreads` / `setThreadsBatch` | runtime default | must stay user-selectable |
| GPU layers | `setGpuLayers(n)`; `-1` = all | 0 = CPU | the GPU path is never taken |
| keep (`n_keep`) | `setKeep(n)` | 0 | **NOT** the prompt cache: it is "tokens pinned from the initial prompt" |

- **Do not confuse `setKeep` with the prompt cache.** `n_keep` pins leading
  tokens; the prompt cache is `cache_prompt` / `withCachePrompt`.
- **Quantize the KV cache by default (`Q8_0`).** It is llama.cpp's own
  recommendation, halves the cache RAM, and the loss is not visible. F16 is
  the default when the setter is never called — the silent trap: the app
  looks tuned and is not.
- **Expose the quantization as a setting** (Q8_0 / Q4_0 / F16) so the user
  can trade RAM for quality. It only applies at the next model load, so say
  so in the hint text.
- **Detect the backend at runtime instead of assuming it.**
  `LlamaModel.getLlamaCppBuildInfo()` returns the compile-time backend list,
  so `"VULKAN" in info` is the only honest test for "the GPU path will
  actually run". It also lets the UI say "this runtime has no GPU backend"
  rather than leaving the user waiting for an acceleration that never comes.
- **A GPU toggle whose path kills the process must be visibly inert, not
  absent.** A native SIGSEGV is below the JVM: no `try/catch`, no
  `runCatching`, no fallback can save the app once the driver dereferences a
  null pointer. So when the GPU path is not yet verified on the target
  device, keep the control in the UI (the user asked for it) but make it
  **not activate the path**, and say why. Gate it on one named flag
  (`GGUF_GPU_EXPERIMENTAL`) so re-enabling it is a one-line change, and
  distinguish the two reasons in the message: "this build has no Vulkan
  backend" versus "the GPU path is still experimental and is off for now".
  Asking for GPU and running on GPU are different claims — the status line
  must report what actually happened.
- **A quantized KV cache pulls the cache onto the GPU.** llama.cpp only
  supports a non-F16 `type_k`/`type_v` together with flash attention, and the
  cache is then allocated on the device. So in a runtime that HAS a GPU
  backend, turning on Q8_0 is what makes the compute path use the GPU — a
  plain CPU generation then fails with a GPU error
  (`vk::Device::createComputePipeline: ErrorUnknown`). When you enable the
  quantization, re-verify generation on a CPU-only runtime, and keep the two
  switches independent: a quantized cache is a RAM win, a GPU backend is a
  speed win, and neither implies the other.

### Adding a Native GPU Backend to an Android .so

Shipping a GPU-enabled native runtime (ggml + Vulkan/OpenCL) is not "flip a
CMake flag and ship it". Each of these has cost a full session:

1. **A Vulkan-Hpp dispatcher initialised with only the INSTANCE leaves the
   DEVICE functions NULL.** `DispatchLoaderDynamic::init(VkInstance)` loads
   the instance-level entry points; `vkWaitSemaphores`, `vkCreateBuffer`,
   `vkGetBufferDeviceAddress` stay at 0 and the first call jumps through a
   null pointer → SIGSEGV with `fault addr 0x0`. Initialise it with the
   device too (`init(VkInstance, PFN_vkGetInstanceProcAddr, VkDevice)`).
   Check the Vulkan-Hpp version: from 1.4.x the `vk::Device` resolves through
   the *global* dispatcher (so re-initialising the global fixes it), while
   1.3.x **copies** the dispatcher into the Device (so it does not).

2. **A driver can advertise a feature it does not implement.** Some drivers
   report `bufferDeviceAddress` but do not export `vkGetBufferDeviceAddress`;
   `getBufferAddress()` then calls a null pointer. Check the function pointer
   with `vkGetDeviceProcAddr` before trusting the feature, and turn the
   feature off when it is missing — every use of it is already guarded by
   `if (device->buffer_device_address)`, so flipping the flag is enough.

3. **The NDK ships only the C Vulkan header, and its version is frozen.**
   Every NDK 27/28/29 carries `vulkan_core.h` 1.3.275, so `vulkan.hpp` must
   be the matching Vulkan-Hpp — the newer one asserts `VK_HEADER_VERSION`
   against the C header and refuses to compile against the NDK's. The NDK
   *does* ship `glslc` and the SPIRV headers, so ggml-vulkan cross-builds
   without the Vulkan SDK: point `Vulkan_GLSLC_EXECUTABLE` at the NDK's
   `glslc` and generate a minimal `SPIRV-HeadersConfig.cmake` (the CMake
   package ggml-vulkan looks for) pointing at the NDK's
   `spirv-headers/include`.

4. **A modern NDK breaks old JNI casts.** `JavaVM::GetEnv` takes `void**`
   while `AttachCurrentThread` takes `JNIEnv**`, and `JNIEnv_` does not
   exist (the class is `_JNIEnv`). A C-style `(void**)&env` compiles for one
   call and not the other; `JNIEnv_` needs `-DJNIEnv_=_JNIEnv`.

5. **Adding a backend to a shipped .so is NOT inert for code that never
   asked for the GPU.** A Vulkan-enabled runtime made plain CPU chat
   generation fail (`createComputePipeline: ErrorUnknown`) because the
   KV-cache quantisation forces the compute path onto the GPU. After adding
   a backend, re-verify **every** path that uses that library — not only the
   one the backend was added for.

### Debugging a Native SIGSEGV: Resolve the PCs

- `adb logcat -d -b crash` carries the backtrace with one PC per frame.
- Resolve them against the **unstripped** library: keep a copy *before*
  `llvm-strip --strip-all` (the shipped copy loses the symbols) and run
  `llvm-addr2line -f -C -e <unstripped.so> 0x<pc> …`.
- The library you resolve against must be the one that was actually
  installed: extract it from the APK
  (`unzip -p app.apk lib/arm64-v8a/libfoo.so`) and `cmp` it with the build
  output. A Gradle module or a local Maven artifact whose **version did not
  change** can be served from the cache with older bytes.
- **A build that only prints "Linking" did not recompile your change.**
  `cmake --build` skips a translation unit whose `.o` is newer than the
  source; confirm the output says `Building CXX object … .o`, and `touch`
  the source when the timestamps are wrong. Debugging a binary that never
  contained your fix costs a whole cycle.
- A crash in the *other* engine of a shared control is usually your own
  test's leftover state: a global "Backend CPU/GPU" spinner that drives
  several engines means a test that flips it for one path silently changes
  the next path. Reset the control to its default before testing the next
  engine, and suspect it first when a path crashes that "worked yesterday".

### Make a Big SD Model Fit on the Phone: Disk Weight Residency

A phone cannot hold a whole Stable Diffusion pipeline in RAM. The engine
already models the parts (`ModelComponent::Conditioner`, `::Diffusion`,
`::VAE`) and already knows how to keep only the active one resident
(`ResidencyMode::Disk` releases the params block of a component whose
`pin_count` is 0, while the file stays mmapped). The app just never turns
it on: the JNI sets `enable_mmap = true` and leaves `params_backend` empty,
so every component stays in RAM.

- `sd_ctx_params_t.params_backend = "disk"` is the one-line switch; it
  changes the peak from "the sum of the components" to "the largest one"
  (FLUX: 21.4 GB → 11.2 GB; SD 1.5: 2.11 GB → 1.70 GB).
- Ship it as a user switch, not as the default: if the page cache cannot
  hold the active component, the pages come from storage and the
  generation slows down.
- Plumbing a JNI flag means changing the `nativeCreate` signature in
  Kotlin **and** the JNI function signature together, or the first model
  load throws `NoSuchMethodError`.
- **Verify the peak actually drops** (`dumpsys meminfo` with the mode on
  and off) and that the UNet is released between denoising steps — the
  UNet runs every step, so if it stays pinned the mode is a no-op.

The component model, the JNI plumbing, the per-family memory table and the
device checks are in `references/drawing-engine-memory.md`.

### Build Verification Commands
- Quick check: `./gradlew :app:compileDebugKotlin --no-daemon -q`
- Full APK: `./gradlew assembleDebug --no-daemon -q`
- Filter output: pipe through `grep -E "BUILD|FAILED|error:"`

### Tests Compile `main` First
- `./gradlew testDebugUnitTest` compiles the `main` source set before any test runs. On a dirty tree, a broken in-progress refactor fails at `compileDebugKotlin` and you never see a test result — so run `compileDebugKotlin` first and fix source errors before interpreting the test task.

### Testing a Handler That Launches Coroutines

A handler that does `scope.launch { … }` needs the coroutines test artifact
(`kotlinx-coroutines-test`) and an explicit `advanceUntilIdle()` after the
call, or every assertion sees an empty world. Make the handler generic in the
payload type so the test does not need an Android type (`android.net.Uri` is
a stub in `android.jar` and its constructor is package-private).

The full recipe — the `runTest`/`advanceUntilIdle` shape, why asserting the
call ORDER is what catches a refactor, and the three Android stubs a JVM test
hits first — is in `references/runtime-testing.md`.

### Extracting a Handler + Host Interface Pair (non-page example)

When the extracted block is logic, not a UI page, use the same host-interface
shape as `ChatImageHandler`/`ChatImageHost`:

```kotlin
class ChatImageHandler(
    private val ctx: Context,
    private val scope: CoroutineScope,
    private val host: ChatImageHost,
) { /* uses only host.xxx */ }

interface ChatImageHost {
    val visionOk: Boolean          // mutable → override var in Activity
    val palette: PonkoTheme
    val pendingImageCount: Int
    val maxAttach: Int
    fun toast(msg: String)
    fun showImageFullscreen(bmp: Bitmap)
    fun showImageMenu(bmp: Bitmap, name: String)
    fun onQuoteImage(bmp: Bitmap)
    fun onRequestStoragePermission(granted: (Boolean) -> Unit)
}
```

- Declare **every** member the extracted class touches on the host interface —
  omitting one produces `Class 'MainActivity' is not abstract and does not
  implement abstract member` for each missing item, which the compiler reports
  by member name, so you can resolve them one at a time but it is cheaper to
  grep the extracted class for every `host.` reference and list them up front.
- For a mutable property that the Activity owns and the handler only reads,
  declare it as a plain `val` on the interface and a real `var` on the Activity
  with an `override`; the handler reads it via the interface, the Activity
  updates its own backing var.
- For a mutable property the handler needs to set (rare), make the interface
  property an `override var` with a custom setter on the Activity that
  delegates to the right backing object (e.g. `VisionManager`).

### Color alias delegation (from ThemeManager refactoring)

When colour-accessor properties such as `C_PRIMARY`, `C_BG`, `C_TEXT` already
exist on the Activity and you move their *source* to a manager, delegate the
Activity accessors to the manager instead of removing them:

```kotlin
// Activity — keep same name so call sites don't change
val C_PRIMARY get() = themeManager.primary

// ThemeManager — holds the real accessor
val primary: Int get() = pal.primary
```

- Do **not** place the colour properties inside a `var`/`val` initializer block
  or getter body; Kotlin rejects initializers for properties that have no
  backing field — you get `Initializer is prohibited here because this property
  has no backing field`. Keep them top-level members of the class.
- `remove` is a valid action in this environment.
- Keep names identical (`C_PRIMARY`, not `primaryColor`) so that the bulk of
  call sites (`view.setBackgroundColor(C_BG)`, `setTextColor(C_TEXT)`) compile
  without edits.
- When the extracted manager exposes the palette value directly (e.g.
  `themeManager.primary`), the Activity accessor is a one-liner delegate; no
  logic is lost.

### Duplicate class detection after extraction

When a nested or top-level class (e.g. `ZoomImageView`, `AiArea`) is moved to a
new file, **delete every other copy in the same commit**. Leaving two top-level
copies causes `Redeclaration: class X` at compile time (a nested `private` copy
does not collide by itself, but a second top-level copy does).

**Grep the whole tree, not just the file you are extracting from** — the
conflicting copy often lives in an unrelated file. `ZoomImageView` existed both
as a nested `private` class in `MainActivity` and as a top-level class in
`ChatImageHandler`, so extracting from `MainActivity` alone still collided with
the new top-level file. Before compiling:

```
grep -rn '\bclass ZoomImageView\b\|\bclass AiArea\b' app/src/main/java/
```

and confirm exactly one definition survives.

### Rebrand / Namespace Gotcha
After renaming the package and `applicationId`, the rename does NOT touch every
identity carrier in the tree. The refactor's rename touched `.kt`/`.cpp`/tests
and the manifest, but these survive and must be swept separately:

- **Native libraries** keep their old basename at runtime (`libponko_sd.so` still
  loads with the name `Ponko` even after `com.yumenode.ai`). The in-app update
  checker that reported a newer version lived behind that native identity, not
  any Kotlin URL — so the "new version" notice can fire from the old/upstream repo.
- **Hardcoded URLs in Resources/UI** (`SettingsPage.kt` About links still pointed
  to `github.com/visitor257/Ponko` after the rebrand to `cjml555/Yumenode-AI`).
- **String resources** (`s_009` "2 loading native library (libponko_sd.so)").

Sweep rule: after any package/brand rename, `grep -rn` the tree for the OLD
identity token(s) across `*.kt`, `*.cpp`, `*.h`, `*.xml` (strings + manifest),
`*.properties`/`*.md`, and list the resulting `.so` basenames. Treat a hit in
a compiled artifact as a runtime identity, not a dead string.

## References

- `references/wrapper-elimination.md` — removing one-line delegation wrappers: pre-flight wiring check, post-elimination dead-code sweep, wrapper inventory for this codebase.
- `references/junit4-nullable-patterns.md` — writing JUnit4 assertions against nullable-returning Kotlin.
- `references/device-ui-automation.md` — driving the app over ADB for the device gate: deriving tap coordinates from the UI dump instead of guessing, the bottom nav that moves when the keyboard opens, why Enter does not send, reading app-private state with `run-as`, and probing the local HTTP API from the host.
- `references/runtime-testing.md` — depth for four shapes: moving a deeply coupled method as an Activity extension, characterizing a marker-based streaming parser, testing a handler that launches coroutines, and pinning an OpenAI-compatible API contract.
- `references/tech-evaluation.md` — answering a "can we add X?" request: audit the classpath and the acceleration flags first, separate the goal from the proposed mechanism, cost the options in lines and weeks, verify ecosystem claims against the registry, and end with one recommendation instead of a survey.
- `references/drawing-engine-memory.md` — making a big Stable Diffusion model fit on a phone: the engine's component model, `params_backend = "disk"` (sequential weight residency), the JNI plumbing and the device checks that prove the peak really drops.
- `scripts/measure-app-memory.sh` — one command to print an app process's PSS / RSS / SWAP and native heap, the numbers to compare when a change claims to save memory. Invoke it as `bash scripts/measure-app-memory.sh <pkg> "<label>"` (the file may not carry the executable bit).

## El usuario prefiere español neutro, kawaii, y formato conciso.