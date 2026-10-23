# Runtime Inventory Audit

Before recommending that a project "add ONNX Runtime / TensorFlow Lite /
OpenXLA / llama.cpp", audit what the project **already has**. The most common
answer is "you already have it, or it is redundant", and that answer changes
the whole plan — usually from "add a runtime" to "flip a flag" or "add an
endpoint".

## 1. List what is on the classpath

```bash
grep -nE "implementation\(" app/build.gradle.kts | grep -iE "litertlm|llama|onnx|tflite|tensorflow|ncnn|mediapipe"
```

Then check whether each dependency is actually *used*, not merely declared:

```bash
grep -rn "import com.google.ai.edge\|import net.ladenthin\|import ai.onnxruntime" app/src/main/java/
```

## 2. List the acceleration each runtime already has wired

```bash
grep -rn "vulkan\|Vulkan"  app/src/main/java/ | head   # GPU for a custom native build
grep -rn "Nnapi\|nnapi"     app/src/main/java/ | head   # GPU for ONNX Runtime
grep -rn "GpuDelegate\|gpu_delegate\|Backend.GPU" app/src/main/java/ | head
```

A runtime listed in `build.gradle.kts` with no acceleration hook is the real
gap; a runtime with a Vulkan/NNAPI path already in the code is done.

## 3. Coverage table — which runtime serves which task

| Task | Runtime | Note |
|---|---|---|
| LLM chat, `.litertlm` | LiteRT-LM | **This IS TensorFlow Lite.** Google ships it as a separate artifact, but the inference is TFLite with a GPU delegate. |
| LLM chat, `.gguf` | llama.cpp (`net.ladenthin:llama-android` or own build) | Same API as the OpenCL variant; own build needed for Vulkan. |
| Image generation | stable-diffusion.cpp | Own native build, `SD_VULKAN=ON`; expose the extra `sd_ctx_params_t` slots yourself. |
| Vision / classification / tagging | ONNX Runtime | `OrtSession.SessionOptions().addNnapi()` for GPU. |
| Embeddings | ONNX Runtime (bge-small, nomic-embed, e5-small) | ~30–130 MB, quantized, runs fine on CPU. |
| Arbitrary `.tflite` model | TensorFlow Lite | Only if the task is *not* LLM chat — in which case LiteRT-LM already covers it. |

**"Add TensorFlow Lite" is a no-op when LiteRT-LM is present.** TFLite is the
runtime *underneath* LiteRT-LM; adding the TFLite AAR buys nothing for LLM
chat and only matters for models that are not LLMs.

**"Add ONNX Runtime" is a no-op when the app already runs an ONNX model**
(a tagger, a classifier, a segmenter). The question is never "the library",
it is "which Execution Provider is configured".

## 4. Check the upstream roadmap before betting on a runtime

A feature listed in a runtime's README is not necessarily shipped on the
platform you target. Check the release notes for the version you depend on and
the platform you ship:

```bash
curl -s "https://api.github.com/repos/<owner>/<repo>/releases/latest" | grep tag_name
curl -s "https://raw.githubusercontent.com/<owner>/<repo>/main/README.md" | grep -i "<feature>"
```

Example shape: a runtime may ship an embeddings model while its **Android**
API is still chat-only, so the embeddings path is not an option today even
though the model exists.

## 5. Third-party bindings are a different project, not a drop-in

A binding for the same library (a Dart package, a Python wheel) ships **its
own** build of the native library, with its own feature set and its own
version. It does not reuse your tuned native build, so it cannot reproduce
capabilities you built that the binding does not expose.

Audit before treating it as a swap:

```bash
curl -s "https://pub.dev/api/packages/<pkg>" | python3 -c "import json,sys; d=json.load(sys.stdin)['latest']; print(d['version'], d['pubspec'].get('repository'), list(d['pubspec'].get('flutter',{}).get('plugin',{}).get('platforms',{}).keys()))"
```

The `platforms` list decides whether the binding is even an option: a package
listing only `ios`/`macos`/`web` cannot serve an `arm64-v8a` Android app.

The decisive question: **does the binding expose the features your build
added?** A custom native build with per-slot paths, tiled VAE decoding,
upscaling and LoRA cannot be replaced by a generic binding of the upstream
library.

## 6. When the answer is "you already have it"

Reframe the request into what is actually missing, and check the device:

- A GPU path that a runtime supports but the app never plumbs → plumb it
  (usually one flag plus a CPU fallback).
- An endpoint the local OpenAI-compatible server does not expose (for example
  `/v1/embeddings`) → implement it on the runtime already present, and it
  costs zero new megabytes in the APK.
- A version bump with no feature in it → not worth the risk.

## 7. "Can I add runtime X to do task Y?" — check the pipeline, not the library

The user often asks about a runtime for a *specific capability* rather than
for the runtime itself ("can I add ONNX Runtime for Stable Diffusion so the
model loads progressively?"). The runtime inventory does not answer that:
the question is whether the runtime can carry the whole pipeline, and whether
it is faster than what is already there.

For a diffusion pipeline, an ONNX export is **UNet + VAE only**:

- The **text encoder** is usually not exported (it depends on Python
  `transformers`), so CLIP/text-embedding has to run somewhere else — two
  runtimes instead of one.
- The exported graph is **one denoising step**. The sampler (KSampler: N steps
  with CFG guidance) is code you write, not a graph you run.
- Everything the existing native build already does (LoRA, hires fix, VAE
  tiling, per-step progress, cancellation) has to be re-implemented against
  the new runtime.
- **Speed**: ONNX Runtime's NNAPI EP on Android is commonly several times
  slower than a Vulkan build of the same model, because the graph is executed
  op-by-op through the EP rather than batched into one kernel launch.
- **Cancellation** is the decisive objection for progressive/interruptible
  work: controlling a run *per step* means invoking the session N times and
  shuttling intermediate tensors in and out of the runtime, which multiplies
  the per-step overhead. A runtime that runs the whole graph in one call
  cannot be paused between steps.

So the answer to "add runtime X for pipeline Y" is usually: **the pipeline is
the product, not the runtime**. Ask what capability is actually missing
(progress while loading? less RAM? embeddings?) and answer it with the
runtime already present, or with the existing native build.

## 8. Progressive loading: what "escalonado" usually means

When the goal is "the user should not wait staring at a blank screen",
there are three distinct mechanisms, and they are often confused:

| Mechanism | What loads progressively | Where it lives |
|---|---|---|
| **Weight staging** | The *decoder* comes in two sizes: a tiny one for a fast preview, the full one for the final image | Existing native build (a distilled mini-VAE) |
| **Tile decode** | The *image* is decoded in blocks, so peak RAM tracks the block, not the frame | Existing native build (tiling params on the decode) |
| **Partial download** | The *model file* arrives by HTTP range and inference starts on the partial file | Downloader + a runtime that accepts a partial model |

The first two are already in a mature native diffusion build and cost nothing
extra. The third is a downloader feature (HTTP range requests + resume), not
a runtime feature, and it is the one that actually removes a multi-minute
wait. Recommend the mechanism, not the runtime.

State the inventory before the recommendation: which runtime already serves
which task, which acceleration is already wired, and what the actual gap is.
