---
name: android-adaptive-icons
description: Use when fixing Android adaptive launcher icons.
category: android
---

# Android Adaptive Icons — Launcher Icon Configuration

## Trigger
Use when creating, updating, or fixing an Android app launcher icon that uses adaptive icons (`mipmap-anydpi-v26/`).

## Always-on rules

### Rule 1: Background layer uses color, not mipmap reference
In `mipmap-anydpi-v26/ic_launcher.xml`, the `<background>` element must reference a color (e.g., `@color/colorPrimary`), never `@mipmap/ic_launcher_background`. The `ic_launcher_background.xml` file exists only in density-specific folders (`mipmap-mdpi/`, etc.), not in `anydpi-v26`, so a mipmap reference inside `anydpi-v26` will fail to resolve at build time.

### Rule 2: Foreground is a single 256×256 PNG in anydpi-v26
Place `ic_launcher_foreground.png` (256×256) in `mipmap-anydpi-v26/` and reference it with `@mipmap/ic_launcher_foreground`. Do not create per-density foreground PNGs — adaptive icons use one density-independent PNG.

### Rule 3: Round variant reuses foreground XML
`ic_launcher_round.xml` in anydpi-v26 references the same foreground PNG with the same color background. The system crops differently based on launcher shape.

### Rule 4: Delete broken background XML from anydpi-v26
If `mipmap-anydpi-v26/ic_launcher_background.xml` exists and references a mipmap drawable, delete it. The background is defined inline in `ic_launcher.xml`.

## Procedure

1. **Define colorPrimary** in `values/colors.xml` (used as adaptive background).
2. **Generate foreground PNG** (256×256) from the app's source icon into `mipmap-anydpi-v26/ic_launcher_foreground.png`.
3. **Write `ic_launcher.xml`** (background + foreground):
   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
       <background android:drawable="@color/colorPrimary" />
       <foreground android:drawable="@mipmap/ic_launcher_foreground" />
   </adaptive-icon>
   ```
4. **Write `ic_launcher_round.xml`** (round variant):
   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
       <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
       <background android:drawable="@color/colorPrimary" />
   </adaptive-icon>
   ```
5. **Delete `ic_launcher_background.xml`** from `mipmap-anydpi-v26/` if present.
6. **Build**: `./gradlew assembleDebug`
7. **Install**: `adb install -r app/build/outputs/apk/debug/app-debug.apk`
8. **Launch**: `adb shell am start -n <package>/<package>.MainActivity`

## Pitfalls

- **Background references `@mipmap/ic_launcher_background` inside `anydpi-v26`** — that drawable does not exist in anydpi-v26, causing build failure or missing icon. Fix: use `@color/colorPrimary`. (Mechanism: Android resource resolution for anydpi-v26 cannot reach into density-qualified mipmap folders by simple name.)
- **Foreground PNG missing or wrong size** — launchers on Android 12+ expect 256×256; smaller images appear blurry or cropped.
- **Stale build artifacts** — after changing icon XML, run `./gradlew clean assembleDebug` or the APK may ship the old icon.

## Verification
- `adb shell ps | grep <package>` — process running
- Launcher app drawer shows the app icon with the new label
- Logcat has no `FileNotFoundException` for `ic_launcher_background`
