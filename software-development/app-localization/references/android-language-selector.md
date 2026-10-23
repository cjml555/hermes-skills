# Android in-app language selector

Adding `res/values-<loc>/` makes the app *available* in a locale. This file covers letting the user pick it
inside the app (System / English / Spanish) without recreating the Activity.

## Why recreate is not acceptable here

An app that keeps native engines alive for the Activity lifetime (llama.cpp / LiteRT model, diffusion
context) loses every one of them to a locale-triggered recreate, plus seconds of model loading. Declaring
`locale` in `configChanges` keeps the instance and lets you rebuild only the view tree.

## 1. Manifest

```xml
<activity
    android:name=".MainActivity"
    android:configChanges="orientation|screenSize|keyboardHidden|uiMode|locale|layoutDirection">
```

`uiMode` is usually already present for theme switching; add `locale|layoutDirection` beside it.

## 2. Apply the locale

API 33+ owns the per-app locale. Keep the call in its own method so the `LocaleManager` class is only
resolved on devices that have it:

```kotlin
override fun setAppLanguage(tag: String?) {
    val t = tag?.trim().orEmpty()                 // "" / null = follow the system
    prefPutStr(KEY_APP_LANG, t)
    if (Build.VERSION.SDK_INT >= 33) applyAppLocale33(t) else applyAppLocaleLegacy(t)
}

private fun applyAppLocale33(tag: String) {
    val lm = getSystemService(android.app.LocaleManager::class.java)
    lm.applicationLocales =
        if (tag.isEmpty()) android.os.LocaleList.getEmptyLocaleList()
        else android.os.LocaleList.forLanguageTags(tag)
}

private fun applyAppLocaleLegacy(tag: String) {
    val cfg = Configuration(resources.configuration)
    cfg.setLocale(if (tag.isEmpty()) java.util.Locale.getDefault() else java.util.Locale.forLanguageTag(tag))
    @Suppress("DEPRECATION")
    resources.updateConfiguration(cfg, resources.displayMetrics)
    applyThemeInPlace()                            // manual rebuild: no config change fires here
}
```

`getEmptyLocaleList()` is what "follow the system" means for `LocaleManager` — an empty list, not the
system's tag.

## 3. Rebuild on change, not on every config change

```kotlin
private var lastLocales: android.os.LocaleList? = null

override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    lastLocales = resources.configuration.locales
    // ...
}

override fun onConfigurationChanged(newConfig: Configuration) {
    super.onConfigurationChanged(newConfig)
    val themeChanged = themeManager.onConfigurationChanged(newConfig)
    val localeChanged = lastLocales != newConfig.locales
    lastLocales = newConfig.locales
    if (themeChanged || localeChanged) applyThemeInPlace()
}
```

Rebuilding unconditionally wipes the chat on every rotation: `configChanges` also covers orientation.

## 4. Initial state: read the effective locale

```kotlin
override fun currentAppLanguage(): String? =
    if (Build.VERSION.SDK_INT >= 33) currentAppLocale33()
    else prefStr(KEY_APP_LANG, "").takeIf { it.isNotBlank() }

private fun currentAppLocale33(): String? {
    val ls = getSystemService(android.app.LocaleManager::class.java).applicationLocales
    return if (ls.isEmpty) null else ls[0].toLanguageTag().substringBefore('-')
}
```

A locale set through Android Settings or `adb shell cmd locale set-app-locales` is effective but was never
written to your preferences. Reading the pref alone shows "System" while the UI is already Spanish — the
selector then lies about the state it exists to reflect.

## 5. The control

A three-way segmented control (System / English / Español) works; persist the choice and apply it in
`onChanged`. The rebuild recreates the control, so its own labels come back in the newly selected language
("Sistema / Inglés / Español").

## Verification

```bash
adb shell cmd locale set-app-locales com.example.app --locales es
adb shell am force-stop com.example.app
adb shell am start -n com.example.app/.MainActivity
adb shell uiautomator dump /sdcard/l.xml && adb shell cat /sdcard/l.xml | grep -oE 'text="[^"]{2,40}"'
adb shell cmd locale get-app-locales com.example.app        # -> [es]
```

Then reset with `--reset` (or `--locales en`) so the device is not left pinned to the test locale, and say
in the report which state you left it in. The per-app locale survives reinstalls of the same package.

## Pitfalls

- **A rebuild that restores the tab by integer range drops the newest tab.** `if (restoreTab in 0..3)` was
  written when the app had four tabs; the fifth — the one the user was on — falls out of the range and the
  rebuild lands on the first page with no error. Grep `in 0..N` / `<= N` over tab indices whenever a tab is
  added, and test the rebuild path from the last tab.
- **Custom-drawn controls are invisible to `uiautomator`.** A segmented switch drawing its labels in
  `onDraw` produces no `text=` nodes; verify placement and state with a screenshot, and never read "no
  node" as "not rendered".
- **Selected text must contrast with the thumb, not match the brand.** Drawing `pal.primary` on a thumb that
  is also `pal.primary` makes the active option unreadable in dark theme while every build stays green.
  Choose the foreground from the thumb's luminance (bright thumb → dark text, dark thumb → light text).
- **A locale change can reset scroll or the current page** if the rebuild path does not restore them:
  capture the index before `buildUi()` and re-apply after, the way the theme path already does.
