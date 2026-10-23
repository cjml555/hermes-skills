---
name: android-native-ai-backends
description: Use when adding or validating Android GPU/NPU inference.
license: MIT
tags: [android, gpu, npu, native, inference]
metadata:
  version: "1.0.0"
  category: software-development
  hermes:
    tags: [android, gpu, npu, native, inference]
    related_skills: [android-kotlin, android-build-troubleshooting]
---

# Android on-device inference backends (CPU / GPU / NPU)

How to decide, wire and prove whether a model runtime can use the GPU (or NPU) on a given phone, and how to ship it without turning a driver bug into an app crash.

## When to Use

- The user asks why a model runs on CPU, or to "add GPU/NPU support".
- The user asks to "add ONNX Runtime / TensorFlow Lite / OpenXLA / llama.cpp" to the project.
- A runtime exposes a GPU flag or layer count and you must confirm the shipped native build honours it.
- You need to validate a vendor driver on one specific phone before shipping an acceleration toggle.
- The app dies with no Java trace while loading or running a model (native crash triage).

## Always-on rules

- **Audit the runtime inventory before recommending a new runtime.** The most common answer is "the project already has it, or it is redundant": LiteRT-LM *is* TensorFlow Lite, and an app that already runs an ONNX model already has ONNX Runtime. Re-deriving the answer from `build.gradle.kts` plus the acceleration hooks already in the source is faster than proposing a migration, and it usually reframes the task from "add a runtime" to "flip a flag" or "add an endpoint". See `references/runtime-inventory-audit.md`.
- **A third-party binding for the same library is a different build, not a drop-in.** It ships its own native library with its own feature set; it cannot reproduce capabilities you built that the binding does not expose. Check the binding's supported platforms before offering it — a package listing only `ios`/`macos`/`web` cannot serve an `arm64-v8a` app.
- **Measure the engine/UI split before answering "should we rewrite the UI".** Count the two sides separately and quote them: the UI is the code that draws (Views, layout calls) and the engine is everything that infers, downloads, serves or persists. A rewrite of the UI costs the whole UI side and none of the engine side, and the engine is usually the larger, riskier half (native C++ plus third-party AARs). The decisive question is whether the engine can be reached from the new UI: an HTTP server is reachable from anything; a Java AAR is not, and needs a MethodChannel bridge that concentrates the bugs (progress callbacks, cancellation, model loading). Present the split as numbers, not adjectives.
- **A UI rewrite is all-or-nothing, and it discards the test suite you already built.** A framework migration cannot be done screen by screen in the same app — either the framework owns the screen or it does not. Price in what gets thrown away: the JVM tests, the characterization coverage, the on-device verification, the changelog history. Quote the test count and the verified-on-device evidence as assets at risk, not as a footnote.
- **A background Service with a broadcast (turn the API on with the screen off) does not migrate cleanly.** A framework's own background-service plugin is unstable on recent Android releases, so that part stays native and needs a bridge anyway — one more MethodChannel surface, and the least testable one.
- **When the user asks "could we use framework F for task T", answer with the inventory first, then the verdict.** The verdict is usually "the pipeline is the product, not the runtime/framework" — the existing native build plus a small feature is the cheaper path by an order of magnitude, and the measurement to offer is the concrete gap (which steps, which minutes, which MB) rather than an architecture sketch.

