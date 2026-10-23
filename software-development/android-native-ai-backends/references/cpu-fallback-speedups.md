# Speedups when the phone has no usable accelerator

For image generation on a phone whose GPU path crashed (see the Pitfalls in SKILL.md), the remaining lever is
the model and the step count, not the runtime. This is also the honest answer to "can we use a FastSD-CPU
type backend?": that project is a Python desktop app, on Android it only runs inside Termux+PRoot, and its
headline accelerator (OpenVINO) is Intel x86 only. Nothing there can be linked into an APK — but its *recipe*
is portable.

## The portable recipe

1. A cheap base checkpoint in GGUF (SD 1.5 / SD 2.1 / SDXL, quantized Q4_0-Q8_0).
2. A distillation artifact for speed:
   - a **step-distilled checkpoint** (SD-Turbo, SDXL-Turbo, SDXS, SDXL-Lightning), or
   - a **distillation LoRA** applied to a normal checkpoint (Hyper-SD, LCM-LoRA, Lightning LoRA), 200-400 MB,
     which keeps the big checkpoint on disk until you need it.
3. Steps and CFG from the family, not from the normal defaults.

## Steps / CFG by family name

Match on the file, set and LoRA names together, lowercased:

| Name contains | Steps | CFG |
|---|---|---|
| `1step`, `1-step`, `hyper` | 1 | 1.0 |
| `2step`, `2-step` | 2 | 1.0 |
| `turbo`, `lightning`, `sdxs`, `lcm`, `distill` | 4 | 1.0 |
| anything else | model default (20+) | 7.0 |

Order matters: test the 1-step tokens before `hyper`, and `2step` before `lightning`, or
`sdxl-lightning-2step` matches the wrong row. Implement this as a pure function and unit-test the names —
UI code is awkward to test, the mapping is not.

Generating a distilled model with 20 steps / CFG 7 costs ~5x the time and looks worse.

## Adding a model to a download catalog

Verify the URL resolves and take the **exact** byte count before writing it into the app, so progress and
"already downloaded" checks agree:

```bash
curl -sIL "<hf-resolve-url>" | grep -iE "^HTTP|x-linked-size|content-length"
```

`x-linked-size` is the real object size behind the redirect. Pin it as the expected size; a size rounded to
MB makes the completion check fire early or never.

## Reference numbers (Snapdragon 6 Gen 1, SD 1.5 Q4_0, 8 threads)

| Config | Release (-O3) | Debug (-O0) |
|---|---|---|
| 256x256, 1 step | 25 s | 265 s |
| 512x512, 4 steps | 166 s | ~17 min (extrapolated from the same ~10x) |

Use these as order-of-magnitude sanity checks, not as promised numbers: a 4-step run at 512 taking under a
minute means you are on a release build, and a 1-step 256 taking minutes means you are on a debug one.
