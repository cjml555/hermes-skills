# Verifying a native dependency's real capabilities

Before promising GPU or NPU acceleration from a prebuilt AAR, prove the backend is
compiled into the shipped library. The Java/Kotlin API is identical either way —
`setGpuLayers(int)` exists in a CPU-only build and silently does nothing — so the
presence of a method proves nothing.

## Inspect the packaged `.so`

Unzip the ABI folder out of the APK (or the `.aar` under `jni/<abi>/`) and ask the
two questions the code cannot answer:

```bash
# 1. Is a driver library linked at all?
readelf -d libX.so | grep NEEDED          # libvulkan.so / libOpenCL.so present?

# 2. Does the library contain backend symbols/strings?
nm -D libX.so | grep -ci vulkan           # 0 means CPU-only
strings libX.so | grep -E 'ggml_vulkan|vkCreateInstance|clCreateContext' | head
```

A library that reports `NEEDED libvulkan.so` and `ggml_vulkan:` strings has the
backend; one with neither is CPU-only no matter what the wrapper exposes. Run the
same check on every path (chat runtime, diffusion runtime, ONNX) — in one app the
diffusion `.so` had Vulkan while the chat runtime had none.

## Prebuilt variants: diff the AARs, do not assume

Vendors often publish a second artifact for acceleration (e.g. a sibling
`-opencl` / `-vulkan` coordinate). Fetch both and compare the Java surface before
planning a migration:

```bash
unzip -p a.aar classes.jar > a.jar;  unzip -l a.jar | awk '{print $4}' | grep .class | sort > a.txt
unzip -p b.aar classes.jar > b.jar;  unzip -l b.jar | awk '{print $4}' | grep .class | sort > b.txt
wc -l a.txt b.txt; diff a.txt b.txt    # empty diff = drop-in swap, same API
```

Same class list + a `.so` that links the driver = dependency swap, no code change.
Different class lists = an API to port, budget it as such.

## Vendor drivers need a manifest entry

An app cannot load a vendor driver library it never declares, even when present on
the device:

```xml
<uses-native-library android:name="libOpenCL.so" android:required="false" />
<uses-native-library android:name="libcdsprpc.so" android:required="false" />  <!-- Hexagon/QNN -->
```

`required="false"` keeps the app installable on devices without it — pair it with a
runtime probe and a CPU fallback.

## Scope the promise to the vendor

OpenCL acceleration is Qualcomm/Adreno-specific; Mali needs a Vulkan build. Do not
advertise "GPU" as if it covers the fleet — say which chips it reaches.

## Never promise a speed-up without measuring

On small models (1B class) a mobile GPU frequently loses to CPU because both fight
for memory bandwidth. Ship the option, keep the CPU fallback, and let the app's own
benchmark decide per device; quote measured numbers, never the assumption that
"GPU is faster".

## NPU is a different project

NPU acceleration needs the chipset vendor's SDK (Qualcomm QNN, etc.) plus per-SoC
graph work — it is not a build flag on the existing runtime. Say so instead of
listing it as pending configuration.
