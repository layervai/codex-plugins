# qURL plugin for Codex

Share an app running on your machine privately, straight from Codex, with
qURL: no deploy, no account, no API key, no signup. Install it as the
[repository README](../../README.md) says.

## What it adds

| Skill | How it runs | What it does |
|---|---|---|
| `qurl:qurl` | Codex uses it on its own whenever you want to share, publish or open something with qURL. You can also type `$qurl:qurl`. | The qURL agent skill. |
| `qurl:share` | Only when you type `$qurl:share [who]` | Share the app you're working on privately. Asks who it's for. |
| `qurl:approve` | Only when you type `$qurl:approve <code> [CRID]` | Let in a person who asked for access, by the six-digit code they gave you. Never by name. |

`share` and `approve` are Codex's equivalent of slash commands: their
`agents/openai.yaml` sets `allow_implicit_invocation: false`, so the model is
never offered them on its own and they add nothing to a session's context
until you type them. Both require qURL CLI 3.4.1 or newer, because an older
CLI publishes a resource that anyone with its address can open, and their
rules hold whatever the skill says.

The plugin has no MCP server. The skill already drives the `qurl` CLI, which
needs no account; a bundled server (`@layervai/qurl-mcp`) would start a Node
process through `npx` in every Codex session, shared or not, to reach the same
CLI.

## Keeping the bundled skill current (maintainers)

`skills/qurl/SKILL.md` is a copy of the skill served at
<https://layerv.ai/skills/qurl/SKILL.md>, byte for byte. The served file is the
source of truth: never edit the copy here. The `Check plugins` workflow
compares the two every day and on every PR, and fails while they differ. To
update it:

1. Copy the served file over the bundled one, from the repository root:

   ```bash
   curl -fsSL https://layerv.ai/skills/qurl/SKILL.md -o plugins/qurl/skills/qurl/SKILL.md
   ```

2. Raise `version` in `plugin.json` in the same PR. People get the new files
   when they run `codex plugin marketplace upgrade layerv`; the version is how
   they, and `codex plugin list`, tell one copy from another. Use a patch
   version for a new copy of the skill or a wording change, a minor version
   for a new command, and a major version when a command is removed or
   renamed. The version lives only in `plugin.json`, never in the marketplace
   entry.
3. If the skill's rules changed, check that `skills/share` and
   `skills/approve` still agree with them.
4. Run the checks the workflow runs:

   ```bash
   python3 scripts/check_manifests.py .
   python3 scripts/check_codex_install.py . -- npx -y @openai/codex@0.162.1
   ```

Raise the version for any other change to the plugin's files too.
