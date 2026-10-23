# Publishing an Android release and verifying the published artifact

A green CI run is not a release. The release is the artifact the user
downloads, and it can disagree with the source in ways the build log never
shows. Publish it, then read it back.

## 1. The version in the tree must equal the version the tag derives

Most release workflows compute `versionCode` from the tag
(`1.4.0` → `major*10000 + minor*100 + patch` → `10400`) so every build of the
same tag is reproducible. If the app's own `versionCode` differs, the
published APK reports a version the tree does not contain — and the mismatch
only surfaces when a user compares the install screen with the repo.

```bash
# what the tree says
grep -E "versionCode|versionName" app/build.gradle.kts
# what the tag derives
awk '{printf "%d%02d%02d\n", $1, $2, $3}' <<< "1.4.0"
```

Set both to the same numbers, in the same commit the tag points at.

## 2. Commit and push before tagging

The tag must point at a commit already on the remote. Tagging a local-only
commit makes the release workflow build a tree nobody else can fetch.

```bash
git add -A && git commit -m "chore: version X (CODE)"
git push origin main
git tag -a v1.4.0 -m "Release 1.4.0"
git push origin v1.4.0
```

## 3. Wait for every run the tag triggers

A tag usually triggers two workflows: the ordinary CI (build + tests) and the
release workflow (build + sign + publish). Watch both to completion and read
the real conclusion, not the queued state.

```bash
gh run list --workflow ci.yml --limit 3
gh run list --workflow release.yml --limit 3
gh run view <run-id> --json conclusion,status
```

## 4. Download the asset you are going to ship

`gh release download` resolves the repository from the git working directory
and fails outside a clone (`failed to run git: fatal: not a git repository`).
Take the asset URL and fetch it directly:

```bash
URL=$(gh release view v1.4.0 --json assets --jq '.assets[] | select(.name | test("apk$")) | .url')
curl -sL -o app-release.apk "$URL"
ls -l app-release.apk
```

## 5. Verify the downloaded artifact, not the build log

```bash
apksigner verify --print-certs app-release.apk        # signature + subject
aapt2 dump badging app-release.apk | grep -E "versionName|versionCode"
```

The certificate subject must be the expected one and `versionName` /
`versionCode` must match the tree. A green workflow proves the build ran;
only the downloaded file proves what ships.

## 6. Replace the auto-generated release body

The default body is a compare link and nothing else — it tells a reader
nothing about the release. Write the notes and set them:

```bash
gh release edit v1.4.0 --notes-file /tmp/release-notes.md --title "Release 1.4.0"
```

Put the user-visible changes in it, with the numbers you measured (memory
saved, throughput, test count) and a link to the full diff.

## Pitfalls

- **The release APK will not install over the debug build.** Debug and
  release are signed with different keys, so `adb install -r` of the release
  over an installed debug build fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`
  (signatures do not match). The package manager treats them as different
  apps: uninstall first (`adb uninstall <pkg>`), and say so when handing the
  artifact over — otherwise the install looks like a broken release.
- **A green workflow does not mean the branch moved.** A workflow that
  commits a version bump without pushing leaves `origin/main` on the old
  version while the release carries the new one. Verify the remote:
  `git fetch -q && git show origin/main:app/build.gradle.kts | grep versionCode`.
- **Do not quote a test count from an earlier run.** The number in the
  release notes must come from a full run's result XML — a filtered test run
  replaces the directory and the count comes out wrong.
- **Verify the artifact you shipped, not a locally built copy.** The two can
  differ: different signing key, different version, stale Gradle cache.
- **A disconnected device does not invalidate a release.** Signature and
  version are verifiable from the downloaded artifact alone; report the
  device check as not run rather than as passed.
