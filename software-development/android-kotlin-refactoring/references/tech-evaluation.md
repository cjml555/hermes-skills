# Evaluating a "can we add X?" request for this app

The user asks whether a technology, engine or rewrite is viable. The useful
answer is never a yes/no from priors — it is an audit of **what the app already
has** plus a costed comparison of the realistic options. Two of these requests
in a row (rewrite the UI in Flutter; add ONNX Runtime for Stable Diffusion)
both had the same shape: the requested technology was already partly present,
or the goal was already met by something the app already ships.

## Step 1 — audit what is already installed and already accelerated

Before saying "we could add X", read the dependency list and the acceleration
flags. In this app the answer to "add ONNX Runtime / add TFLite" was
"both are already there, and the GPU paths are already wired":

```bash
grep -nE "implementation\(" app/build.gradle.kts        # engines already on the classpath
grep -rn "System.loadLibrary\|external fun" app/src/main/java/   # native bridges
```

- A third-party SDK that *wraps* a runtime you already have is a no-op, not
  an addition. LiteRT-LM **is** TensorFlow Lite; ONNX Runtime was already
  there for the tagger.
- Check the acceleration, not just the runtime: a grep for the provider names
  (`Vulkan`, `Nnapi`, `addNnapi`, `vulkanDevice`) shows whether the GPU path
  is wired or merely possible.
- The "Running mode" toggle in the UI usually maps to those flags. If the
  device already has a CPU/GPU switch, the runtime is already dual-path.

## Step 1b — the vendored engine may already implement the requested mechanism

The classpath audit answers "is the runtime installed?". The deeper audit
answers "**does the vendored engine already implement the thing the user is
asking to add?**" — and the answer is often yes, behind a flag the app never
sets.

When the user proposes a mechanism (run the text encoder, keep the result in a
variable, free it, then run the UNet…), read the engine's own source before
designing anything:

```bash
grep -rn "enum class.*Component\|ResidencyMode\|params_backend" app/src/main/cpp/<engine>/src/
grep -rn "free_params_storage_block\|pin_count" app/src/main/cpp/<engine>/src/
```

In this app the vendored stable-diffusion.cpp already has the whole idea:
`ModelComponent` enumerates `Conditioner` / `Diffusion` / `VAE`, and
`ModelManager::ResidencyMode::Disk` frees a component's params block when its
`pin_count` drops to zero. The app sets `enable_mmap = true` but never
`params_backend = "disk"`, so every component stays resident at once. The
requested feature was a **one-line switch**, not a new pipeline — and the
engine's version beats the proposal, because the weights stay mmapped and are
re-faulted from the page cache instead of being re-read from flash.

Cost the win in the unit the user cares about: the RAM peak becomes the
largest single component instead of their sum (on a phone, Flux goes from
~21 GB resident to ~11 GB). The answer must also name the risks to check on
the device: does the engine re-materialize the weights on every denoising
step, does the switch interact with VAE tiling / LoRA / the step preview, and
what does it cost in speed when the page cache is cold.

## Step 2 — separate the goal from the proposed solution

The user states a *goal* ("carga escalonada", "que no se reviente la RAM")
and *proposes* a mechanism. Measure the goal first:

- **Does the app already deliver it?** The gradual preview during drawing
  already existed: the native engine emits a preview frame per step, the UI
  auto-switches to the process tab, and the header shows
  "Dibujando…". The gap was not the feature, it was the download blocking the
  app for minutes.
- **Then list the options that serve the goal**, and mark which exist already.

Frame the answer as: goal → what already delivers it → what is genuinely
missing → cost of each missing piece.

## Step 3 — cost the realistic options, including "do nothing"

For a rewrite of the UI or a new inference engine, the cost is not "a lot of
work" — it is a specific number of lines, a specific time, and a specific
risk, derived from the tree:

```bash
# lines of UI vs engine — the split that decides a rewrite
for f in $(find app/src/main/java -name "*.kt"); do
  echo "$(wc -l < $f) $f"
done | sort -rn | head -20

# native code that a rewrite would have to replace
find app/src/main/cpp -name "*.cpp" -o -name "*.h" | xargs wc -l | tail -1
```

- For a UI rewrite: the line count of the UI tells you the rewrite size; the
  line count of the native/engine code tells you what is *protected* by not
  touching it. Say both.
- For a new runtime: the honest risks are the things that runtime does not
  do. A per-step UNet graph means writing the sampler by hand; a text encoder
  that is never exported means running a second engine. These are the
  disqualifiers, and they are checkable facts about the pipeline, not
  opinions.

## Step 4 — verify the ecosystem claims before quoting them

Versions and platform support change; check the registry, do not recall:

```bash
curl -s "https://api.github.com/repos/<owner>/<repo>/releases/latest" | grep tag_name
curl -s "https://pub.dev/api/packages/<pkg>" | head -c 300   # Dart/Flutter
curl -s "https://api.github.com/search/repositories?q=<terms>&sort=stars" | head -c 800
```

- A binding existing for the platform does not mean it is usable *today*:
  check whether the feature you need is released for the platform you target
  (a runtime may have embeddings on desktop but not on Android).
- Search the ecosystem for the specific capability ("stable diffusion
  onnxruntime"), not the library name — the answers are scattered across
  sample repos, and their existence tells you what a migration would cost.

## Step 5 — answer in the user's language with a recommendation, not a survey

The user asked a yes/no question and expects a decision. Structure:

1. **Short verdict up front** ("se puede, pero no te serviría" / "ya lo
   tienes"), because a long preamble is a non-answer.
2. **The audit**: what is already there, with the evidence (dependency lines,
   flag names, file paths).
3. **Why the proposed mechanism does/doesn't serve the goal**, concretely.
4. **The options that do**, each with cost, ordered by value-per-effort.
5. **One clear recommendation** and the next action to take.

Never present a neutral menu without a recommendation — the user is asking
for a decision, not a survey. End with the single next step you propose.

## Pitfalls

- **Do not answer from priors about frameworks.** "Flutter is better for
  this" is worthless; the audit of *this* tree is the answer.
- **Do not propose adding a runtime before checking the classpath.** It is
  the most common shape of a request that turns out to be already done.
- **Quantify the rewrite in the unit the user cares about**: lines of Dart to
  write, weeks of work, lines of C++ protected — not "it's a big change".
- **When the goal is already met, say so plainly and redirect to the part
  that is actually missing.** That is the highest-value answer you can give.
