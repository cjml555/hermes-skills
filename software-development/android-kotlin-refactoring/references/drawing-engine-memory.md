# Making a big Stable Diffusion model fit on a phone: disk weight residency

A phone cannot hold a whole SD pipeline in RAM at once. The obvious fix —
"encode the prompt, free the text encoder, load the UNet, free it, load the
VAE" — sounds like a lot of file I/O. The engine already does the equivalent
**without touching the flash twice**, and the app is one line away from
enabling it.

## What the engine already models

`app/src/main/cpp/sd/src/model_component.h` names the pipeline parts
explicitly:

```cpp
enum class ModelComponent {
    Conditioner,        // the text encoder(s)
    Diffusion,          // the UNet / DiT
    HighNoiseDiffusion,
    CLIPVision, IPAdapter,
    VAE,                // the decoder
    PreviewVAE, AudioVAE, ControlNet, PhotoMaker, PuLID, LoRA,
    Upscaler, Detector, LatentUpsampler, Count
};
```

and `app/src/main/cpp/sd/src/model_manager.h` gives each of them a
residency mode:

```cpp
enum class ResidencyMode { Disk, ParamBackend };
```

`ResidencyMode::Disk` is the sequential behaviour. In
`src/model_manager.cpp` the tensors of a component whose `pin_count` is 0
and that is not staged to the compute backend have their params-storage
block released (`free_params_storage_block(*block)`) — so the RAM of that
component goes back to the system when its stage ends, while the file stays
mmapped. Returning to that stage re-maps pages the kernel still holds in
the page cache: reclaimable RAM, not a re-read of the model.

## Enabling it

`sd_ctx_params_t` has the switch:

```c
const char* backend;         // where the graph runs
const char* params_backend;  // where the WEIGHTS live — "disk" keeps them mmapped
bool eager_load;             // false (default) = load lazily on first use
```

The app's JNI bridge (`app/src/main/cpp/sdcpp_jni.cpp`) already sets
`p.enable_mmap = true` but never sets `p.params_backend`, so today every
component stays resident. The change is one line in the ctx setup:

```cpp
if (diskWeights == JNI_TRUE) {
    p.params_backend = "disk";
}
```

Plumbing a JNI flag through means changing the `nativeCreate` signature in
`SdCppEngine.kt` **and** the JNI function signature in `sdcpp_jni.cpp`
together — the two must agree or the app throws
`NoSuchMethodError` at the first model load.

## What it buys

Peak memory goes from "the sum of every component" to "the largest one":

| family | components | resident now | with disk residency |
|---|---|---|---|
| SD 1.5 | unet 1.70 GB + CLIP-L 0.25 + VAE 0.16 | 2.11 GB | 1.70 GB |
| SDXL | unet 2.60 GB + CLIP-L+G 0.70 + VAE 0.16 | 3.46 GB | 2.60 GB |
| FLUX | DiT 11.2 GB + T5-XXL 9.8 + CLIP-L 0.25 + VAE 0.16 | 21.4 GB | 11.2 GB |

On FLUX this is the difference between a model that fits on a phone and one
that does not. On SD 1.5 it is a modest saving with no downside.

## Ship it as a switch, not as the default

Disk residency trades speed for RAM: if the page cache cannot hold the
active component, pages come from the storage and the generation slows
down. Expose it as a user setting ("High speed" / "Low memory") that takes
effect at the next model load, and say so in the hint text.

## Verify on the device before believing it

Two things to check, in this order, because both can make the feature look
like it works while it does nothing:

1. **The UNet must be unpinned between denoising steps.** The UNet runs for
   every step of the sampler. If the engine keeps it pinned across the whole
   sampling loop, the peak never drops and the mode is a no-op (or worse, it
   thrashes). Watch the log for the params-backend release messages.
2. **The peak RSS must actually drop.** Compare the process's peak memory
   (`adb shell dumpsys meminfo <pkg>`) with the mode on and off, same
   model, same steps. A setting that does not move the number is not
   working, whatever the logs say.

Interactors to re-check: VAE tiling (it already forces releases), the TAESD
preview path (1 MB, not the VAE) and LoRA (its own budget on top of the
UNet).

## Measured on device (Edge 50 Fusion, sd_turbo-f16-q8_0, 1,88 GB)

Same device, same model, only the mode switched - this is the comparison
that proves the feature, not the table above:

| mode | PSS | RSS | SWAP PSS |
|---|---|---|---|
| Low memory (`params_backend = "disk"`) | **1,18 GB** | 1,23 GB | 50 MB |
| High speed (weights stay resident) | **1,50 GB** | 1,60 GB | 0,2 MB |

**331 MB less PSS (-21,5 %)** with the same model. In Low memory a full
image was generated ("Quitando ruido... paso 686/686 - 63 s") with zero
crashes.

`scripts/measure-app-memory.sh <pkg> "<label>"` prints these numbers for
any app process, so the comparison is one command per mode.

## What makes this feature crash (and how to tell it from a driver bug)

With the weights on a **GPU** backend, the same model load dies with SIGSEGV
at 0x0. The trace is
`ModelManager::alloc_params_buffers` -> `ggml_vk_create_buffer_device` ->
`vk::Device::getBufferAddress`: the driver advertises the
`bufferDeviceAddress` feature but does not export
`vkGetBufferDeviceAddress`, so the call goes through a null pointer. The
fix is to check the function pointer before trusting the feature (see the
GPU-backend section of the main skill).

Two traps make this look like a bug in the feature:

- The crash is in the **other** engine of a shared "Backend" control. A
  device test that leaves the spinner on GPU changes the drawing engine's
  backend too, so the drawing dies for a reason the chat test caused.
- A native build that only prints "Linking" did not recompile the patched
  source. Check for `Building CXX object ... .o` in the build output before
  believing that a fix is in the binary you are testing.

The remaining crash after the BDA fix is inside the driver
(`ggml_vk_create_pipeline_func`): the Adreno driver cannot compile
ggml-vulkan's shaders. That one is not fixable from the app.
