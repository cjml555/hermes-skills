---
name: android-build-troubleshooting
description: Use when an Android/Gradle build fails to resolve.
license: MIT
metadata:
  version: "1.0.0"
  category: software-development
---

# Android Build Troubleshooting

Scope: getting `./gradlew` to actually produce an APK. For Kotlin/Compose/Material design work, load `android-native-dev` instead — this skill only covers the build failing to start or resolve.

## Always-on rules

- Never pass `--offline` on a first build attempt. It converts "dependency not downloaded yet" into a wall of `No cached version of X available for offline mode` errors that look like version conflicts but are not.
- Before diagnosing anything, print the toolchain facts: `ANDROID_HOME`, `ANDROID_SDK_ROOT`, `local.properties`, and the contents of every directory under `~/Android`. The dominant failure on this machine is two SDKs that differ only by letter case.
- Configure the SDK location through exactly ONE mechanism: `ANDROID_HOME` alone in the shell plus `sdk.dir` in `local.properties`; `unset ANDROID_SDK_ROOT`.
- Long builds run with `terminal(background=True, notify=True)`. Use the wait to ask the user a scoping question about the next task instead of idling.
- `BUILD SUCCESSFUL` proves the build ran, not that the artifact is correct. When the task changed what gets packaged (a new locale, a new resource dir, a manifest entry), inspect the built APK before reporting done.
- **Never run two builds against the same project directory at the same time.** Gradle and the Kotlin compile daemon both write into `build/`. When your own build, a worktree-merge build and subagent builds overlap, they interleave writes into the same incremental state and the loser reports hundreds of errors that no single build would produce. Stop the other builds before diagnosing anything.
- **The parent runs the authoritative build after any subagent fan-out that edits source.** Subagent build claims are not evidence; see `codebase-bug-audit`. Compile once, yourself, with no other daemon alive, over the whole merged tree.
- **Measure a cache speedup by deleting the build directory between runs, not by re-running without it.** A second plain re-run is `UP-TO-DATE` and tells you nothing. `./gradlew <task>` after `rm -rf build/` is the only pair of numbers that compares the same work.
- **Never report a version control ref that a rebase/force-push moved.** After amending or force-pushing, re-read the SHA — a SHA quoted from before the amend is stale and points at an object the reader can no longer reach.
- **A helper script must read the project's pinned toolchain version, not "the newest installed".** `ls -d "$SDK"/ndk/*/ | sort -V | tail -1` silently diverges from the `ndkVersion` the build system actually uses, and the resulting mismatch surfaces as a build error that never mentions the NDK. Read the pin from `app/build.gradle` / `gradle.properties` and pass it through.
- **A green rebuild does not mean your native edit was compiled.** CMake re-links when the source's mtime is older than the object file, so a patch to a native source is silently skipped and the binary keeps the old code — the classic "I applied the fix and nothing changed". Read the build log for the compile line of the file you touched (`Building CXX object …/foo.cpp.o`); `Linking …libfoo.so` on its own means it was not rebuilt. `touch <source>` to force it.
- **Find out which build path actually produced the artifact before "fixing" a script.** A project with `externalNativeBuild` compiles its native code as part of the Gradle build; a helper script that stages `.so` into `jniLibs/` is a *parallel* path, not the one that made the APK. A disagreement between them is a mismatch to report, not a broken build — and the existing artifact stays valid. Confirm with `unzip -l <apk> | grep '\.so$'` and the NDK recorded in the build's own CMake cache (`grep ANDROID_NDK app/.cxx/Release/*/arm64-v8a/CMakeCache.txt`).

## Procedure

1. Locate the project and read its requirements: `gradle.properties` for `compileSdkVersion` / `ndkVersion`, and `app/build.gradle` for flavors and native build hooks. Match the required platform/build-tools/NDK against what is actually installed before running anything.
2. Inventory the SDK dirs: `ls ~/Android`, then list platforms/build-tools/cmdline-tools/ndk in each. On a case-sensitive Linux filesystem `~/Android/sdk` and `~/Android/Sdk` are two independent, partially-populated SDKs — a build configured against the wrong one fails on missing platform or missing NDK.
3. Unify on one canonical SDK: keep the directory that already has the platform, build-tools and NDK the project needs, then symlink the packages the other one uniquely owns into it (`ln -s ../Sdk/<pkg> <pkg>` for `emulator`, `system-images`, …). Verify with `ls -la`.
4. Write `local.properties` with `sdk.dir=<canonical sdk>` so the build is independent of shell state.
5. Fix the shell profile: point `ANDROID_HOME` at the canonical SDK, `unset ANDROID_SDK_ROOT`, and put that SDK's build-tools on `PATH`. Tell the user to reload the shell.
6. Run the build: `ANDROID_HOME=<sdk> ANDROID_SDK_ROOT= ./gradlew :app:assembleDebug` in the background, then read the real tail of the output.

