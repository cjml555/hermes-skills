# Wiring an installed service into Hermes as a plugin

How to connect a freshly installed third-party service to Hermes itself, once the base
tool works. Applies to memory providers, image/web backends, and any plugin-catalog
service.

## Locate the plugin before doing anything else

The catalog at `~/.hermes/hermes-agent/plugin-catalog/<name>.yaml` is the source of truth.
Each entry declares `subdir`, a pinned upstream `sha`, `requires_env`, `provides_hooks`,
and `docs_url`. Reading it tells you the credential the plugin wants before you start.

Probing the CLI is even faster: running the plugin's own subcommand when it is not yet
installed returns the exact install command.

```bash
hermes honcho --help
# → The 'honcho' memory plugin is not installed. Install it with: hermes plugins install honcho
```

## Install and enable

```bash
hermes plugins install <name>     # clones pinned sha into ~/.hermes/plugins/<name>
hermes plugins enable <name>      # resolves Python deps, reloads the gateway
```

Install and enable are separate steps; install alone leaves the plugin inert. Enable
reports whether a session or gateway reload is needed, or that neither is.

## Configure with `hermes config set`, never by editing YAML

A stray indent in `config.yaml` breaks the live gateway. Always go through the CLI.

**Plugin config keys live at the top level, not under the provider namespace.** Even when
the plugin IS the memory provider, the path is `honcho.baseUrl`, not
`memory.honcho.baseUrl`. When a path is wrong the CLI replies with a `Did you mean:`
line — that suggestion is the authoritative path, so take it rather than guessing.

```bash
hermes config set memory.provider honcho
hermes config set honcho.enabled true
hermes config set honcho.baseUrl http://localhost:8000 --force
```

Two flags that decide whether the write lands:

- **`--force` goes AFTER the value.** `hermes config set KEY VAL --force` works;
  `hermes config set --force KEY VAL` prints the flag's help text and writes nothing.
- **`--force` is required for plugin keys.** The schema validator does not know a
  community plugin's keys, so they are rejected as unrecognized without it. Recognized
  keys like `enabled` do not need it.

Verify every write by reading it back — `hermes config get <key>` — rather than trusting
the success line:

```bash
hermes config get honcho
```

## Local stacks skip API-key auth

Plugins that support a self-hosted instance expose a base-URL setting, and a **local URL
auto-skips API-key authentication**. This is the clean path when the base tool runs a
local Docker stack: set the base URL to the local endpoint and no plugin credential is
needed, even when the plugin's catalog entry lists `requires_env`. Keep the hosted-service
option in mind as the fallback if the local stack cannot be brought up.

## Peer identity for single-operator gateways

On a gateway (Telegram, Discord) every runtime user arrives with a platform-native ID, so
a CLI-configured peer name and a Telegram chat end up as two separate identities by
default. For a single-operator deployment, collapse them with the plugin's
pin-user-peer setting so every platform shares one peer and one memory history. The
plugin README documents the full resolver ladder (alias → prefix → raw ID fallback) when
more than one real user needs distinct peers.