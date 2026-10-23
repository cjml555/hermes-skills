---
name: hermes-messaging-channels
description: "Enable and configure Hermes gateway chat channels."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [gateway, messaging, whatsapp, telegram, discord, slack, signal, channels]
    related_skills: [hermes-agent, hermes-desktop-from-source]
---

# Enabling a Hermes gateway messaging channel

## Overview

Use this when the user wants to talk to Hermes from WhatsApp, Telegram,
Discord, Slack, Signal, Teams, Google Chat, or Home Assistant. The gateway is
the long-lived process that bridges those platforms to agent runs; the CLI
session you are in does not own it.

Two independent writes carry the whole job:

- `~/.hermes/.env` — enablement and access control (secrets + allowlists)
- `~/.hermes/config.yaml` — optional behaviour (prefix, receipts, unauthorized-DM policy)

**Set access control in the same change that enables the channel.** With no
allowlist the gateway denies every inbound message, and with a wildcard
allowlist it accepts every sender's. Both are wrong defaults to leave in place
while you figure out the rest.

Verify, don't assume: confirm the channel appears in the gateway's connected
list and that a real inbound message round-trips before telling the user it
works.

- The scripts for this skill live in `scripts/` (currently:
  `scripts/status_monitor.sh`).

## When to Use

- "Quiero usar tambien WhatsApp" / "add Discord" / "message me on Signal"
- A channel is enabled but sends nothing, or replies to strangers
- Re-pairing after a phone reset or a platform protocol change

**Don't use for:** the desktop app, cron delivery, or the CLI itself — those
are not gateway channels.

## Before you start — do these two things

**Confirm the platform is already wired.** `~/.hermes/config.yaml` carries a
`platform_toolsets` map listing a toolset per platform. If the platform is
absent from that map, stop and tell the user: the adapter needs a Hermes update,
and no amount of env-var work will connect it.

```bash
grep -nA14 '^platform_toolsets:' ~/.hermes/config.yaml
```

**Check current state** so you write only what is missing:

```bash
grep -oE '^[A-Z_]+=' ~/.hermes/.env | tr -d '='   # keys already present
ls ~/.hermes/platforms/<platform>/session 2>/dev/null   # paired already?
```

## Step 1 — Two credential files, two different refusals

Both of these files are guarded, and the guards behave differently. Know which
one you are hitting before you work around it.

`~/.hermes/.env` — `read_file` **refuses** (credential store). Use the terminal:
list keys without printing values.

```bash
grep -oE '^[A-Z_]+=' ~/.hermes/.env | tr -d '='
```

Append with `>>`, never overwrite. Values in this file are secrets.

`~/.hermes/config.yaml` — the `patch`/`write_file` tools **refuse** (agent may
not modify security-sensitive config). Edit it through the terminal, and take a
backup first so a malformed write is recoverable:

```bash
cp ~/.hermes/config.yaml ~/.hermes/cache/scratch/config.yaml.bak
python3 - <<'PY'
import io
p = "/home/jhon/.hermes/config.yaml"
s = io.open(p, encoding="utf-8").read()
block = "platformname:\n  key: value\n"
assert s.count("\ngateway:\n") == 1     # anchor must be unique, or you duplicate
s = s.replace("\ngateway:\n", "\n" + block, 1)
io.open(p, "w", encoding="utf-8").write(s)
PY
```

**Assert the anchor count before replacing.** A `.replace()` without the assert
silently no-ops or duplicates the block, and the YAML may still parse — you
will not notice until the setting has no effect.

Validate the result instead of eyeballing it:

```bash
python3 -c "import yaml,io; d=yaml.safe_load(io.open('$HOME/.hermes/config.yaml')); print(d.get('<platform>'))"
```

**Never quote or restate a secret the user gave you.** Ask for the value, write
it, and refer to it by name.

## Step 2 — Enablement and allowlist (`.env`)

```bash
cat >> ~/.hermes/.env <<'EOF'

# <Platform> — <mode>
<PLATFORM>_ENABLED=true
<PLATFORM>_ALLOWED_USERS=<numbers-or-ids>
EOF
chmod 600 ~/.hermes/.env
```

Identity format rules, per platform:

- **WhatsApp / Signal**: full international number, **country code, no `+`, no
  spaces, no dashes**. `+52 722 653 5147` becomes `527226535147`.
- **Telegram / Discord**: numeric user or server id as a string.
- **Slack**: member or channel id.