- **Verify the packaged native library, not the API.** A wrapper class exposing `setGpuLayers(n)` proves nothing: the `.so` shipped in the AAR may be a CPU-only build where the call is a silent no-op. Inspect the artifact before promising GPU.
- **Benchmark only the build type you ship.** AGP compiles Debug with `-O0`, and a `CMakeLists.txt` that forces `-O3` usually does it for the RELEASE variants only, so the same 1-step 256x256 image took 265 s in a debug install and 25 s in release — a ~10x error that reads as "the hardware cannot do it". Rebuild `assembleRelease` (or force `-O3` on the native target in Debug) before quoting any number.
- **Drive benchmarks through the app's own API when it exposes one.** A POST to its OpenAI-compatible endpoint with explicit `steps` / `cfg_scale` / `size` takes the touchscreen out of the measurement and stops the app's persisted defaults from silently changing the test; only the model-load step needs UI. 
- **Never enable GPU/NPU by default.** A vendor driver can crash the process inside its own compiler; the JVM cannot catch a SIGSEGV. Ship acceleration as an explicit opt-in with a CPU fallback, and measure on the device.
- **Benchmark before believing the claim.** On small models (1B class) GPU is frequently *slower* than CPU because the model fights the CPU for memory bandwidth. Public numbers for Llama-3.2-1B class models on a mid Snapdragon: CPU ~14 tok/s vs Vulkan GPU ~4 tok/s. The app's own benchmark decides per device.
- **NPU is not a toggle.** It needs the chipset vendor SDK (Qualcomm QNN, etc.), per-SoC, usually with a signed/allowlisted app. Say so instead of implying a Kotlin flag exists.
- **A GPU path that crashes is a device finding, not a code bug.** Report it with the tombstone's top frame (vendor library name) and keep the CPU build shipped.

## Procedure

### 1. Probe the device (what hardware is actually there)

Do not infer from `Build.MODEL`. Read:

| Fact | Source |
|---|---|
| SoC | `Build.SOC_MODEL` / `Build.SOC_MANUFACTURER` (API 31+), else `Build.HARDWARE` |
| Big cores | `/sys/devices/system/cpu/cpu<N>/cpufreq/cpuinfo_max_freq`; group by frequency, count cores ≥ 85 % of the max |
| RAM | `ActivityManager.MemoryInfo.totalMem` |
| Vulkan | `PackageManager.FEATURE_VULKAN_HARDWARE_VERSION` feature **version** decoded as `(v shr 22) and 0x3FF`.`(v shr 12) and 0x3FF`; level from `FEATURE_VULKAN_HARDWARE_LEVEL` |
| GLES | `ActivityManager.deviceConfigurationInfo.reqGlEsVersion` → `major.minor` |
| ABI | `Build.SUPPORTED_ABIS[0]` |

Cache the result in an object — sysfs reads on every settings render are wasted work. Default CPU thread count to the **big-core** count, not `availableProcessors()`: on big.LITTLE, sending work to little cores (or waiting for migration) costs more than using only the big ones.

### 2. Inspect the native runtime (what the artifact can do)

Run `scripts/probe-native-libs.sh <apk>` (or the raw commands below) on the built APK, not on the source tree:

```bash
unzip -l app-release.apk | grep '\.so$'                 # what ships
readelf -d lib*.so | grep NEEDED                         # libvulkan.so / libOpenCL.so
nm -D lib*.so | grep -ic vulkan                          # 0 => no Vulkan backend
strings lib*.so | grep -m5 -i 'ggml_vulkan'              # backend strings prove a build flag
```

To check whether a GPU variant of a Maven AAR is a **drop-in** replacement, compare the class lists — identical `classes.jar` contents means the Kotlin/Java API is unchanged and only the native side differs:

```bash
unzip -p a.aar classes.jar > c1.jar; unzip -p b.aar classes.jar > c2.jar
unzip -l c1.jar | awk '{print $4}' | grep '\.class' | sort > l1
unzip -l c2.jar | awk '{print $4}' | grep '\.class' | sort > l2
diff l1 l2 && echo "same API"
```

### 3. Choose the integration

| Runtime | Today | Path to GPU |
|---|---|---|
| llama.cpp GGUF (`net.ladenthin:llama-android`) | CPU-only `.so` (0 Vulkan symbols) | Same-API swap to `llama-android-opencl` (OpenCL, **Adreno only**) or own build with `-DGGML_VULKAN=ON` + your own JNI |
| LiteRT-LM (`.litertlm`) | `EngineConfig(backend = Backend.GPU())` with automatic CPU fallback | Already there; verify per model |
| stable-diffusion.cpp | `SD_VULKAN=ON` compiled in; `NEEDED libvulkan.so` | Validate by generating one image: init selects `Vulkan0` and still dies in the graph on some drivers (see Pitfalls), so CPU is the safe default |
| ONNX Runtime (tagger) | `useGpu` plumbed to the session options | NNAPI / GPU EP per build |

