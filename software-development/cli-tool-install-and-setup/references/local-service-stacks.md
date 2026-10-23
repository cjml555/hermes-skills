# Docker-backed local stacks for CLI-installed servers

Recipe for tools whose CLI pulls an image and composes up an API + datastore + worker
(AI memory servers, vector DBs, agent runtimes).

## Sequence that works

1. `docker info --format '{{.ServerVersion}}'` — confirm the daemon is reachable before
   attributing any failure to the tool. Container count in the same output tells you
   whether other stacks are already running.
2. Run the tool's `start` without the setup wizard. It pins the image by digest on first
   run; the pull is slow and is worth letting finish before judging anything else.
3. Read the blocking error for the exact env var names. These tools usually accept
   several provider keys and pick the first one present, so the error text is the
   authoritative list — do not guess names from the provider's own conventions.
4. Hand the credential step to the user, then start for real.

## Port and URL wiring

- The local stack does **not** change the CLI's configured server URL. After startup, the
  SDK must be pointed at it explicitly with a base-URL env var (e.g. `HONCHO_BASE_URL`,
  `HONCHO_URL`) or a `base_url=` client argument. A successful local stack with an unset
  base URL will silently talk to the hosted service instead.
- Pass explicit host ports when defaults collide with other stacks already on the host.

## OpenAI-compatible providers

Most of these tools expose only three transports (OpenAI / Anthropic / Gemini) but allow
a per-module base-URL override. To use an aggregator such as OpenRouter, keep the OpenAI
transport and change only the base URL and key env var — do not add a new transport name.
Embeddings are configured separately from text generation and may point at a different
model or endpoint.

## Health checking

Poll the service's `/health` endpoint (or the CLI's own wait flag) instead of sleeping a
fixed interval. Compose-up of a multi-service stack routinely exceeds 60s on first run
while the image layers are still being extracted.