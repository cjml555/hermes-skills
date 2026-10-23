# Driving the App UI over ADB (device verification without guessing)

The device gate needs the app to be *in a known state* before you can prove a
behaviour. Coordinates captured by eye are wrong half the time, and a wrong tap
silently does nothing — which reads as "the feature is broken" when the feature
is fine and the tap missed.

## Never hardcode a coordinate you read from a screenshot

A screenshot is rendered at the display's *scaled* size. The UI dump gives
real pixels. Always derive the tap point from the dump.

```bash
# 1. dump the current tree
adb shell uiautomator dump /sdcard/ui.xml

# 2. pull the text of every node (fast read)
adb shell cat /sdcard/ui.xml | tr '>' '>\n' | grep -oE 'text="[^"]{2,60}"' | sed 's/text=//'

# 3. get the REAL bounds of the element you want to tap
adb shell cat /sdcard/ui.xml | tr '<' '\n<' \
  | grep -E 'text="(GENERAR|Enviar)"' \
  | grep -oE 'text="[^"]*"|bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' | paste - -
# -> text="GENERAR"  bounds="[40,1292][1040,1412]"
# -> tap the CENTRE: x=(40+1040)/2, y=(1292+1412)/2
```

## The bottom navigation MOVES when the keyboard opens

The single most expensive mistake. The chat input bar sits at `y=2092`; when
the soft keyboard opens, the bottom nav moves from `y=2287` to `y=1422`. A tap
computed for the closed-keyboard layout lands on the input field, and the
screen does not change — so the next step looks like a broken feature.

- **Close the keyboard before navigating**: `adb shell input keyevent KEYCODE_BACK`
  (one back press closes the IME; a second pops the screen — send one, then
  re-dump to confirm you are still in the app).
- **Re-dump after any layout change** (keyboard open/close, tab change,
  dialog). Do not reuse bounds from before.
- If a tap appears to do nothing, **assume the coordinate is stale** and
  re-dump before concluding the app is broken.

## Enter does not always send

`adb shell input keyevent KEYCODE_ENTER` inside a multiline `EditText` inserts
a newline instead of submitting. The symptom: the text is in the field, the
message never appears in the thread, and the screen looks "frozen".

- Find the send button in the dump and tap it (`text="↑"` or a content-desc).
- Type into the field first, then `KEYCODE_BACK` to close the keyboard, then
  re-dump — the button may have moved with the keyboard too.

## Reading a state that only exists in a View

`uiautomator dump` only sees visible nodes. Two cases need a screenshot:

```bash
adb shell screencap -p /sdcard/s.png && adb pull /sdcard/s.png /tmp/s.png
```

- A `ProgressBar` that is not a `TextView` shows no text in the dump; a
  screenshot shows it filled/empty.
- The *value* of a live counter ("paso 372/372 · 15 s") is in the dump only
  while the screen is not mid-layout; if the dump comes back empty, take the
  screenshot and read the value from the pixels.
- An empty dump during a long operation usually means the UI thread is busy
  rendering — wait and re-dump, or use the screenshot.

## Reading app-private state without root

```bash
# the app's own preferences: proves the write path of a store
adb shell run-as <pkg> cat shared_prefs/<name>.xml | tr '>' '>\n' | grep -oE '<string name="[^"]*">[^<]*</string>'

# the app's own data dir
adb shell run-as <pkg> ls -la files/<subdir>/
```

`adb shell ls /data/data/...` is permission-denied; `run-as` is the way.

## Driving a local HTTP API the app exposes

The app's OpenAI-compatible server is the best functional probe available —
it exercises the engine, the JSON contract and the network stack at once,
from outside the app:

```bash
curl -s http://<phone-ip>:<port>/health
curl -s http://<phone-ip>:<port>/v1/models
curl -sN -X POST http://<phone-ip>:<port>/v1/chat/completions \
     -H 'Content-Type: application/json' \
     -d '{"messages":[{"role":"user","content":"di ok"}],"max_tokens":10}'
```

Start the server from the UI first (Models/API -> API tab -> Start service),
and read the printed address — it is the phone's LAN IP, not the host's.

## Ending a long generation

A generation that is not interesting (a 90 s model on CPU) should be stopped
rather than waited out: `adb shell am force-stop <pkg>`. The in-flight request
is cancelled with the process, and the crash buffer stays clean — which is
itself the assertion you want.
