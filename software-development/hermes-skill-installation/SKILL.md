---
name: hermes-skill-installation
description: Install Hermes skills from catalogs or repos via CLI.
version: 1.0.0
---

# Hermes Skill Installation Workflow

This skill covers the reliable workflow for installing skills in Hermes Agent when the catalog UI doesn't show approval cards or when direct CLI installation is needed.

## When to Use This Workflow

Use this when:

- The catalog UI doesn't show an approval card after searching for skills
- Skills appear as "not_connected" in the catalog despite being found
- You need to install skills from specific GitHub repos or catalogs directly
- You want to batch install multiple skills without UI interaction
- The `manage_catalog` tool returns "not_connected" state without presenting a visible approval card

## Step 1: Verify Skill Availability

Before installing, check if the skill exists and get the exact identifier:

```bash
# Search in Hermes skills index
hermes skills search "<skill-name-or-keyword>"

# Or search the catalog via tool_call with manage_catalog
# action=search, kind=skill, query="<keyword>"

# Check the repo directly on GitHub or skills.sh
# Example: https://skills.sh/juliusbrussee/caveman
```

## Step 2: Install Skills via CLI

Use the Hermes skills CLI for reliable installation:

```bash
# Install a single skill
hermes skills install "skills-sh/<org>/<repo>/<skill>" --yes

# Install multiple skills in batch
for skill in <skill1> <skill2> <skill3>; do
  hermes skills install "skills-sh/<org>/<repo>/$skill" --yes
done

# Install with --force when name conflicts exist
hermes skills install "skills-sh/<org>/<repo>/<skill>" --force --yes
```

## Step 3: Handle Common Issues

### Stale Index Entry

If you get: "Error: 'skills-sh/...' is listed in the hermes-index index, but its files no longer exist upstream"

- The skill has been renamed or removed by its author
- Try searching for alternatives with `hermes skills search`
- Check the repo directly on GitHub for the current skill name

### Security Scan Blocks

If you get: "Scan: <skill> (...) Verdict: DANGEROUS"

- The skill contains potentially dangerous patterns (persistence, exfiltration, execution risks)
- Do NOT install with --force - review the findings first
- Ask the author to fix the security issues or find an alternative skill

### Name Conflicts

If you get: "Warning: '<skill>' is already installed at <skill>"

- Another skill with the same name is already installed
- Use --force to replace the existing skill
- Be aware this will overwrite the existing skill

### Verification After Installation

Always verify skills are properly installed:

```bash
# List all installed skills
hermes skills list

# Check a specific skill
hermes skills list | grep "<skill-name>"

# Verify status is "enabled"
hermes skills list | grep "<skill>" | grep "enabled"
```

## Step 4: Batch Installation Patterns

### Installing All Skills from a Catalog

When you want to install every skill from a catalog (like "obra/superpowers" or "juliusbrussee/caveman"):

1. First, search the catalog to get all skill IDs
2. Install each one individually (no bulk install option exists)
3. Use a loop for efficiency:

```bash
# Example for juliusbrussee/caveman catalog
skills_to_install=(
  "caveman"
  "cavecrew"
  "caveman-commit"
  "caveman-evidence-review"
  "caveman-explore"
  "caveman-help"
)

for skill in "${skills_to_install[@]}"; do
  hermes skills install "skills-sh/juliusbrussee/caveman/$skill" --yes
done
```

### Handling Conditional Installation

Some skills may have variants (like language-specific versions):

- caveman-cn and caveman-es both install as "caveman" and conflict
- Install the base caveman first, then use --force for variants if needed
- Or choose only the variant you need based on language preferences

## Step 5: Upstream Agent-Skill Bundles (vendors that ship their own installer)

Many vendors publish plain `SKILL.md` trees with install instructions for Claude Code/Codex/etc. — e.g. Cloudflare's `developers.cloudflare.com/agent-setup/prompt.md`. Hermes is an "other agent": follow the vendor's generic branch, not the Claude plugin commands (`claude plugin ...` installs into Claude, never into Hermes).