Same-API swap steps (three files):
1. `implementation("net.ladenthin:llama-android-opencl:5.1.0")` (same `net.ladenthin.llama` API).
2. Manifest: **two** entries, not one —
   `<uses-native-library android:name="libOpenCL.so" android:required="false" />` (puts the vendor library in the app's linker namespace so the `.so` can load; `required=false` keeps installation working without it) and
   `<uses-feature android:name="android.hardware.opencl" android:required="false" />` (same for the device itself; without it the app sees zero OpenCL devices).
3. Offload all layers when the user selects GPU (`setGpuLayers(99)`), with a CPU retry if construction throws, and report which backend actually ran in the status line.

### 4. Verify on the device, then read the crash buffer

- Load the model and read the status line + the tok/s footnote (or run the app's benchmark) for both backends on the same model.
- If the app dies with no Java trace, the crash is native. `adb logcat -b crash -d | tail -40` shows the tombstone; the **top frame names the culprit library**.
- **The top frame can be in YOUR OWN `.so`, not the vendor's.** "The top frame names the culprit library" is a rule about driver crashes; a null function pointer inside the runtime you built looks the same in the tombstone and points the wrong way. Keep an unstripped copy of every native library you build, strip the shipped one, and resolve the frame:
  ```bash
  adb logcat -d -b crash | grep -oE '#0[0-2] pc 0x[0-9a-f]+' | tail -3
  llvm-addr2line -f -C -e /tmp/lib<name>-unstripped.so 0x… 0x… 0x…
  ```
  A frame in `/vendor/lib64/<vendor>.so` is a device finding to report; a frame in your own library (e.g. `vk::Device::waitSemaphores`, `ggml_backend_buft_alloc_buffer`) is your bug to fix. Full recipe: the `android-build-troubleshooting` skill.

## Pitfalls

- **A device with the GPU feature is not enough: the APP must declare it too.** From Android 12 the system exposes Vulkan devices to an app only when the app declares `<uses-feature android:name="android.hardware.vulkan" android:required="false" />`. Without it the driver loads, the instance is created, and the enumeration returns zero devices — the app then behaves as if there were no GPU. This is also what puts a vendor library (`libOpenCL.so`, `libvulkan.so`) into the app's linker namespace, so a `.so` with `NEEDED libOpenCL.so` cannot even load without it.
- **A vendor OpenCL compiler can SIGSEGV while compiling ggml kernels.** On Adreno 619 (SM6450) the top frames were `/vendor/lib64/libllvm-qcom.so` `llvm::QGPUI64EmulatePass::emulateModule` → `Fatal signal 11 (SIGSEGV)`. The process dies; `try/catch` in Kotlin is irrelevant because the fault is below the JVM. Do not ship that path on that device family.
- **Vulkan can initialise and still die on the first generation.** The same Adreno 619 logged `backend: Vulkan0` and a real `ggml-vulkan` instance on `/vendor/lib64/hw/vulkan.adreno.so`, then SIGSEGV'd at `ggml_backend_buft_alloc_buffer+180` through a null pointer inside `ModelManager::alloc_params_buffers` while running the graph. Init success is not validation: run one real generation before declaring GPU usable.
- **`setGpuLayers(n)` is silently ignored by a CPU-only build.** Confirm symbols in the `.so` first; otherwise you ship a "GPU" toggle that runs CPU at CPU speed.
- **The library classes existing at compile time does not mean the device has the backend.** A GPU feature flag gated on a driver is the same shape as any other capability probe: ask the device, not the dependency graph.
- **`uses-native-library` fixes installation, not runtime.** A missing `libOpenCL.so` still fails at `dlopen`; keep the CPU retry and a visible message.
- **Measure at the same model/quantization/context.** A "GPU is 2× faster" claim from a different quant or context is not a measurement.
- **A LoRA passed per request can be re-applied on every generation.** sd.cpp takes `g.loras` in the generation params (`LORA_APPLY_AUTO`), so a large LoRA may cost a merge pass per call: a 128x128 one-step run came out far above the no-LoRA time. Time with and without the LoRA before blaming the quant or the device; if it dominates, apply it once at context load instead.
- **stable-diffusion.cpp ships a full hi-res fix that most wrappers never expose.** `sd_hires_params_t` (in `sd/include/stable-diffusion.h`) carries `enabled`, `upscaler`, `scale`, `target_width/height`, `steps`, `denoising_strength` and `upscale_tile_size`; `sd_hires_params_init` defaults to `scale=2.0`, `denoising_strength=0.7`, `upscale_tile_size=128`. The `sd_hires_upscaler_t` enum covers `LATENT` (cheap, in latent space), `LATENT_*` variants, `LANCZOS`, `NEAREST` and `MODEL` (ESRGAN). The implementation lives in `sd/src/pipeline/image.cpp` and runs either a latent-space upscale followed by a second denoise pass, or a pixel-space Lanczos/ESRGAN upscale. This is strictly better than faking a 2x upscale by re-drawing the image through img2img: no prompt tokens are spent, the composition is not re-randomised, and it is a single extra graph rather than a full re-sample. Check whether the JNI bridge actually plumbs `hires` through (`grep -c hires sdcpp_jni.cpp` returning 0 means the vendor supports it but the app does not).
- **`sd_hires_params_t.steps` is the *effective* step count of the second pass, and it is divided by `denoising_strength` before the sigma schedule is trimmed** (`sd/src/pipeline/request.cpp`: `scheduler_steps = effective_steps / denoising_strength`, then only the last `scheduler_steps - t_enc` sigmas survive). Reusing the first pass's step count is a trap on distilled checkpoints: a 4-step Turbo model with `denoise=0.35` yields `scheduler_steps = 11` and keeps the 8 highest-noise sigmas, so the hires pass resamples from near-pure noise and the composition is completely lost. Give the hires pass its own step budget (>= 8) and map the user's slider onto a usable denoising range (roughly 0.15-0.55) instead of passing 0.05-0.99 straight through — at 0.99 the hires pass is a full re-sample.
- **The vendor's model-slot table is much wider than a typical JNI wrapper exposes.** `sd_ctx_params_t` has 21 path slots but wrappers usually wire 13; the ones that unlock whole feature families are `control_net_path` (plus `sd_ctx_load_control_net` / `sd_ctx_unload_control_net` / `sd_ctx_has_control_net` for hot-loading), `ip_adapter_path`, `photo_maker_path` and `pulid_weights_path` (facial identity), `motion_module_path` (video), and `embeddings_connectors_path`. Also unexposed but cheap to add: `sd_img_gen_params_t.mask_image` (inpainting), `vae_tiling_params` (tile size + overlap — the single biggest win for large images on a low-RAM phone, because it stops the VAE from decoding the whole frame at once), `cache` (TaylorSeer/spectral latent caching for speed), `circular_x`/`circular_y` (panoramas), and `sample_params.eta` / `shifted_timestep` / `flow_shift` (Flux and SD3). Enumerate the gaps with `grep -oE 'SD_API[^;]*' include/stable-diffusion.h`.
- **TAESD is the single biggest speed win for stable-diffusion.cpp on a phone.** `sd_ctx_params_t.taesd_path` makes sd.cpp use a Tiny AutoEncoder (a distilled mini VAE) instead of the full one for latent decoding. It is a separate 5-10 MB file, not part of the main checkpoint: `madebyollin/taesd/resolve/main/diffusion_pytorch_model.safetensors` carries both encoder and decoder, and sd.cpp loads it with the `tae.` tensor prefix. Measured on a Motorola Edge 50 Fusion (CPU, sd_turbo 4 steps, 256x256): 2184 MB peak RSS and 720 s without it, 1912 MB and 635 s with it — about 12% less memory and 12% less wall clock, with no visible quality loss at that resolution. It only applies to SD1.x/SD2.x; SDXL needs the separate TAESDXL weights.
- **Decoding dominates the wait on a phone, and it is also where the memory goes.** For 512x512 the VAE decodes the whole frame in one graph, so peak RSS scales with the full image (measured 2.1 GB). `sd_tiling_params_t` (in `sd_img_gen_params_t.vae_tiling_params`) decodes in blocks with overlap: the peak then depends on the block, not the frame. Its `rel_size_x/y` semantics are counter-intuitive — `<= 0` means use the absolute `tile_size_x/y` in pixels, `<= 1` means a fraction of the latent, `> 1` means a number of tiles. Absolute pixels is the right choice when the image size varies, so the block stays constant instead of scaling with the frame. Counter-intuitively, tiling was *faster* on CPU, not slower (256x256: 720 s without, 456 s with a 128px block) because small blocks hit cache better than one huge graph.
- **Automating an Android app from adb: implicit broadcasts from the shell do not reach a backgrounded app on Android 14+.** An explicit broadcast with the component (`am broadcast -a ACTION -n "com.yumenode.ai/.ApiService\$BootReceiver"`) does work, and the `\$` must be escaped or the shell eats it. Starting a non-exported Service directly is refused ("not exported from uid"), and `cmd activity start-service` silently runs it under the *shell* uid so it reads the wrong SharedPreferences. The practical pattern for testing an on-device model server: register a small exported BroadcastReceiver that calls `startService` on the app's own Service, then drive the whole thing over HTTP through `adb forward`.
- **A backgrounded app rewrites SharedPreferences from its in-memory copy, so hand-editing the XML is pointless.** Write the preference through the app (a button, or a broadcast that reaches it) — otherwise the next `edit().apply()` from the running process overwrites the file.
- **When no accelerator survives, the speedup is in the model, not the backend.** Few-step distilled checkpoints/LoRAs (Turbo, Lightning, Hyper-SD, LCM, SDXS) with CFG 1 cut a 20-step CPU run to 1-4 steps. See `references/cpu-fallback-speedups.md`.

- `references/runtime-inventory-audit.md` — auditing which runtimes a project already has, which acceleration is already wired, and whether a proposed runtime is redundant.
- **Freeing the native context while inference is in flight is a process-killer, and it looks like a GPU/driver bug.** The classic shape: `Activity.onDestroy` → `nativeFree(ctx)` runs while the inference thread is still inside the runtime, so the runtime's destructor tears down a live compute graph. In ggml-based runtimes the symptom is `ggml_abort` from `GGMLRunner::runner_end()` hitting `GGML_ASSERT(!graph_active_)` → SIGABRT → the whole app dies with no Java stack trace, and the tombstone's top frames point at the *runtime library*, not at your code. Diagnostic: `adb shell cat /data/tombstones/tombstone_NN | head -40` and look for `~VAE` / `~GGMLRunner` / `free_sd_ctx` in the destructor chain. Fix in the JNI, not in Kotlin: track an in-flight flag under a mutex, and when a free is requested during inference, mark it pending and let the inference thread perform the real `free_*_ctx` after it returns. A Kotlin-side `runCatching` around the free does nothing here — the fault is below the JVM. Related: the ADB daemon can die with the app under memory pressure, so a vanished device is not proof of a device-side fault.
- **A separate process is the only safety net for unknown drivers.** If GPU must be offered broadly, run it in `android:process=":gpu"` so a driver crash kills the service, not the UI. It does not fix a crashing driver — it only contains it.

## Reporting

State, per runtime: the artifact evidence (symbols/linked libs), the device values (SoC, big cores, Vulkan/GLES), what ran (CPU vs GPU), the measured tok/s, and — when it crashed — the tombstone's top frame. "GPU available" without a symbol count and a measurement is a guess.
