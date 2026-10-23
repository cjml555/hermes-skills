# Rebuilding a prebuilt native dependency from source with a GPU backend

When a published AAR ships a **CPU-only** `.so` and the app needs a GPU
backend, the path is: build the native library yourself with the backend
enabled, then swap the `.so` into the AAR. The Kotlin API does not change, so
the app's call sites keep compiling.

## 0. Pick a backend the device actually has

Before rebuilding anything, ask the phone which GPU backends exist. The
upstream may already publish a GPU-flavoured AAR (a second artifact next to
the CPU one in the same group), and choosing the wrong one wastes the whole
rebuild.

```bash
adb shell pm list features | grep -iE "vulkan|opencl|opengles"   # declared features
adb shell getprop | grep -iE "ro.hardware.vulkan|ro.hardware.egl" # the GPU itself
```

- **A missing feature line means the path is dead on that device.** An
  OpenCL-flavoured AAR is useless on a phone that does not declare
  `android.hardware.opencl` — the library loads and the driver call fails at
  the first dispatch. Vulkan (`android.hardware.vulkan.compute`,
  `ro.hardware.vulkan=<gpu>`) is the broadly available one on modern
  Android; OpenCL is being deprecated and many current devices do not
  declare it at all.
- **A present feature line is NECESSARY but NOT SUFFICIENT.** The
  declaration says the platform exposes the API — it says nothing about
  whether the vendor's driver can compile and run a particular compute
  workload. A device can report Vulkan 1.3 and still fail inside the
  vendor's shader compiler on the backend's own shaders, while the same
  build runs fine on a different GPU vendor's driver. The feature list
  narrows the candidates; only a real generation on the device ranks them.
- **One device's failure does not condemn the path.** Keep the build
  reproducible (vendored headers, a committed build script, the patch
  committed) and report the failure as a property of that GPU vendor, not
  as a defect of the backend. A vendor that fails to compile a compute
  shader set is a device finding.
- **Never assume the published GPU artifact matches the app's version.**
  Check the group on the registry: a CPU AAR at 5.1.0 and a GPU AAR at a
  different version means the Kotlin classes do not line up.
- Vulkan on Android needs no vendor SDK: the NDK carries the loader, the
  headers and the shader compiler (see §3).

## 1. Find the upstream source and the matching version

The AAR's POM names the project and the SCM URL. The AAR version is **not**
the repo's HEAD — check out the tag that matches it, or the native ABI will
not match the Kotlin classes:

```bash
AAR=$(find ~/.gradle/caches -name "<artifact>-<version>*.aar" | head -1)
POM=$(find ~/.gradle/caches -name "<artifact>-<version>.pom" | head -1)
grep -E "<url>|<connection>|<version>" "$POM"
git clone <scm-url> && cd <repo> && git fetch --tags && git checkout v<version>
```

Confirm what the published `.so` actually contains before rebuilding — the
question "does it have the backend?" is answerable from the binary:

```bash
unzip -q -o "$AAR" -d /tmp/aar
nm -D /tmp/aar/jni/arm64-v8a/lib<name>.so | grep -ci vulkan   # 0 = CPU-only
```

## 2. The native sources arrive via FetchContent

The binding's `CMakeLists.txt` pulls the engine with
`FetchContent_Declare(<engine> GIT_REPOSITORY … GIT_TAG <tag>)`. Pre-clone
that tag and point CMake at it, so the configure step does not download
during the build:

```bash
git clone --depth 1 --branch <engine-tag> <engine-url> /tmp/<engine>
cmake … -DFETCHCONTENT_SOURCE_DIR_<ENGINE.CPP>=/tmp/<engine>
```

**Apply the upstream patches by hand when you bypass FetchContent.** The
project keeps them in `patches/*.patch` and FetchContent applies them during
the download; with a pre-set source dir that step is skipped, and the build
fails on missing symbols from the patched files:

```bash
for p in <repo>/patches/*.patch; do
  git apply --check "$p" 2>/dev/null && git apply "$p" && echo "applied $p"
done
```

Apply them **sequentially, in one pass**: a patch that fails to apply on its
own may still apply after an earlier one has already touched the file, so
re-check the whole set instead of skipping the first failure.

## 3. The Vulkan bootstrap (no Vulkan SDK needed)

ggml-vulkan needs three things, and the NDK supplies two of them:

| need | source |
|---|---|
| `glslc` (compiles the `.comp` shaders to SPIR-V) | `$NDK/shader-tools/<host>/glslc` |
| SPIRV-Headers | `$NDK/sources/third_party/shaderc/third_party/spirv-tools/external/spirv-headers/include` |
| **Vulkan-Hpp** (`vulkan/vulkan.hpp`) | **not in the NDK** — only the C header is |