## Speeding up a slow build

A build that recompiles everything from zero each time is usually one or two
settings, not a slow machine. Check these three in order.

1. **`org.gradle.caching=true` in `gradle.properties`.** This is the gate. A
   `buildCache { local { … } }` block with the flag absent does **nothing** —
   Gradle logs `Build cache is disabled` once per task and writes no entries, so
   the directory never even appears. Read the flag, not the presence of the
   directory, to decide whether caching is on.
2. **The `buildCache` block belongs in `settings.gradle`.** It is a method of
   `Settings`, not of `Project`; in `build.gradle` it fails with `Could not
   find method buildCache()`. `removeUnusedEntriesAfterDays` is not accepted by
   `DirectoryBuildCache` in every Gradle version — drop it rather than fight it.
3. **`resolutionStrategy.cacheChangingModulesFor 0, 'seconds'` disables
   dependency caching** across every repository in the project, forcing
   re-resolution of all changing modules on each run. Remove it unless there is
   a documented reason for pinning SNAPSHOT freshness.

Confirm caching is live rather than trusting the config:

```bash
./gradlew :app:compileDebugKotlin --info 2>&1 | grep -c 'Build cache is disabled'
# 0 = enabled; any nonzero count means every task is being skipped
du -sh .gradle-build-cache
```

Then measure. Delete the build directory before each run so both runs do the
same work:

```bash
rm -rf app/build .gradle-build-cache && ./gradlew :app:compileDebugKotlin   # cold
rm -rf app/build && ./gradlew :app:compileDebugKotlin                        # warm
```

For CI, `actions/setup-java` with `cache: gradle` covers `GRADLE_USER_HOME` (the
dependency cache) but **not** a project-local build-cache directory — that needs
its own `actions/cache` entry, or every job recompiles from zero.

## Release signing from CI

Signing errors surface minutes into the build and name the symptom, not the
cause. Resolve the config first, cheaply:

```bash
./gradlew :app:signingReport --console=plain   # resolves the keystore, prints fingerprints
```

- **`SigningConfig "release" is missing required property "storeFile"`.** The
  signing block's guard condition was false — usually because the keystore path
  resolved to a file that does not exist, so the block silently skipped setting
  `storeFile`. It is a **configuration-time** miss reported at packaging time,
  minutes later.
- **A path passed to `file()` inside a Gradle module is relative to that
  module's directory, not the project root.** A build script doing
  `file(jksFile)` inside `app/` and a CI step passing
  `app/release.jks` makes Gradle look for `app/app/release.jks`. The variable is
  named `…PATH`, so both forms get tried; drop the redundant prefix rather than
  patching around it.
- **A guard that logs a warning and continues turns a missing secret into a
  confusing downstream failure.** When a signing config is optional for debug
  builds, make the failure legible: the warning should name the variable that
  was missing and the task that will fail because of it.

Verify the artifact, not the log line: `apksigner verify --print-certs <apk>`
must report the expected certificate digest.

### Signing secrets in GitHub Actions

- **`secrets` cannot be evaluated in an `if:` expression.**
  `if: ${{ secrets.KEYSTORE_BASE64 != '' }}` does not skip the step — the workflow
  fails at parse time, before a runner is allocated. The run reports **0s**, no steps,
  and `gh run view --log-failed` answers `log not found`; read that as a YAML/expression
  error, never as a runner flake. Fix with job-level env indirection:
  ```yaml
  jobs:
    build:
      env:
        HAS_KEYSTORE: ${{ secrets.KEYSTORE_BASE64 != '' }}
      steps:
        - name: Set up signing keystore
          if: env.HAS_KEYSTORE == 'true'
  ```
- **CI needs the keystore file, not only its password.** Store it base64-encoded
  (`base64 -w0 release.jks | gh secret set KEYSTORE_BASE64` — stdin, so the value never
  reaches `ps` or the transcript) and have the workflow decode it into the exact path that
  `keystore.properties` names, writing that properties file in the same step. Both files are
  gitignored, so every run must recreate them from secrets. For a PKCS12 keystore let
  `keyPassword` fall back to the store password instead of adding a second secret.