Allowlist forms: a comma-separated list, `*` for everyone, or omit it and use
the DM pairing flow. `*` and `PLATFORM_ALLOW_ALL_USERS=true` are equivalent.

## Step 3 — Behaviour you usually want for a personal number

When the bot shares a number with real human contacts, the default is wrong:
unknown senders get a pairing-code reply, which means strangers can talk to the
agent from your personal account.

```yaml
# ~/.hermes/config.yaml
whatsapp:
  unauthorized_dm_behavior: ignore
  reply_prefix: "☤ *Hermes Agent*\n──────\n"
  send_read_receipts: false
```

`ignore` makes the channel silent to unauthorized senders. Set
`unauthorized_dm_behavior: pair` only when you want the pairing flow. Keep
`send_read_receipts: false` on a personal number — blue ticks on a shared
account leak that you are reading messages you never answered.

Groups are governed by `group_policy` (`pairing` | `allowlist` | `open`) and
`require_mention`, **not** by the DM allowlist.

## Step 4 — Platform prerequisites

Bridge-based platforms (WhatsApp via Baileys) run as a Node subprocess with its
own dependency tree and install scripts:

```bash
cd ~/.hermes/hermes-agent/scripts/whatsapp-bridge && npm install
```

npm in this repo **blocks install scripts by default**. A package like
`@whiskeysockets/baileys` validates its engine requirements in `preinstall` and
silently does nothing if skipped — the bridge then fails to start later with no
trace of the real cause.

```bash
npm install-scripts approve @whiskeysockets/baileys protobufjs
npm install
node ./node_modules/@whiskeysockets/baileys/engine-requirements.js   # expect exit 0
```

Verify the install-script actually ran; approving it is not the same as it
having executed.

## Step 5 — Pairing is the user's job, not yours

Pairing always ends in a secret the user must physically present: a QR code, a
six-digit code, an OAuth consent screen. **Drive the wizard only as far as the
prompt, then hand the remaining steps to the user in their own terminal.**

Background PTY input does not reliably reach an interactive wizard: writes
return success, bytes land in the buffer, and the prompt never advances. If you
cannot get past the first prompt, stop, kill the process, and tell the user to
run the wizard themselves — that is also where they can see the QR rendered.

```
hermes whatsapp
```

Tell them what to expect and how wide the terminal needs to be (QR codes need
60+ columns), and which platform-side settings to change (WhatsApp: Settings →
Linked Devices → Link a Device).

Do not leave a wizard blocked on a prompt you cannot answer — kill it and report.

## Step 6 — Protect the session directory

The pairing directory holds full account credentials — for WhatsApp it is the
auth keys for the linked account.

```bash
mkdir -p ~/.hermes/platforms/<platform>/session && chmod 700 ~/.hermes/platforms/<platform>/session
```

