# NDK Version Upgrade (native Android builds)

Use when `app/build.gradle.kts` sets `ndkVersion` and the project has an
`externalNativeBuild` (CMake/ndk-build) block — e.g. a bundled stable-diffusion.cpp,
ggml or llama.cpp build. The change is small; the failure modes are not.

## Pre-flight

Confirm the target NDK is actually installed and carries everything the build
needs. `java-actions`-style setup actions do not install the NDK.

```bash
ls "$ANDROID_HOME/ndk/"
N="$ANDROID_HOME/ndk/29.0.14206865"
cat "$N/source.properties"            # Pkg.Revision must match ndkVersion
ls "$N/build/cmake/android.toolchain.cmake"
ls "$N/shader-tools/linux-x86_64/glslc"       # needed if the build uses Vulkan
ls "$N/toolchains/llvm/prebuilt/linux-x86_64/lib/clang/*/lib/linux/aarch64/libomp.so"
```

Quick compiler sanity check for a pinned ISA flag before a full build:

```bash
echo 'int main(){return 0;}' > /tmp/t.c
"$N/toolchains/llvm/prebuilt/linux-x86_64/bin/clang" \
  --target=aarch64-linux-android28 -march=armv8.2-a+dotprod+fp16 \
  -c /tmp/t.c -o /tmp/t.o && echo OK
```

## Procedure

1. Edit `ndkVersion` in `app/build.gradle.kts`.
2. **Delete the stale CMake cache:** `rm -rf app/.cxx`. It stores absolute paths to
the previous NDK; without this, configure fails pointing at a missing directory.
3. Configure only (validates the toolchain end to end):
   `./gradlew :app:configureCMakeDebug --console=plain`
   Read the cache back — it must name the new NDK, not the old one:
   ```bash
   C=$(ls -d app/.cxx/Debug/*/arm64-v8a/CMakeCache.txt | head -1)
   grep -m1 'ANDROID_NDK' "$C"
   grep -m1 'Vulkan_GLSLC_EXECUTABLE' "$C"
   grep -m1 'OpenMP_omp_LIBRARY' "$C"
   ```
4. Compile in the background — full native rebuilds are slow and can exceed a
   foreground tool timeout:
   `./gradlew :app:externalNativeBuildDebug --console=plain`
5. Package: `./gradlew assembleDebug`.

## Failure modes

### `2 files found with path 'lib/arm64-v8a/libomp.so'` at `mergeDebugNativeLibs`

The old NDK's `libomp.so` still sits in `src/main/jniLibs/arm64-v8a/`, while the
CMake build now emits the new NDK's copy into `build/intermediates/cxx/.../obj/`.
AGP refuses to choose. Delete the jniLibs copy — the CMake output is the one built
from the same toolchain as the rest of the native code.

```bash
rm app/src/main/jniLibs/arm64-v8a/libomp.so
```

### `libc++_shared.so` jumps from ~1.8 MB to ~9 MB

The NDK sysroot copy ships with `.debug_*` sections. Replace the jniLibs copy with
the new NDK's and strip it:

```bash
N="$ANDROID_HOME/ndk/29.0.14206865"
cp "$N/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so" \
   app/src/main/jniLibs/arm64-v8a/libc++_shared.so
"$N/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" --strip-unneeded \
   app/src/main/jniLibs/arm64-v8a/libc++_shared.so
```

Verify with `file`: it must say `stripped`, not `with debug_info`.

### Verify the artifact, not the build log

```bash
unzip -l app/build/outputs/apk/debug/app-debug.apk | grep 'lib/arm64-v8a'
```

Every native lib must be present, `libomp.so` and `libc++_shared.so` must be the
ones from the new NDK, and total native size should not have ballooned.

## CI counterpart

`actions/setup-java` does not install the NDK. Add an explicit step before the
Gradle build:

```yaml
- name: Set up Android NDK
  uses: nttld/setup-ndk@v1.6.0
  with:
    ndk-version: r29
    link-to-sdk: true
```

`link-to-sdk: true` symlinks the download into `$ANDROID_HOME/ndk/<full-version>`,
where AGP looks. `r29` resolves to the latest r29 patch; the download URL is
`https://dl.google.com/android/repository/android-ndk-r29-linux.zip`. Apply the
same step to every workflow that compiles native code (debug, beta, release).

## Release builds

`assembleRelease` also needs the signing secrets (`KEYSTORE_PASSWORD`, etc.). If
they are absent, the build compiles native code and then fails at signing — do
not treat that as an NDK problem, and do not ask for the password in chat.
