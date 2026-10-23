#!/usr/bin/env bash
# probe-native-libs.sh — which native libs ship in an APK, and do any carry a GPU backend?
# usage: probe-native-libs.sh path/to/app.apk
set -u
APK="${1:?usage: probe-native-libs.sh app.apk}"
[ -f "$APK" ] || { echo "no such file: $APK" >&2; exit 1; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
unzip -q "$APK" 'lib/*' -d "$TMP" || { echo "no lib/ entries in $APK" >&2; exit 1; }
for so in "$TMP"/lib/*/*.so; do
  [ -f "$so" ] || continue
  printf '== %s  (%s)\n' "$(basename "$so")" "$(du -h "$so" | cut -f1)"
  if readelf -d "$so" 2>/dev/null | grep -qE 'vulkan|OpenCL|OpenGL'; then
    readelf -d "$so" 2>/dev/null | grep -E 'NEEDED.*(vulkan|OpenCL|OpenGL)' | sed 's/^/   linked: /'
  else
    echo "   linked: (no GPU/OpenCL libs)"
  fi
  vk=$(nm -D "$so" 2>/dev/null | grep -ic vulkan || true)
  gs=$(strings "$so" 2>/dev/null | grep -c 'ggml_vulkan' || true)
  cl=$(strings "$so" 2>/dev/null | grep -ic 'clEnqueueNDRange' || true)
  echo "   vulkan_syms=$vk ggml_vulkan_strings=$gs opencl_strings=$cl"
done
