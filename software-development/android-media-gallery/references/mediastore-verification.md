# Verifying a MediaStore gallery on a device

Commands that distinguish the three ways an empty grid happens (no permission,
empty folder, wrong selection).

## Index a test image

```bash
adb -s <serial> push /tmp/test.png "/sdcard/Pictures/<Folder>/test.png"
adb -s <serial> shell "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
  -d \"file:///sdcard/Pictures/<Folder>/test.png\""
sleep 2
```

## Prove the row exists in MediaStore

The `--where` argument is re-split by `adb shell`; wrap the whole remote command in single
quotes and keep the SQL string in double quotes inside.

```bash
adb -s <serial> shell "content query --uri content://media/external/images/media \
  --projection _id:_display_name:relative_path \
  --where \"relative_path LIKE 'Pictures/<Folder>%'\""
```

No rows => the folder/selection is wrong or the file was never scanned. Rows present but
the app shows nothing => permission or query mismatch.

## Permission state

```bash
adb -s <serial> shell dumpsys package <pkg> | grep -E 'READ_MEDIA_IMAGES: granted'
adb -s <serial> shell pm revoke <pkg> android.permission.READ_MEDIA_IMAGES   # test the empty state
adb -s <serial> shell pm grant  <pkg> android.permission.READ_MEDIA_IMAGES   # restore
```

Revoking is the cheapest way to exercise the "allow photos" button; granting restores the
populated grid without navigating the system dialog.

## Read the app's own files

```bash
adb -s <serial> shell run-as <pkg> ls -l files/tagger/     # debug builds only
```

## Dump the UI and check layout numbers

```bash
adb -s <serial> shell uiautomator dump /sdcard/ui.xml
adb -s <serial> shell cat /sdcard/ui.xml | grep -oE 'content-desc="[^"]+"[^>]*bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"'
```

Thumbnails carry `contentDescription` (the file name), so their bounds show whether a cell
was clipped or stretched — a width equal to the row means a missing spacer.

## Screenshot + pixel check

```bash
adb -s <serial> shell screencap -p /sdcard/s.png
adb -s <serial> pull /sdcard/s.png /tmp/s.png
python3 -c "
from PIL import Image; from collections import Counter
im=Image.open('/tmp/s.png').convert('RGB'); c=Counter()
for x in range(0,1080,3):
  for y in range(0,2400,3): c[im.getpixel((x,y))]+=1
print(c.most_common(5))"
```

Dominant-colour counts answer questions a screenshot review cannot: pure black theme
(`(0,0,0)` dominating), a status bar with invisible icons (background dominating, no
contrast pixels), an empty grid (one flat colour).