- **Regenerating the keystore silently invalidates the password secret that pointed at the
  old one.** The build then dies at `:app:packageRelease` — after the whole native compile,
  minutes in — with `KeytoolException: Failed to read key <alias> from store <path>:
  keystore password was incorrect`. Re-sync the secret from the properties file without
  printing it:
  ```bash
  grep '^storePassword=' keystore.properties | cut -d= -f2- | tr -d '\n' | gh secret set KEYSTORE_PASSWORD
  ```
  Then confirm the published asset carries the expected certificate: download the release
  APK and run `apksigner verify --print-certs` on it — a green run alone does not prove the
  artifact was signed with the key you think.

### Reading credentials from `keystore.properties` in `build.gradle.kts`

- **The `java` identifier is shadowed inside `android { }`.** `java.util.Properties()`
  there fails with `Unresolved reference 'util'`, because `java` resolves to the Java
  plugin extension rather than the package. Add `import java.util.Properties` at the top
  of the script and call `Properties()`.
- **A local `val keyAlias` / `val keyPassword` collides with `SigningConfig`'s own
  properties.** Inside `signingConfigs { create("default") { … } }` the receiver already
  declares both, so the assignment reads as reassigning your local and fails with
  `'val' cannot be reassigned`. Prefix the locals (`ksAlias`, `ksKeyPassword`, `ksPath`,
  `ksPassword`) and then assign `keyAlias = ksAlias`.
- **Build the `Properties` object as a plain statement, not inside `apply { load(it) }`.**
  The chained form produces cascading unresolved-reference errors that look like the file
  is unreadable. `val p = Properties(); f.inputStream().use { p.load(it) }` is unambiguous.
- Resolve the file from the root project (`rootProject.file("keystore.properties")`), not
  `file(...)` inside `app/`, and expand a leading `~` yourself — Gradle does not.
- Keep the signing config **conditional** (`if (password.isNotBlank()) config else null`)
  so a machine without the secret still assembles an unsigned APK instead of failing at
  configuration time.

### Creating or replacing a keystore

- **`keytool -genkeypair` will not overwrite an existing keystore.** It tries to open the
  target with the new password first and dies with `UnrecoverableKeyException …
  BadPaddingException: Given final block not properly padded`. Move the old file aside
  before generating (`cp old.jks old.jks.bak && rm old.jks`) and keep the backup: losing
  a published app's signing key permanently blocks updates.
- **A `.jks` extension does not mean JKS.** Modern `keytool` writes PKCS12 by default.
  Check the magic bytes with `xxd -l 4`: `30 82` is PKCS12, `FE ED FE ED` is JKS. AGP
  accepts either.
- Keep the generated password out of the process list: write it to a mode-600 temp file
  and pass `-storepass:file` / `-keypass:file`, then delete the file.
- Verify before building: `keytool -list -keystore <ks> -storepass "$(grep '^storePassword='
  keystore.properties | cut -d= -f2-)"` must list the alias as a `PrivateKeyEntry`.
- **When no stored password opens the keystore, do not guess.** Report that it does
  not match and let the owner correct the file or regenerate the key.

## Publishing a Release and Verifying the Published Artifact

A green CI run is not a release. The release is the artifact the user
downloads, and it can disagree with the source in ways the build log never
shows. The standing rules:

- **The app's `versionCode` must equal the versionCode the tag derives.** Most release workflows compute it from the tag (`1.4.0` → `major*10000 + minor*100 + patch` → `10400`). If the tree says something else, the published APK reports a version the source does not contain, and only a user comparing the install screen with the repo notices.
- **Verify the artifact you downloaded, not the build log.** `apksigner verify --print-certs` for the signature and `aapt2 dump badging` for `versionName`/`versionCode`. A green workflow proves the build ran; only the downloaded file proves what ships.
- **Commit and push before tagging.** A tag on a local-only commit makes the workflow build a tree nobody else can fetch.
- **A release APK will not install over the debug build** — different signing key, so `adb install -r` fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Uninstall first, and say so when handing the artifact over.
- **A green workflow does not mean the branch moved.** A workflow that commits a version bump without pushing leaves the remote on the old version while the release carries the new one. Check the remote, not the run.

The full procedure — the tag/CI/download/verify/notes sequence, and why
`gh release download` fails outside a git clone — is in
`references/release-publish-and-verify.md`.

## Rebuilding a prebuilt native dependency with a GPU backend

