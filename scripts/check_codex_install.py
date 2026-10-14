#!/usr/bin/env python3
"""Install every plugin of this marketplace with the real Codex CLI and check what it loaded.

Codex has no validate command, and it skips a marketplace entry it cannot
resolve instead of failing, so a zero exit code proves nothing. This adds the
checkout as a marketplace in a throwaway HOME and CODEX_HOME, installs each
plugin, and then requires that Codex:

- lists the plugin as installed and enabled, at the version in its plugin.json;
- loads one skill per skills/<name>/ directory, named <plugin>:<name>;
- installed each SKILL.md byte for byte;
- offers the model only the skills it may use on its own: a skill whose
  agents/openai.yaml sets allow_implicit_invocation: false must be absent
  from the model's skill list (it loads only when the user types it).

Usage: python3 scripts/check_codex_install.py REPO_ROOT -- CODEX_COMMAND...
  e.g. python3 scripts/check_codex_install.py . -- npx -y @openai/codex@0.162.1
"""

import json
import os
import re
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

errors = []


def fail(msg):
    errors.append(msg)
    print(f"::error::{msg}")


def run(codex, args, env, cwd):
    proc = subprocess.run(codex + args, env=env, cwd=cwd, capture_output=True, text=True, timeout=300)
    print(f"$ codex {' '.join(args)}  (exit {proc.returncode})")
    if proc.returncode != 0:
        print(proc.stdout, proc.stderr, sep="\n")
        raise SystemExit(f"::error::codex {' '.join(args)} failed")
    return proc.stdout


def skills_list(codex, env, cwd):
    """Ask the Codex app server (JSON-RPC over stdio) which skills it loaded."""
    proc = subprocess.Popen(codex + ["app-server"], env=env, cwd=cwd, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def wait(request_id, timeout=180):
        end = time.time() + timeout
        while time.time() < end:
            ready, _, _ = select.select([proc.stdout], [], [], 1)
            if not ready:
                continue
            line = proc.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("id") == request_id:
                if "error" in msg:
                    raise SystemExit(f"::error::app-server request {request_id}: {msg['error']}")
                return msg["result"]
        raise SystemExit(f"::error::app-server did not answer request {request_id}")

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "codex-plugins-ci", "version": "1.0.0"}}})
        wait(1)
        send({"jsonrpc": "2.0", "method": "initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "skills/list",
              "params": {"cwds": [cwd], "forceReload": True}})
        return wait(2)["data"]
    finally:
        proc.terminate()


def model_skill_names(prompt_input):
    """Skill names in the model-visible 'Available skills' list."""
    texts = []

    def walk(node):
        if isinstance(node, str):
            texts.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(prompt_input))
    names = set()
    for text in texts:
        if "### Available skills" in text:
            section = text.split("### Available skills", 1)[1]
            names.update(re.findall(r"(?m)^- ([^:\s]+(?::[^:\s]+)?): ", section))
    return names


def main():
    if "--" not in sys.argv:
        raise SystemExit(__doc__)
    split = sys.argv.index("--")
    root = Path(sys.argv[1] if split > 1 else ".").resolve()
    codex = sys.argv[split + 1:]
    market = json.loads((root / ".agents/plugins/marketplace.json").read_text())

    with tempfile.TemporaryDirectory(prefix="codex-plugin-check-") as tmp:
        tmp = Path(tmp)
        env = dict(os.environ, HOME=str(tmp / "home"), CODEX_HOME=str(tmp / "codex"))
        work = tmp / "work"
        for d in (tmp / "home", tmp / "codex", work):
            d.mkdir()
        run(codex, ["plugin", "marketplace", "add", str(root)], env, work)
        expected = {}
        for entry in market["plugins"]:
            plugin_dir = (root / entry["source"]["path"]).resolve()
            manifest = json.loads((plugin_dir / "plugin.json").read_text())
            plugin_id = f"{entry['name']}@{market['name']}"
            run(codex, ["plugin", "add", plugin_id], env, work)
            expected[plugin_id] = (plugin_dir, manifest["version"])

        listing = json.loads(run(codex, ["plugin", "list", "--json"], env, work))
        installed = {p["pluginId"]: p for p in listing.get("installed", [])}
        for plugin_id, (_, version) in expected.items():
            got = installed.get(plugin_id)
            if not got or not got.get("installed") or not got.get("enabled"):
                fail(f"{plugin_id}: not listed as installed and enabled: {got}")
            elif got.get("version") != version:
                fail(f"{plugin_id}: Codex installed version {got.get('version')}, plugin.json says {version}")
            else:
                print(f"ok: {plugin_id} {version} installed, enabled")

        loaded = {}
        for entry in skills_list(codex, env, str(work)):
            for err in entry.get("errors", []):
                fail(f"Codex reported a skill error: {err}")
            for skill in entry.get("skills", []):
                if skill.get("pluginId") in expected:
                    loaded[skill["name"]] = skill
        offered = model_skill_names(run(codex, ["debug", "prompt-input", "hi"], env, str(work)))

        for plugin_id, (plugin_dir, _) in expected.items():
            plugin = plugin_id.split("@", 1)[0]
            want = {}
            for skill_dir in sorted(p for p in (plugin_dir / "skills").iterdir() if p.is_dir()):
                want[f"{plugin}:{skill_dir.name}"] = skill_dir
            got = {name for name, s in loaded.items() if s.get("pluginId") == plugin_id}
            if got != set(want):
                fail(f"{plugin_id}: Codex loaded skills {sorted(got)}, expected {sorted(want)}")
            for name, skill_dir in want.items():
                skill = loaded.get(name)
                if not skill:
                    continue
                if not skill.get("enabled"):
                    fail(f"{name}: loaded but disabled")
                if Path(skill["path"]).read_bytes() != (skill_dir / "SKILL.md").read_bytes():
                    fail(f"{name}: installed SKILL.md differs from {skill_dir / 'SKILL.md'}")
                policy = skill_dir / "agents" / "openai.yaml"
                explicit_only = policy.is_file() and re.search(
                    r"(?m)^\s+allow_implicit_invocation:\s*false\s*$", policy.read_text())
                if explicit_only and name in offered:
                    fail(f"{name}: offered to the model although it is explicit-only")
                if not explicit_only and name not in offered:
                    fail(f"{name}: missing from the model's skill list")
                mode = "only when typed ($" + name + ")" if explicit_only else "offered to the model"
                print(f"ok: skill {name} loaded, {mode}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