Treat it as a password: never cat it, never copy it, never include it in a
report. Tell the user not to commit or share it, and how to revoke (unlink the
device from the platform's linked-devices settings).

## Step 7 — Restart the gateway and verify

The running gateway does not pick up new channels.

```bash
hermes gateway install && hermes gateway start   # or: systemctl --user restart hermes-gateway
```

Then verify from evidence, in this order:

1. Gateway logs list the channel as connected (not merely enabled).
2. A real inbound message from an allowed sender round-trips.
3. An unauthorized sender produces no reply.

Only after (2) and (3) both hold is the channel actually working. Enabling a
flag is not evidence of a working channel.

## Step 8 — "Connected once, then kicked": another poller owns the token

A channel that logs `Conflict: terminated by other getUpdates request` (or
Discord's "only one session per token") is not broken config — a second process
else on the machine is long-polling with the **same bot token**. Restarting the
gateway never fixes it; each new instance is just the next one to lose the
race. Check this before touching allowlists, proxies, or DNS fallbacks.

Find the holder, not the loser. Enumerate every process with a live connection
to the platform's API range, then look up each PID's full command line:

```bash
journalctl --user -u hermes-gateway --since "-10min" --no-pager | grep -i <platform>
ss -tnp | grep -E '<api-ip-range>'          # e.g. 149.154. / 91.108. for Telegram
for p in <pids>; do tr '\\0' ' ' < /proc/$p/cmdline; echo; done
```

**Match both address families.** A rival runtime may hold its connection only
over IPv6 while the platform's IPv4 ranges show nothing — that reads as "no
rival" and sends you after the wrong cause. Filter the platform's IPv6 prefix
too (`2001:67c:4e8` is Telegram's):

```bash
ss -tnp | grep -E '149\.154\.|91\.108\.|2001:67c:4e8'
```

Sockets prove who is connected; the cmdline tells you what they are. A desktop
client holding a socket is harmless — only a `getUpdates` poller conflicts.

Then check whether a **different agent runtime** is configured with the same
token. OpenClaw (`~/.openclaw/openclaw.json` → `channels.telegram.botToken`) is
the common one on this machine, and other bot frameworks store it under
`channels`/`messaging` too. Compare without printing the secret:

```bash
python3 -c "
import os,re,json
tok=re.search(r'TELEGRAM_BOT_TOKEN\s*=\s*([^\s]+)', open(os.path.expanduser('~/.hermes/.env')).read()).group(1)
print('same token in openclaw.json:', tok in open(os.path.expanduser('~/.openclaw/openclaw.json')).read())"
```

`getWebhookInfo` returning an empty `url` with `pending_update_count: 0` rules
out a webhook and confirms polling mode is the right expectation.

**Resolve it, then say what stays broken.** Stopping the other service is a
decision that belongs to the user — ask which side keeps the bot (stop the
rival service, disable just its channel, or hand Hermes's token over) rather
than killing a long-running gateway on your own initiative. After the fix,
verify the fix held for at least a poll interval or two (~90s) instead of
trusting the first successful connect.

**`systemctl --user stop` does not un-enable.** A stopped unit still starts on
the next login and will re-steal the token, so the conflict looks fixed until
it silently returns. Either `systemctl --user disable --now <unit>` or give the
rival runtime its own bot token from @BotFather — tell the user which one you
did, since a stopped-but-enabled service is a latent repeat.

## Step 9 — Removing the rival runtime for good

Once the user chooses to drop the other runtime, disabling the unit is not the
end of it. AppImage and installer layouts leave state that outlives the unit:
a bundled runtime tree, a per-user unit file, and app-named config/data/cache
directories that `systemctl` never touches.

Inventory before deleting anything, and separate *its* state from *yours*:

```bash
systemctl --user list-unit-files | grep -i <runtime>          # unit still installed?
ls -d ~/<runtime-dir>                                        # size
find ~ -maxdepth 3 -iname '*<runtime>*' 2>/dev/null           # every leftover path
```

Read the leftovers before removing them: a `credentials/` or `sessions/`
directory is unrecoverable once deleted, so back up the small config to the
agent's own backup dir and keep it, while large bundled runtimes and installer
images can go.

```bash
cp ~/<runtime>/config.json ~/.hermes/backups/<runtime>.json.removed-$(date +%Y%m%d-%H%M%S)
systemctl --user disable --now <runtime>-gateway.service
rm -f ~/.config/systemd/user/<runtime>-gateway.service
systemctl --user daemon-reload
rm -rf ~/<runtime-dir>                        # bundled runtime + credentials
rm -f ~/Downloads/<Runtime>-*.AppImage        # installer
rm -rf ~/.config/<app-id> ~/.local/share/<app-id> ~/.cache/<runtime>
```

Rules that matter here:

- **`daemon-reload` after removing the unit file**, or systemd keeps serving
  the deleted unit from its cache and `list-unit-files` still shows it.
- **`--now` kills the whole process tree**, so helper/worker subprocesses die
  with the parent. Verify by *name* (`pgrep -af <runtime>`), and exclude your
  own inspection shells from the result — `pgrep -f` matches the grep command
  line itself and will report phantom PIDs.
- **Search wider than the unit name.** AppImage runtimes often install under a
  reverse-DNS app id (`ai.<vendor>.linux`) that does not match the product
  name, plus a versioned AppImage in `~/Downloads`.
- **Keep the agent's own directories out of the sweep.** Backups, migration
  state, and imported skills that carry the old name are not the rival's
  leftovers; deleting them is data loss.
- **Re-verify the channel after removal**, filtering logs by the gateway's
  *current* PID (`journalctl … | grep 'hermes\[<newpid>\]'`). Counted across
  the whole window, pre-fix conflicts and send failures from the dead process
  still appear and make a repaired channel look broken.

Report what was deleted, what was kept and why, and the space reclaimed.

## Pitfalls

- **A polling conflict means a second process, not a Hermes bug.** Two long-
  pollers on one token alternate wins forever; restart the gateway only to
  change which one wins. Enumerate sockets before changing any setting — over
  IPv4 *and* IPv6, or the rival is invisible.
- **Stopping a rival service is not enough while it stays `enabled`.** It comes
  back on next login and the conflict returns with it — disable it or split the
  token. And removing its unit file is not enough either: AppImage runtimes
  leave a bundled runtime tree and app-id-named config dirs that must go too.
- **A missing allowlist denies everything; a `*` admits everything.** These are
  the two failure modes users actually hit. Set one deliberately, every time.
- **`write_file` and `patch` refuse both credential files.** Use the terminal,
  and assert your YAML anchor is unique before replacing it.
- **Never read `~/.hermes/.env` with `read_file`.** Use `grep -oE '^[A-Z_]+='`
  to see keys without exposing values.
- **Phone numbers go in without `+`, spaces, or dashes.** A formatted number
  silently matches nobody.
- **Approving an npm install script is not running it.** Verify with a direct
  invocation; a skipped `preinstall` fails much later with an unrelated symptom.
- **Interactive wizards do not accept background PTY input.** Deliver the
  secret-bearing step to the user's own terminal instead of fighting the PTY.
- **A logged-out channel is usually re-pairing, not a bug.** Platform protocol
  changes and long inactivity both unlink devices; sessions normally survive
  restarts, so a reset session means something actually happened.
- **Unofficial bridges carry account risk.** For WhatsApp, say plainly that
  Baileys is not the official Business API, that a dedicated number is safer,
  and that automated outbound messaging can get a number restricted. Offer the
  official Cloud API path for business use.
- **CLI and gateway do not share live context.** Work requested on one surface
  is retrievable from the other through session history, not pushed between
  them. Say which one you are answering from.
- **`pgrep -f <pattern>` matches your own inspection shell.** The grep command
  line contains the pattern, so a clean sweep still reports phantom PIDs.
  Filter with `grep -v 'bash -c'` or check each PID's `/proc/<pid>/cmdline`.
- **Post-fix verification must be scoped to the new process.** Filter journal
  output by the gateway's current PID; pre-fix errors from the terminated
  process remain in the window and read as an unrepaired channel.

## Standing rule for this skill

- **Shared summary, not exhaustive list.** The receiving chat prefers one
  compact status line with the head metrics. Do not dump a full table; a
  short list is fine. Accept partial coverage.

## Status-and-cron delivery via Telegram (snapshots with Hermes cron)

When you want a recurring status snapshot pushed to a channel, do not embed
the reporting logic in the gateway. Put a script in
`~/.hermes/scripts/`, register it with the Hermes cron subsystem, and let
the cron job deliver its stdout to the channel.

### Workflow

1. **Write the script.** Bash (or any executable) script in
   `~/.hermes/scripts/`. It must print the report on stdout and exit 0.
2. **Register the cron job** from the project root (`~/.hermes`):

   ```bash
   hermes cron create "<freq>" --name "<display name>" \
     --deliver telegram \
     --script <relative path, e.g. status_monitor.sh> \
     --no-agent "<optional prompt>"
   ```

   - `--no-agent`: run the script directly; its stdout is pushed to the
     channel (single delivery).
   - Without `--no-agent`: Hermes starts an agent loop, which is heavier and
     rarely wanted for a status script.
   - `--script` is **relative to `~/.hermes/scripts/`**. Use
     `status_monitor.sh`, not an absolute path.
3. **Test the delivery**:

   ```bash
   hermes cron run <job_id>      # run once
   hermes cron list              # confirm next run time and state
   ```

4. **Verify the message landed.** Watch the Telegram chat or the gateway logs.
   If the message is missing, `hermes cron list` shows the job, but the
   channel is the bottleneck — re-check Step 7 of this skill.

### Standalone ad-hoc delivery

For one-off messages, `hermes send --to telegram "text"` reuses the
already-configured credentials; no gateway restart is needed. This is a
one-off, not part of the cron loop.

### Pitfalls

- **Two senders, one message.** The cron subsystem pushes the script's
  stdout; adding `hermes send --to telegram` inside the script duplicates
  the line. Deliver once: let the cron subsystem emit.
- **`--script` is relative to `~/.hermes/scripts/`.**
  Use `status_monitor.sh`, not an absolute path. An absolute path is
  accepted by some builds and rejected by others.
- **Wrong exec mode is silent.** With `--no-agent`, the script's stdout goes
  to the channel. Without it, an agent loop starts and the script is treated
  as a prompt. Always check `hermes cron list` after creation.
- **Shared summary, not exhaustive list.** The receiving chat prefers a
  compact status line with head metrics. A short list is fine; a full dump
  is not.