- The NDK ships `vulkan_core.h` (C) but **not** `vulkan.hpp` (C++), so
  `ggml-vulkan.cpp` fails with `fatal error: 'vulkan/vulkan.hpp' file not
  found`. Vendor a **Vulkan-Headers release** (it ships both `vulkan.hpp` and
  `vulkan_core.h`) and add its include dir.
- **The rule is "the pair must match", not "the pair must be 1.3.275".** A
  `vulkan.hpp` from one release against a `vulkan_core.h` from another
  asserts and the build stops with `Wrong VK_HEADER_VERSION!`. The NDK's
  frozen 1.3.275 pair is the conservative choice; a newer vendored pair
  (1.4.313 works) is fine **provided you take both files from the same
  release and let the vendored include dir come first**, so the vendored
  `vulkan_core.h` shadows the NDK's.
- **The header version decides which dispatcher fix applies** — see §6. Pick
  the pair with that in mind, not by habit: the 1.4.x semantics are the
  ones the §6 fix relies on.
- `find_package(SPIRV-Headers CONFIG)` needs a package config the NDK does
  not ship. Generate a minimal one that points at the NDK's headers and
  exposes an imported target `SPIRV-Headers::SPIRV-Headers`.
- **The SPIRV include must be a global `include_directories()`, not only the
  imported target's `INTERFACE_INCLUDE_DIRECTORIES`.** The target is not
  linked by the `ggml-vulkan` target, so the headers are not found and the
  error is `fatal error: 'spirv/unified1/spirv.hpp' file not found`.
- The shader compilation is the part that proves the bootstrap: when it
  works, `ggml/src/ggml-vulkan/vulkan-shaders.spv` exists and
  `vulkan-shaders-gen-done` is stamped.

## 4. The modern NDK broke two JNI signatures

A binding written against an old NDK does not compile against a current one:

- `JavaVM::GetEnv` still takes `void**`, but `AttachCurrentThread` now takes
  `JNIEnv**`. **Each call needs its own cast** — casting both the same way
  makes one of them fail:
  ```cpp
  g_vm->GetEnv((void **)&tenv, JNI_VERSION_1_6);                          // void**
  g_vm->AttachCurrentThread(reinterpret_cast<JNIEnv **>(&tenv), nullptr);  // JNIEnv**
  ```
- The C++ class is `_JNIEnv` (with `typedef _JNIEnv JNIEnv`), so a binding
  that spells it `JNIEnv_` fails with `use of undeclared identifier
  'JNIEnv_'`. Alias it at the compiler level rather than editing the
  binding's sources:
  ```bash
  -DCMAKE_CXX_FLAGS="… -DJNIEnv_=_JNIEnv"
  ```

## 5. Build, verify, swap

```bash
cmake --build <build> --target <target> -j4
nm -D <build>/lib<name>.so | grep -ci vulkan   # must be > 0
```

**Keep an unstripped copy before stripping.** The shipped `.so` should be
stripped (a debug build of llama.cpp is 218 MB; stripped it is 49 MB), but
the unstripped one is the only way to read a crash frame afterwards:

```bash
cp lib<name>.so /tmp/lib<name>-unstripped.so
llvm-strip --strip-all lib<name>.so
```

**Ship the rebuilt AAR from a local Maven repository, not from `files()`.**
`implementation(files("libs/x.aar"))` bypasses the POM, so the AAR's
transitive dependencies (Jackson, slf4j, …) disappear and the app dies at
runtime with `NoClassDefFoundError` on a class that the binding always
needed. Copy the published POM next to the AAR and keep its `<dependencies>`
block:

```
local-maven/<group>/<artifact>/<version>/
    <artifact>-<version>.aar     # published AAR with jni/<abi>/*.so replaced
    <artifact>-<version>.pom     # same deps as the published POM
```

```kotlin
// settings.gradle.kts
repositories { maven { url = uri("$rootDir/local-maven") } }
// app/build.gradle.kts
implementation("<group>:<artifact>:<version>")
```

Drop the published artifact from the dependency graph so the two never fight
over the same `jni/<abi>/` path.

**Archive the recipe in the repo, not in a scratch directory.** A rebuild
that lives only in `/tmp` (cloned sources, hand-applied patches, a CMake
cache) is lost the next time the machine reboots, and the `.aar` in the
local Maven repo becomes an unexplainable binary that nobody can rebuild.
Before calling the work done, commit:

- the build script (fetch → patch → configure → build → package → publish
  into `local-maven/`), so the whole chain is one command;
- the patch files as diffs, applied by the script with `git apply`;
- the vendored header pair, or the exact release and the download step.

The script must be re-runnable from a clean checkout, not a continuation of
the current `/tmp` state.

**Verify on the device, not only by symbol count.** A binary can export
`vulkan_*` and still be unusable: the runtime may have no Vulkan driver, or
the backend may not be the one the compute graph picks. The honest test is
the runtime's own build-info string (llama.cpp: `getLlamaCppBuildInfo()`
contains `VULKAN`) plus a real generation on the phone.

