# LayerV plugins for Codex

A Codex plugin marketplace from LayerV. Its one plugin, `qurl`, lets you share
an app running on your machine privately, straight from Codex, with qURL™: no
deploy, no account, no API key, no signup.

Install it with two commands:

```bash
codex plugin marketplace add layervai/codex-plugins
codex plugin add qurl@layerv
```

Then start Codex and ask it to share what you're working on ("share my app
with ana@example.com"), or type one of the plugin's commands:

| Type | What it does |
|---|---|
| `$qurl:share [who]` | Share the app you're working on privately. Asks who it's for. |
| `$qurl:approve <code> [CRID]` | Let in a person who asked for access, by the six-digit code they gave you. Never by name. |

The first time it shares, Codex installs the `qurl` CLI for you. To get a new
version of the plugin later, run `codex plugin marketplace upgrade layerv`.

See [plugins/qurl](plugins/qurl) for what the plugin contains.

## License

[MIT](LICENSE)
