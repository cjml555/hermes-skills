---
name: android-download-manager
description: Use when building or fixing an in-app file downloader.
license: MIT
author: Hermes Agent
metadata:
  version: "1.0.0"
  category: software-development
  hermes:
    tags: [android, kotlin, downloads, huggingface, notifications]
    related_skills: [android-kotlin-refactoring, android-device-deployment]
---

# In-App Download Manager (models, assets, large files)

Scope: a catalog of remote files, a download button per entry, progress UI, a
notification, and integrity checks. Everything here is about the failure modes that
turn a plausible downloader into one that always errors or never shows progress.

## When to Use

- Adding a "download models / assets" tab to an Android app.
- A download button always errors, shows no progress, or the file never appears in the
  model picker afterwards.
- A model catalog needs new entries and the URLs/sizes have not been verified yet.
- Wiring download progress into a notification or a foreground service.

## Always-on rules

- **Every catalog URL must be proven with `HEAD` before it ships**, against the mirror
  the app actually uses *and* the canonical host. `curl -sIL -o /dev/null -w '%{http_code}' <url>`
  must be `200` on both; fetch `Content-Length` in the same call.
- **A repo that looks public can still be gated.** Hugging Face repos under a
  `community` org may appear un-gated in the model list while `resolve/main/<file>`
  returns `401` without a token (license acceptance is per-repo). Confirm per file, not
  per org, and drop the entry rather than shipping a button that always fails.
- **`sizeBytes` must equal the real `Content-Length`, not a rounded guess.** Any
  "already downloaded" test of the form `length > expected * 0.9` silently re-offers a
  finished file when the declared size is too large, and re-downloads on every launch.
- **Resolve catalog entries by key, never by display name.** A UI that passes
  `info.name` into a map keyed by file name yields `Modelo no encontrado en catálogo:
  <pretty name>` for every entry. Accept both in the resolver:
  `catalog[key] ?: catalog.values.firstOrNull { it.name == key || it.displayName == key }`.
- **The progress row belongs under the tapped item, not at the end of the list.**
  Appending to the shared container puts it below the fold on a long catalog and looks
  like "no progress at all". Give each entry its own vertical wrapper, add the row to
  it, then `scrollView.smoothScrollTo(0, item.bottom)`.
- **Validate on read, not only on write.** Files that exist but are shorter than ~90% of
  the expected size must be flagged (`[incomplete 87%]`, error colour) and refused on
  tap with a message telling the user to delete and retry.
- **Long downloads need a notification, and its permission is a runtime grant.**
  One fixed notification id updated in place (`setOnlyAlertOnce`, `setOngoing`,
  `setProgress`) beats a new notification per tick; switch it to a completed/failed
  state at the end. Request `POST_NOTIFICATIONS` when the download starts on API 33+.
- **Refresh dependent lists on completion.** Downloading into `models/gguf/` does not
  update a picker that scanned `models/` at build time; call the picker's refresh from
  the completion callback so the new file is selectable without an app restart.
- **A catalog that mixes asset kinds carries the kind in the model, not in the UI.**
  Give the entry a `kind` (CHAT / MMPROJ / DRAW / TAGGER …) and one `baseDir(context)`
  that maps kind → directory the consuming feature already scans (`models/`, `mmproj/`,
  `draw/`, `tagger/`). Then `isModelDownloaded`, `getModelFilePath` and the download
  target all resolve through that mapping. Leaving them on a single hardcoded
  `models/` makes a downloaded projector or tagger land where nothing looks for it,
  and every non-chat row stays "not downloaded" forever.
- **Take exact file names and sizes from the repo tree, not from a guessed path.**
  `curl -s https://huggingface.co/api/models/<repo>/tree/main` returns every file with
  its exact `size` and path, so `remoteName` and `sizeBytes` come from the source.
  Reserve `HEAD` for proving the mirror actually serves the final
  `resolve/main/<file>` URL; guessing `mmproj-model-f16.gguf` style names produces
  entries whose button 404s on first use.

## Procedure

1. **Catalog** — one entry per model: key (file name), display name, description,
   format, `sizeBytes` (real), and the URL verified by `HEAD`.
2. **Storage layout** — write into a subdirectory per format (`models/gguf/`,
   `models/litertlm/`) and scan that same subdirectory when listing; a one-level
   `listFiles()` on the parent silently misses everything you downloaded.
3. **Downloader** — `HttpURLConnection` on `Dispatchers.IO`, 1 MiB buffer, connect/read
   timeouts, redirects on, retries with exponential backoff, and `cancelled` checked in
   the read loop so a cancel deletes the partial file instead of leaving a truncated one.
4. **Progress** — throttle callbacks to ~500 ms; report percent, speed and ETA from the
   same numbers the notification shows.
5. **Completion** — verify size (and checksum once real hashes exist), then notify the
   caller so the UI refreshes and the picker sees the file.
6. **Verify on device** — start a download and confirm three separate things: the
   notification text carries percent/speed, the inline row appears under the right
   model, and the file lands in the picker. A `BUILD SUCCESSFUL` proves none of them.

## Pitfalls

- **Placeholder checksums must be recognisable, or they delete good downloads.** A
  verification step that compares against a literal like `"a1b2c3…"` fails, deletes the
  file, retries, and finally reports failure. Either skip verification when the field is
  unset/null, or branch on a documented placeholder prefix.
- **A hardcoded sidecar (`mmproj`) URL breaks the whole entry.** Fetch the sidecar from
  the same repo as the main file, and if the public mirror does not publish it, disable
  the feature flag instead of downloading into a 404.
- **`isModelDownloaded` keyed by display name is always `false`**, which also makes the
  "already downloaded" chips unreachable — the same root cause as the catalog mismatch.
- **Cancel means delete.** A cancelled or incomplete stream leaves a truncated file that
  later passes an existence check; remove it in the `finally`/cancel path.
- **Sizes near a GB boundary:** store bytes as `Long` literals (`1_708_582_752L`); a
  float or an `Int` overflows, and rounding a `Double` loses the exactness the
  completeness test depends on.
- **A filtered list's empty state is not "no internet".** Once the catalog is split by
  kind, an empty category is the common case and rendering the network-error string
  there tells the user their connection is broken while the Wi-Fi is fine. Give the
  empty state its own key ("no models in this category yet") and keep the offline
  message for the actual `NetworkError` result.
