# System bars, theme state, and custom controls

Depth for apps that paint their own chrome (no Material theme attributes): a
runtime palette object, hand-drawn controls, and status/navigation bar colours
set from code. Every rule below was a real defect that built cleanly and only
showed up on device.

## System bar icon contrast

- **Decide the icon colour from the bar's luminance, never from a boolean
  `isDark` flag.** A light theme with a saturated blue status bar has dark
  chrome around it and needs *light* icons; a light theme drawing edge-to-edge
  behind a pale page needs *dark* icons. The same `isDark` value gives the wrong
  answer in one of those two cases.
- **API 30+:** `window.insetsController?.setSystemBarsAppearance(appearance, mask)`
  with `APPEARANCE_LIGHT_STATUS_BARS` / `APPEARANCE_LIGHT_NAVIGATION_BARS`, setting
  **both** halves of the mask every time. Below 30: `systemUiVisibility` with
  `SYSTEM_UI_FLAG_LIGHT_STATUS_BAR` / `..._LIGHT_NAVIGATION_BAR`.
- **Setting only the navigation-bar flag leaves the status bar unchanged.** That is
  the classic defect: the nav bar is correct, the clock and battery are invisible
  against a near-white bar.

## Android 15+ is edge-to-edge and ignores bar colours

- With `targetSdk >= 35`, `window.statusBarColor` / `navigationBarColor` are
  deprecated and **not applied**; the app draws behind the bars.
- Contrast therefore depends on whatever is actually behind them — usually the
  page background, not the colour you assigned to the bar. Compute the light/dark
  decision from that real background when `Build.VERSION.SDK_INT >= 35`, and from
  the bar colour below it.
- Verify by screenshotting the top ~100 px and counting dark vs light pixels (or
  reading the crop). A histogram of only the background colour means the icons
  were drawn in the background colour — unreadable, not absent.

## Theme persistence and live application

- **Save and load through the same `SharedPreferences` file.** A manager that
  writes `getSharedPreferences("ponko_prefs", 0)` while the loader reads
  `getSharedPreferences("ponko", 0)` persists nothing: the setting reverts on the
  next launch with no error anywhere.
- **Resolving a new palette does not repaint attached views.** If the theme
  manager only swaps its palette object, the UI keeps the old colours until the
  Activity restarts. The change must rebuild the view tree (or invalidate every
  cached colour alias).
- **That rebuild must restore transient UI state.** Capture the selected tab
  before rebuilding and restore it after — and keep the restore bounds in sync
  with the tab count (`0..N-1`); a hardcoded `0..3` silently drops the newest tab.
- **Verify both halves:** change the setting, `am force-stop`, relaunch, re-read the
  screen (persistence); then change it again and confirm it applies *without* a
  restart (live rebuild).

## Custom segmented / switch controls

- A control that paints its labels in `onDraw` publishes **nothing** to the
  accessibility tree: `uiautomator dump` shows no `text=` for that region while the
  control renders fine. Verify with a screenshot, never from a missing node.
- **The selected label's colour must be derived from the thumb colour's
  luminance**, not reused from the brand accent. Accent-coloured text on an
  accent-coloured thumb is invisible in dark theme with a green build.
- With four or more options on a phone-width bar, keep labels short and measure
  at 10–12sp; a long label is clipped, not wrapped, inside a segment.
- **Own the gesture only when it is horizontal.** Calling
  `requestDisallowInterceptTouchEvent(true)` in `ACTION_DOWN` stops the parent
  ScrollView, so a settings page will not scroll when the drag starts anywhere on
  the switch; a slightly diagonal swipe also slides the thumb into the next segment
  and changes the setting mid-scroll. Record `downRawX/downRawY`, claim the gesture
  only once `|dx| > |dy| + touchSlop`, update the thumb only while claimed, and on
  `ACTION_CANCEL` snap back to the real index instead of to the finger position.

## OLED / pure-black preset

- Use `#000000` for the page background, card surfaces **and** both system bars;
  keep borders and field backgrounds barely lifted (`#0A0A0A`–`#2A2A2A`) so cards
  and inputs stay distinguishable. Pure black everywhere flattens the hierarchy.
- A preset is a copy of the dark palette with those fields overridden, so accents
  and semantic colours keep working.
- Verify with a pixel histogram: the dominant colour must be `(0,0,0)`, and the
  accent colour must still be present.

## Thumbnail grids built by hand

- **Give each cell `width=0, weight=1`** so the row divides evenly. A fixed pixel
  width computed from the screen minus paddings clips the last cell of every row.
- **Pad the last partial row with invisible spacer views** carrying the same
  layout params. Without them a lone trailing item stretches across the entire
  width — obvious on a 4-item grid in 3 columns.
- Load thumbnails off the main thread, and downsample a full-size decode with
  `inSampleSize` before handing it to the viewer.

## Bottom navigation beyond five items

- Material guidance caps bottom navigation at five; a sixth works if the labels
  are shortened (`10sp`, `maxLines = 2`) and the tab index range is updated in
  every place that enumerates tabs (visibility switch, restore-after-rebuild,
  any `switchTab(n)` caller).
- Re-check the bar after adding one: six equal cells with a long label wrap the
  bar taller and misalign the icons.
