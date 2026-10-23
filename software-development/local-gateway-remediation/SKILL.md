---
name: local-gateway-remediation
description: Diagnose local gateway providers; stale daemon, missing env.
license: MIT
tags:
  - gateway
  - free-ride
  - provider
  - troubleshooting
related_skills:
  - systematic-debugging
---
# Skill: Local AI Gateway Remediation

## When to use
Diagnosing and fixing a local AI model gateway (e.g. FreeRide at `http://127.0.0.1:11343`) when a provider handler (OpenRouter, Groq, HuggingFace, etc.) stops seeing models or reports `no usable API key in env; skipping`. Specifically: the OpenRouter handler is not returning the expected set of free models.

## Procedure (in order)

### 1. Check gateway health
```bash
curl -sf http://127.0.0.1:11343/health
```
Expected: `ok:true`, a version string, and a `keyed_providers` array. If the endpoint fails or reports a stale version, proceed to step 2.

### 2. Compare daemon version vs installed package
```bash
# Daemon version (from health endpoint or CLI)
freieride --version        # or: curl health (look at "version" field)
# Installed package version
ls /home/jhon/.local/share/uv/tools/freeride-gateway/lib/python3.14/site-packages/freeride_gateway-*.dist-info/METADATA
grep Version METADATA
```
**Rule:** if installed is newer than the running daemon, the daemon is stale. The daemon was likely started before the package update and keeps old in-memory code.

### 3. Check systemd user service environment loading
```bash
cat /home/jhon/.config/systemd/user/freeride.service
systemctl --user show freeride --property=EnvironmentFile
```
**Rule:** a running local gateway MUST source its `.env` (keys for each provider). If the unit lacks `EnvironmentFile=` and the daemon only sees a subset of keys (e.g. only `HF_TOKEN`), the service was started without the full environment. This causes providers to skip silently.

### 4. Verify the daemon's actual environment
```bash
PID=$(pgrep -f "freeride serve" | head -1)
tr '\0' '\n' < /proc/$PID/environ | grep -E "^(OPENROUTER|GROQ|CLOUDFLARE|HF_TOKEN|HOME|USER|PATH)="
```
**Rule:** every provider key (OPENROUTER_API_KEY, GROQ_API_KEY, CLOUDFLARE_API_TOKEN, HF_TOKEN) must appear in the daemon's environ. Missing keys mean the provider is skipped.

### 5. Restart the daemon to load latest code + full environment
```bash
systemctl --user restart freeride
sleep 3
curl -sf http://127.0.0.1:11343/health
```
Then check `/v1/models`:
```bash
curl -sf "http://127.0.0.1:11343/v1/models?refresh=true" | python3 -c "import json,sys; d=json.load(sys.stdin); print('total:',len(d['data']), 'free:', sum(1 for m in d['data'] if m['id'].endswith(':free')), 'openrouter:', sum(1 for m in d['data'] if m.get('owned_by')=='openrouter'))"
```
**Rule:** after restart, all keyed providers must appear in health, and `/v1/models` must reflect the full catalog (e.g. OpenRouter models now visible, not 0).

## Pitfalls
- **Stale daemon code:** the installed package may be v0.4.0a24 but the daemon runs a23 (started earlier). Restart to load new code.
- **Environment not loaded:** systemd user service without `EnvironmentFile=` means the daemon never sees the keys; providers silently skip.
- **Silent provider skip:** the daemon log shows `provider openrouter has no usable API key in env; skipping`. Don't be misled by a healthy-looking health endpoint — check `keyed_providers` and the daemon log.
- **Version skew is the smoking gun:** the combination of `daemon_version < installed_version` AND one provider missing from `keyed_providers` points to `EnvironmentFile` missing in the unit plus stale code.

## Always-on rules (user preferences)
- Always respond in Spanish (Latin American neutral, no voseo).
- Prefer a shared lookup (a single health/`/v1/models` endpoint or a single diagnostic script) over an exhaustive per-item list of providers.
- When presenting results, show a compact table or one-line summary, not a wall of logs.
- Use kawaii expressions (◕‿◕, ★, ♪) sparingly — the user values warmth but the response must stay direct and avoid filler.
- Never report a fix you did not actually run and verify; if the final restart/health check was blocked, say so plainly.
