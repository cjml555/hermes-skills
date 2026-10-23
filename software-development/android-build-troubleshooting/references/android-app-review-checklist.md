# Android App Review Checklist

Use when reviewing an Android project's build configuration, CI workflows, or code changes. Ordered by blast radius (build-breaking first).

## 1. Build-blocking checks (do these first)

- [ ] **NDK version match** — read `ndkVersion` in `gradle.properties` or `app/build.gradle.kts`, then `ls $ANDROID_HOME/ndk/` to confirm it exists. A missing NDK causes native build failures with misleading CMake errors.
- [ ] **SDK location** — verify `local.properties` has `sdk.dir=`, and `$ANDROID_HOME` matches it. Case mismatches (`sdk` vs `Sdk`) cause silent failures.
- [ ] **compileSdk / targetSdk / minSdk** — read from `build.gradle.kts`, verify platforms are installed (`ls $ANDROID_HOME/platforms/`).
- [ ] **Signing config** — if release builds are expected, verify keystore exists and `KEYSTORE_PATH` / env vars resolve to real files.

## 2. CI workflow checks

- [ ] **NDK installation step** — every workflow that runs a build must install the required NDK version. `actions/setup-java` alone is NOT sufficient for projects with `externalNativeBuild`.
- [ ] **Action versions** — pin actions to major version tags (`@v4`, `@v6`), never to floating tags. Check for deprecated action warnings.
- [ ] **Test execution** — workflows should run `./gradlew test` or `./gradlew testDebugUnitTest` before building.
- [ ] **Artifact upload** — verify artifact paths match actual build outputs (`build/outputs/apk/`, `build/outputs/bundle/`).

## 3. Code review checks

- [ ] **Test coverage for new/modified code** — for every new public function or refactored class, check `app/src/test/` for corresponding test methods. Use `grep` to search for function names in test files.
- [ ] **Import cleanup** — refactored files should have unused imports removed. Check for orphaned imports with a quick `grep` for the old utility class.
- [ ] **Duplicated logic** — when utilities are extracted, verify no duplicate copies remain in other files. Common with token estimation, file I/O, and UI helpers.
- [ ] **API compatibility** — when changing types (e.g., `Pair` to `LamaPair`), verify the new type is imported and the old one is fully removed.

## 4. Reporting format

Structure findings by severity:
- **CrITICAL** — build will fail (NDK mismatch, missing SDK, broken signing)
- **Quality** — code works but needs attention (missing tests, duplicated logic, import cleanup)
- **Good** — acknowledge what was done well (clean separation, good comments, solid tests)

End with actionable recommendations the user can accept or decline.