A published AAR often ships a **CPU-only** `.so`. When the app needs a GPU
backend, build the native library yourself from the upstream source (the
AAR's POM names the repo and the version tag) with the backend enabled, then
swap the `.so` into a copy of the AAR. The Kotlin API is unchanged, so the
app's call sites keep compiling.

The parts that cost time are not the build command: the engine sources arrive
via `FetchContent` (pre-clone them and apply the upstream `patches/` by
hand), the Vulkan bootstrap needs the NDK's `glslc` plus a hand-written
`SPIRV-Headers` package config and Vulkan-Hpp (the NDK ships only the C
header), and a current NDK broke two JNI signatures the old binding used.

Full recipe — source/version matching, the FetchContent bypass, the Vulkan
bootstrap, the NDK's JNI drift, the Vulkan-Hpp null-dispatcher trap, the
manifest feature the device needs, how to prove a native patch actually
landed, and how to read the crash frame:
`references/native-gpu-backend-build.md`.

## Bumping the NDK version

Changing `ndkVersion` is not a one-line edit on a project that builds native code.

1. Edit `ndkVersion` in `app/build.gradle.kts`, then **delete `app/.cxx/`**. Its CMake cache stores absolute paths to the old NDK; left in place, configure runs against a directory that no longer exists.
2. `./gradlew :app:configureCMakeDebug` — a few minutes, and proves the toolchain, `glslc`, spirv-headers and libomp resolve against the new NDK.
3. `./gradlew :app:externalNativeBuildDebug` in the background — the real compile.
4. `mergeDebugNativeLibs` failing with `2 files found with path 'lib/arm64-v8a/libomp.so'` means `src/main/jniLibs/` still carries a prebuilt `libomp.so` from the old NDK while the CMake build now emits NDK's own. Delete the stale `jniLibs` copy.
5. Replace `jniLibs/.../libc++_shared.so` with the new NDK's and `llvm-strip --strip-unneeded` it — the NDK ships it with debug info (~9 MB; ~1.4 MB stripped).
6. Verify the packaged APK, not the log: `unzip -l app/build/outputs/apk/debug/app-debug.apk | grep 'lib/arm64-v8a'`.

Full command sequence and the CI counterpart: `references/ndk-version-upgrade.md`.

## Pitfalls

- **"Several environment variables and/or system properties contain different paths to the SDK."** Gradle compares `ANDROID_HOME`, `ANDROID_SDK_ROOT` and `sdk.dir` and aborts configuration when they disagree by even one character of case. Fix the env, don't work around it or guess which path "should" win.
- **`Could not resolve <group>:<artifact>:<version>` in a fresh dependency set.** Read the message: if it says `No cached version … for offline mode`, the only cause is that you passed `--offline`. Drop it and let Gradle download.
- **NDK version mismatch** looks like a compile error in native code. Read `ndkVersion` in `gradle.properties` (or `app/build.gradle.kts`) first — the fix is installing or pointing at that exact version, not editing the CMake code. Always verify the required NDK against installed versions (`ls $ANDROID_HOME/ndk/`) before reporting a build failure; a missing NDK version is a 10-second check that saves hours of CMake debugging.
- **CI workflows must install the required NDK explicitly.** `actions/setup-java` with `cache: 'gradle'` only covers the JDK and Gradle dependency cache — it does NOT install the Android NDK. Projects with `externalNativeBuild` (CMake/ndk-build) need an explicit NDK step. Verified recipe: `uses: nttld/setup-ndk@v1.6.0` with `ndk-version: r29` and `link-to-sdk: true` — it downloads `android-ndk-r29-linux.zip` and symlinks it to `$ANDROID_HOME/ndk/<full-version>`, exactly where AGP resolves `ndkVersion`. AGP can also auto-download a missing NDK when a working SDK is present, but the explicit step is deterministic and cached. Check every workflow file for NDK coverage when native code is present.
- **`local.properties` is usually gitignored and absent on a fresh clone.** Its absence is not a bug; create it as part of setup rather than editing build scripts to hardcode a path.
- **A locale can be silently dropped from a green build.** `resConfigs` in the module's `build.gradle` whitelists which locale qualifiers get packaged; a `values-xx/` directory that is not listed merges and compiles cleanly and then never reaches the device. Intermediates under `merged_res/` and `packaged_res/` still contain it, so those directories prove nothing — check the APK with `aapt2 dump badging <apk> | grep locales`. Details in the `app-localization` skill.
- **Incremental builds hide changes made while a build was running.** A background build that started before you wrote the new resources reports success without ever seeing them. Re-run the build after the edit, or the APK is stale.
- **`Duplicate resources` at `:app:mergeDebugResources` means the same `name` is defined twice in one locale.** Android merges every `values-*/` file in a locale into one namespace, so a key added to `strings.xml` that already exists in a sibling like `avnc_strings.xml` is a hard error, not a warning. `grep -rn 'name="KEY"' app/src/main/res/values-xx/` names both sites. Common when backfilling a locale from an audit report that only inspected one file.
- **An opaque numeric resource name that "looks free" is usually taken.** With generated names (`s_520`, `s_521`), the next unused number is rarely the next one: the file's numbering is sparse and other names are already bound to unrelated strings. A duplicate inside ONE file fails at `:app:packageDebugResources` with `Found item String/s_521 more than one time` — a different task from the cross-locale merge above, and it also breaks the existing call site that already used that name. **List the free numbers before adding one:**
  ```bash
  python3 - <<'EOF'
  import re, io
  s = io.open('app/src/main/res/values/strings.xml', encoding='utf-8').read()
  used = {int(m) for m in re.findall(r'name="s_(\d+)"', s)}
  print('max:', max(used), 'libres:', [n for n in range(max(used), max(used) + 8) if n not in used])
  EOF
  ```
  Grep the whole `res/` tree for the chosen name, not just `values/strings.xml`, and grep the Kotlin sources for the same `R.string.<name>` to see whether the number is already in use for something else.
- **A grep that pipes a command's output to an interpreter, or that chains a mutating command with `&&`, can be blocked by the security scanner.** This is the harness being cautious, not a broken tool. Split the work into separate steps — read the file with the file tools, run the mutation alone, then verify — rather than trying to rephrase the compound command.
- **A lone `Unresolved reference 'X'` for a member that provably still exists is a stale Kotlin compile cache, not a code defect.** When a single property/method reports unresolved (e.g. `pal.softBtn` → `'softBtn' not found`) but `grep` shows the data class declares it, the incremental compiler is compiling against a stale symbol table — often after a rename or a data class grew new members. Do NOT edit the code to "fix" it: `./gradlew clean` then rebuild collapses the false errors to the genuine set (possibly zero). Diagnose order — `search_files` for the symbol first; if the source declares it, run `clean` before touching any file.
- **Isolate whether an in-progress refactor caused a build error at all: `git stash` + rebuild.** If the identical error reproduces on the clean committed tree, it is environmental or stale cache, not your change — unstash and `clean` instead of blaming/editing your extraction. This stops you "fixing" a phantom (e.g. adding properties that already exist) and burning effort on a cache artifact.
- **A wall of errors in files nobody touched is a build-contention symptom, not a code defect.** The signature: 100+ errors spread across files that `git status` reports as unmodified, with a root cause like `Unresolved reference 'databinding'` or `Cannot access 'val File.root'` in code you have never edited. Generated sources for those files exist on disk — check before assuming they were lost. The cause is concurrent daemons sharing `build/`, not the source. Recover with `./gradlew --stop`, kill stray `KotlinCompileDaemon`/`GradleDaemon` processes, then rebuild with `--no-build-cache --rerun-tasks` to force a cold compile. Expect the count to collapse from hundreds to the handful of genuine errors, and only then read them.
- **StringFormatMatches lint error blocks the build.** `getString(R.string.X, intArg)` where `strings.xml` declares `%1$s` for an integer argument fails lint with "Suspicious argument type for formatting argument." Fix the format specifier in `strings.xml` (`%1$s` → `%1$d` for integers) — the Kotlin call is correct, the string resource declaration is wrong. Check every locale file (`values-*`) that declares the same key; each can carry its own specifier mismatch.
- **lint `abortOnError` blocks builds on pre-existing errors.** Existing string-format mismatches across many `values-*/strings.xml` files abort `:app:lintDebug` before packaging. Set `lint { abortOnError = false }` in `app/build.gradle.kts` so lint reports do not block CI or device deployment.
- **CMake minimum version below 3.10 triggers deprecation warnings.** The NDK toolchain warns when `cmake_minimum_required(VERSION ...)` is below 3.10 and may remove compatibility in future CMake. Update all `CMakeLists.txt` files to `>=3.14` to clear the warning.
- **`./gradlew clean` deletes the APK while a build runs.** Inspecting `build/outputs/` during or right after a clean build races the packaging task and yields "file not found". Wait for the build to finish before reading the artifact.

## Reporting

State which SDK was chosen and what was symlinked, then the build result with the artifact path. If the build is still running when you reply, say it is running — never report success you have not seen in output. When the build changed what ships, quote the evidence from the artifact (locale list, resource count) rather than the build log line.