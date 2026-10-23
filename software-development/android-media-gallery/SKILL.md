---
name: android-media-gallery
description: Use when building an in-app photo gallery over MediaStore.
license: MIT
tags: [android, mediastore, gallery, images, permissions]
metadata:
  version: "1.0.0"
  category: software-development
  hermes:
    tags: [android, mediastore, gallery, images, permissions]
    related_skills: [android-device-deployment, android-download-manager]
---

# In-app photo gallery over MediaStore

Scope: a tab or screen that lists images the app saved to the device gallery, shows
them in a grid, opens them full screen, and can share or delete them.

## When to Use

- Adding a "Gallery" / "Photos" screen to an Android app.
- A saved image never appears in the list, or the list shows unrelated photos.
- Delete does nothing, or the viewer OOMs on a modern camera photo.
- Handling `READ_MEDIA_IMAGES` on Android 13+ without prompting on every open.

## Always-on rules

- **Filter by folder, not by ownership.** `MediaStore.Images.Media.RELATIVE_PATH LIKE
  'Pictures/<Folder>%'` on API 29+; below 29 `RELATIVE_PATH` does not exist and naming it
  in the selection throws `IllegalArgumentException`, so the gallery renders empty with no
  crash. Use `DATA LIKE '%/Pictures/<Folder>/%'` on 28.
- **Try the query before asking for permission.** An app sees media it inserted itself
  without `READ_MEDIA_IMAGES`; other apps' images need it. Show the "allow photos" button
  only when the result set is empty *and* the permission is missing, otherwise you prompt
  on every entry to a gallery that already worked.
- **Thumbnails via `loadThumbnail` on 29+, `Thumbnails.getThumbnail(..., MINI_KIND)` below.**
  Decoding the full image for a 100 dp cell is what makes a 20-item grid stutter and OOM.
- **Delete through the system consent flow on 30+.** `MediaStore.createDeleteRequest(resolver,
  listOf(uri))` + `startIntentSenderForResult`; a plain `resolver.delete` only removes the
  app's own rows and silently returns 0 for anything else. Handle the result code in
  `onActivityResult` and refresh the grid.
- **Decode the full-screen image with `inJustDecodeBounds` + `inSampleSize` (cap ~2048 px).**
  A 12 MP JPEG decoded at full size is a guaranteed OOM on a mid-range phone.
- **Grid cells need weight, and the last partial row needs spacers.** Three fixed-width
  cells plus the card padding overflow the row and clip it; weight `(0, cell, 1f)` shares
  the row evenly. With 1–2 items in the last row, add invisible spacer views with the same
  weight, or the lone cell stretches to the full width.

## Procedure

1. **Query** — `_ID`, `DISPLAY_NAME`, order by `DATE_ADDED DESC`, filtered by folder.
2. **Grid** — rows of N `ImageView`s with `CENTER_CROP`, weight-based width, square height
   computed from the screen width; load thumbnails on `Dispatchers.IO` and set on the main
   thread.
3. **Viewer** — full-screen `Dialog` with a zoomable `ImageView`, tap-to-close, and a bar
   with close / share / delete.
4. **Share** — `Intent.ACTION_SEND` with `type=image/*`, `EXTRA_STREAM` = the content URI,
   `FLAG_GRANT_READ_URI_PERMISSION`.
5. **Delete** — confirm dialog → consent request (30+) → refresh on result.
6. **Permission** — manifest `READ_MEDIA_IMAGES` (33+) and `READ_EXTERNAL_STORAGE` with
   `maxSdkVersion="32"`; a button requests it; refresh when granted.
7. **Verify on the device** — push a test image, index it, open the tab, tap a thumbnail,
   delete, then confirm the row is gone (commands in `references/mediastore-verification.md`).

## Pitfalls

- **A pushed file is invisible until the media scanner indexes it.** `adb push` alone
  changes nothing; a `MEDIA_SCANNER_SCAN_FILE` broadcast (deprecated but still effective
  for a manual test) or a direct `content insert` makes it appear.
- **An empty grid is ambiguous.** No permission, an empty folder and a wrong selection
  string all look identical; check which one you have before "fixing" the layout.
- **Deleting the app's own image skips the consent dialog.** That is expected, not a bug —
  the system only asks when the row belongs to someone else.
- **Do not brand the consent dialog.** Its title and buttons come from the system and
  change per OEM/Android version; don't test for exact strings.

## Reporting

Report what was verified on the device: images listed (count), the viewer opened, delete
performed, and the post-delete count. "The build passed" does not prove a gallery shows
anything — a wrong `RELATIVE_PATH` selection compiles and renders an empty screen.