## 6. The Vulkan-Hpp dispatcher trap (null device functions)

The single most expensive failure mode of this whole path: **the process
dies with `SIGSEGV` at address `0x0` while loading the model**, and the
tombstone's top frame is `vk::Device::waitSemaphores` (or `vkCreateBuffer`,
or `vkGetBufferDeviceAddress`) — a function that certainly exists.

Cause: `vk::detail::DispatchLoaderDynamic::init(VkInstance)` loads **only
the instance-level functions**. The device-level ones
(`vkWaitSemaphores`, `vkCreateBuffer`, `vkQueueSubmit`,
`vkGetBufferDeviceAddress`, …) stay `NULL` until the dispatcher is
initialised *with the device*. ggml-vulkan initialises it with the instance
only, so the first device call jumps through a null pointer.

A second null-site has the same shape:
`ggml_backend_vk_host_buffer_type()` builds its buffer type with
`ggml_backend_reg_dev_get(ggml_backend_vk_reg(), 0)`, which is `NULL` when
the registry reports no device — and then `vk_instance.devices[0]` indexes an
empty vector.

Both are fixed in the backend by re-initialising the dispatcher with the
device right after `createDevice`, and by refusing to trust a feature flag
whose entry point the driver does not actually export:

```cpp
device->device = device->physical_device.createDevice(device_create_info);

// Device-level functions were NULL: the dispatcher only knew the instance.
VULKAN_HPP_DEFAULT_DISPATCHER.init(vk_instance.instance);
VULKAN_HPP_DEFAULT_DISPATCHER.init(vk::Device(device->device));

// Some drivers advertise bufferDeviceAddress but do not export the function.
if (device->buffer_device_address) {
    auto pfn = (PFN_vkGetBufferDeviceAddress)
        vkGetDeviceProcAddr(device->device, "vkGetBufferDeviceAddress");
    if (pfn == nullptr) { device->buffer_device_address = false; }
}
```

**The header version decides which of the two fixes is correct**, so it is
part of the diagnosis, not a detail:

- **1.4.x**: `vk::Device` resolves through the **global** dispatcher, so
  re-initialising the global dispatcher with the device repairs even a
  `Device` that was built earlier. The two `init()` calls above are enough.
- **1.3.x**: the dispatcher is **copied** into the `Device` at construction,
  so re-initialising the global does *not* repair an already-constructed
  `Device` — the device must be constructed **after** the dispatcher knows
  the device.

Either way, the dispatcher must be initialised for the instance **and** the
device; a driver that advertises `bufferDeviceAddress` without exporting
`vkGetBufferDeviceAddress` needs the same treatment (§6, second null-site).

Vendor the header pair from one release (Vulkan-Headers ships both) and let
the vendored include dir shadow the NDK's — mixing a new `vulkan.hpp` with
the NDK's `vulkan_core.h` asserts with `Wrong VK_HEADER_VERSION!`.

## 7. Declare the feature, or the app sees zero devices

From Android 12 the system exposes Vulkan devices to an app **only if the
app declares the feature**. Without it the driver loads, the instance is
created, and the enumeration returns nothing:

```xml
<uses-feature android:name="android.hardware.vulkan" android:required="false" />
```

`required="false"` keeps the app installable on devices without Vulkan.

This is separate from the library dependency: a `.so` with
`NEEDED libvulkan.so` (or `libOpenCL.so`) cannot even be loaded if the
linker does not expose the vendor library to the app, so the app dies at
startup with "cannot locate symbol" instead of at model-load time. The
manifest entry is what puts the vendor library in the app's namespace.

## 8. Prove the patch landed, then read the crash frame

**A patched source can be silently skipped by the build.** If the source's
mtime is older than the object file, `cmake --build` re-links and reports
success while the patch never reaches the binary. The build log tells you:
`Building CXX object …/ggml-vulkan.cpp.o` means it compiled;
`Linking … lib<name>.so` alone means it did not. Touch the file to force it:

```bash
touch <patched-source> && cmake --build <build> --target <target> -j4
```

**Resolve the crash frame in your own library, not only in the vendor
one.** "The top frame names the culprit library" is true for a driver
crash; it is false when the fault is a null function pointer inside the
runtime you built. Use the unstripped copy:

```bash
adb logcat -d -b crash | grep -oE '#0[0-2] pc 0x[0-9a-f]+' | tail -3
llvm-addr2line -f -C -e /tmp/lib<name>-unstripped.so 0x… 0x… 0x…
```

`vk::Device::waitSemaphores` in the output means the dispatcher, not the
driver: fix §6. A frame inside `/vendor/lib64/libllvm-qcom.so` means the
vendor's shader compiler: that is a device finding, not a code bug.
