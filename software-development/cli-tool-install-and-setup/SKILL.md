---
name: cli-tool-install-and-setup
description: Use when installing a third-party CLI or SDK on Linux.
version: "1.0.0"
metadata:
  hermes:
    tags: [install, setup, cli, docker, credentials]
    related_skills: [hermes-agent, linux-system-maintenance]
---

# Installing and setting up third-party CLI tools

Getting a PyPI/npm CLI installed, verified, configured and actually usable on this
Manjaro host. Covers name disambiguation, isolated installs, credential handoff,
interactive setup wizards, and Docker-backed local stacks.

## When to Use

- "Can you install X?" / "instálame X" for any tool that is not already present.
- The user names a package that could refer to more than one project.
- The tool needs credentials or an interactive setup wizard before it works.
- The tool self-hosts a local stack (API + DB + worker) via Docker.

## Rules (always on)

- **Disambiguate the package name before installing anything.** Search PyPI/npm and the
  web first; one bare name often resolves to unrelated projects (e.g. `honcho` is both a
  Foreman clone for Procfile apps and an AI-agent memory server). Present the candidates
  and let the user pick. Installing the wrong one wastes the turn and can shadow a
  command they already rely on.
- **Never ask the user to paste a secret into chat.** When a tool needs an API key, tell
  them where to mint it and give the exact export line to put in their own shell. If a
  login/credential form must be driven by a browser, use the vault tools
  (`browser_vault_list` → `browser_vault_fill`), never `fill_input`.
- **When an install needs root and `sudo` demands a password, hand over the one-liner instead
  of asking for the password.** Give the exact command (`sudo pacman -S <pkg>`) and wait for
  them to run it — that is the safe default and needs no stored secret. Mention
  `SUDO_PASSWORD` in `~/.hermes/.env` as the alternative that lets the agent run it itself,
  and say plainly that a sudo password in a plaintext file gives any process running as that
  user full root; then let them choose. Never write the value yourself, and never accept it
  in chat.
- **Prefer the non-interactive configuration path.** Read the tool's config file or env
  vars and run it without the wizard. Interactive wizards need a real TTY and are not
  reliably drivable from a background PTY — see
  `references/interactive-wizard-ttys.md`.
- **Check the Hermes plugin catalog before hand-wiring an integration.** Many services
  ship an official/community Hermes plugin already listed in
  `~/.hermes/hermes-agent/plugin-catalog/*.yaml`, with `requires_env`, `provides_hooks`
  and a pinned upstream sha. Installing the plugin is usually less work and more
  maintainable than a bespoke integration — surface it as an option once the base tool
  works.
- **When the user says yes to the plugin, finish the wiring in the same turn.** Install,
  enable, and configure it end to end; do not stop at the install confirmation and leave
  the plugin inert. Configure with `hermes config set KEY VAL --force` (the `--force` goes
  after the value, and community-plugin keys require it) — never by hand-editing
  `config.yaml`. Read back with `hermes config get` instead of trusting the success line.
  See `references/hermes-plugin-integration.md`.
- **Prefer a local base URL when the service supports self-hosting.** Plugins with a
  base-URL setting skip API-key auth entirely for local URLs, which removes the credential
  step instead of deferring it.
- **Verify by executing, not by exit code.** Run `<tool> --version` and one real
  subcommand. A zero exit with empty output means the CLI is broken, not healthy —
  report the empty output rather than treating it as success.
- **Report the install honestly, including what is still blocked.** Say plainly which
  parts work now, which credential or manual step remains, and the exact command to
  finish. Do not describe a stack as "running" when it is only "installed".
- Answer in **Spanish** (neutral Latin American, no voseo).

## Procedure

1. **Resolve identity.** Web/PyPI search for the name; list distinct projects if >1 and
   ask which one.
2. **Check the installer already present.** On this host `uv` is normally in
   `~/.local/bin`; there is no `pipx`, and the system `python3`/`pip` belong to the
   Hermes-managed toolchain — never pip-install into it.
   ```bash
   which uv; uv --version
   ```