```bash
npx -y skills add <org>/<repo> --skill '*' --yes --global
```

- Skills land in `~/.agents/skills/<name>`; the ones Hermes can see are symlinked from `~/.hermes/skills/<name>` already. Verify with:
  `for s in <names>; do [ -e ~/.hermes/skills/$s ] && echo "OK $s" || echo "MISSING $s"; done`
- The installer prints one `✗ <skill> → PromptScript: ... does not support global skill installation` line per skill — that is a per-target adapter declining, not a failed install. Confirm by listing the directories above rather than trusting those lines.
- Skills are loaded per session: after a global install, a fresh session (or an explicit reload) is what picks them up.
- Vendor prompts usually also ask for MCP servers. Register those separately with `hermes mcp add` / `hermes mcp install` — load the `hermes-agent` skill and read its `references/native-mcp.md`. Do not translate a vendor's `mcp add` command verbatim; Hermes' flags are `--url`, `--auth oauth|header`, `--connect-timeout`.

## Best Practices

- Always start with `hermes skills search` or catalog search to confirm the skill exists
- Use --yes to skip confirmation prompts when installing multiple skills
- Prefer CLI installation over the `manage_catalog` tool when batch installing
- Always run `hermes skills list` after installation to verify success
- Do NOT install skills that return a DANGEROUS security verdict, even with --force
- Use --force only when intentionally replacing an existing skill with the same name
- Install skills one-by-one in a loop to see individual results for each
- Do not retry failed installations without investigating the root cause first

## Troubleshooting Reference

### Skill Shows as "not_connected" in Catalog

This is a UI state issue - the skill may be installed but not marked as connected in the catalog UI.
Solution: Ignore the catalog UI state and verify with `hermes skills list`.

### manage_catalog Tool Doesn't Show Approval Card

This is a known issue with the `manage_catalog` tool - it may settle successfully but not present a visible approval card in the user interface.
Solution: Use the CLI directly with `hermes skills install` instead.

### Installation Appears to Succeed but Skill Doesn't Appear

1. Check if you are looking in the right profile
2. Verify installation completed (check logs at ~/.hermes/logs/)
3. Some skills require restarting Hermes to load fully
4. Check for naming conflicts with existing skills
5. Wait a few seconds and re-run `hermes skills list`

### "Could Not Download" Errors

1. Verify the skill identifier is correct
2. Check internet connectivity
3. The skill may have been removed from the index
4. Search for alternatives or check the repo directly

## User Preferences

- Use --yes flag to skip confirmation prompts during batch installation
- Check `hermes skills list` after each batch to verify success
- Be cautious of skills with security scan warnings (DANGEROUS verdict)
- Use --force only when intentionally replacing an existing skill with the same name

## Related Tools and Commands

- `hermes skills search <query>` - Find skills in the index
- `hermes skills install <id> --yes` - Install a skill (use --force to override conflicts)
- `hermes skills list` - View installed skills and their status
- `hermes skills remove <name>` - Remove an installed skill
- `hermes skills update` - Update installed skills to latest versions
- `hermes skills inspect <id>` - View skill details without installing

## References

- Official Hermes skills documentation: https://hermes-agent.nousresearch.com/docs/
- Skills.sh catalog: https://skills.sh/

## Examples

### Installing a Single Skill

```bash
hermes skills install "skills-sh/juliusbrussee/caveman/caveman" --yes
```

### Installing Multiple Skills from One Catalog

```bash
for skill in caveman cavecrew caveman-commit caveman-evidence-review caveman-explore caveman-help; do
  hermes skills install "skills-sh/juliusbrussee/caveman/$skill" --yes
done
```

### Handling a Known Conflict

```bash
# First install the base skill
hermes skills install "skills-sh/juliusbrussee/caveman/caveman" --yes

# Then install a variant that conflicts (language-specific version)
hermes skills install "skills-sh/juliusbrussee/caveman/caveman-es" --force --yes
```

### Verifying Installation

```bash
hermes skills list | grep -E "caveman|caveman|caveman-commit"
```