3. **Install isolated.**
   ```bash
   uv tool install <package-name>
   ```
   For an SDK used from code rather than a CLI, prefer a project venv
   (`uv venv && uv add <pkg>`) instead of a global tool install. When build scripts call a
   bare `python3`/`python` and nobody will remember to activate a venv, install into the
   interpreter's own user site instead — no activation needed, still outside the system tree:
   ```bash
   uv pip install --target "$(python3 -m site --user-site)" "<package>==<version>"
   python3 -c "import <package>; print(<package>.__version__)"
   ```
   Confirm the target is genuinely on `sys.path` first:
   `python3 -c "import site,sys; print(site.ENABLE_USER_SITE, site.getusersitepackages() in sys.path)"`.
   On a distro python that ships `EXTERNALLY-MANAGED` **and no `pip` at all**, `pip install`
   fails in every form (`No module named pip`, then the externally-managed refusal) — this is
   the only path that works without root.
4. **Verify the binary.**
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   <tool> --version && <tool> --help
   ```
   Inspect `--help` for the real subcommand names; some Typer/Click CLIs print nothing
   for a bare `--help` and only document per-subcommand help.
5. **Resolve credentials.** Identify the exact env var names from the error message or
   config template, then hand the user the mint URL + export line.
6. **Configure without the wizard.** Read the generated config template and set values
   directly; for OpenAI-compatible providers, reuse the OpenAI transport and only change
   the base URL rather than inventing a new provider.
7. **Start and health-check.** For Docker-backed stacks, verify the daemon is up
   (`docker info --format '{{.ServerVersion}}'`) before blaming the tool, then poll the
   service's health endpoint instead of sleeping a fixed amount.

## Pitfalls

- **Do not conclude "no wheel, must compile from source" from a `cp<version>` filename
  filter.** Many packages ship `py3-none-<platform>` wheels that are version-independent and
  install on a brand-new Python with no compiler present — capstone is one. List the real
  filenames (`https://pypi.org/pypi/<pkg>/<version>/json`) before reaching for an sdist or a
  build toolchain.
- **A binary installed by the package manager is not always on `PATH`.** Some distro packages
  (versioned toolchains especially) drop their executables in a private prefix such as
  `/usr/lib/<tool><ver>/bin/` and add nothing to `/usr/bin`, so `command -v <tool>` fails while
  the package is correctly installed. Check ownership before reinstalling:
  `pacman -Ql <pkg> | grep bin`, then symlink the binaries into `~/.local/bin`. Watch for names
  the package does *not* actually ship — a symlink pointing at a nonexistent file also reports
  `command not found`, which looks identical to "not installed".
- **A bare `<tool> --help` that prints nothing is a failure, not a quirk.** Check
  `<tool> <subcommand> --help` for the actual surface before reporting the install done.
- **`process_manage` coerces purely numeric `data` arguments to int**, so
  `submit data="4"` is rejected by schema validation and never reaches the PTY. Numeric
  menu answers cannot be delivered this way; switch to the non-interactive path rather
  than retrying with `/proc/<pid>/fd/0`, which does not drive a TTY either.
- **Config templates ship with placeholder secrets** like `OPENAI_API_KEY =
  "your-api-key-here"`. Treat any literal API key already present in a generated config
  as a placeholder, not a working credential.
- **A model name in your own config is not a credential.** Grepping your agent config for
  a provider name can hit an unrelated model identifier (e.g. `openrouter/free`) and look
  like a stored key — confirm a key is actually present before telling the user you found
  one, and redact it when quoting context.
- **Do not mutate Hermes's own venv to install a tool.** `pip install` into the
  toolchain Python pollutes the agent runtime and can break unrelated skills.
- **Install and enable are two separate plugin steps.** `hermes plugins install <name>`
  clones the plugin but leaves it inert until `hermes plugins enable <name>` resolves its
  dependencies and reloads the gateway. Reporting the install as done at that point is
  wrong.
- **Plugin config keys are top-level, not namespaced under the provider.** For a memory
  plugin the path is `honcho.baseUrl`, not `memory.honcho.baseUrl`. When `config set`
  rejects a path it prints a `Did you mean:` line — that is the authoritative path.
- **A local base URL can replace a plugin credential.** Plugins that read a base-URL
  setting skip API-key auth when the URL is local, even if the catalog entry lists
  `requires_env`.

## Reporting shape

Verdict first (installed / blocked), then the verified evidence (`--version` output),
then the exact remaining step the user must run themselves with their own credentials.
Offer the adjacent integration (plugin, SDK wiring) as a question, not as assumed scope.

## References

- `references/interactive-wizard-ttys.md` — TTY-gated wizards: what fails, what to do.
- `references/local-service-stacks.md` — Docker-composed stacks, ports, base URLs.
- `references/hermes-plugin-integration.md` — plugin install/enable, `config set` quirks,
  local-URL auth skip, gateway peer identity.