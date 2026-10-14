#!/usr/bin/env python3
"""Offline checks of the marketplace and plugin manifests (standard library only).

Codex skips a marketplace entry it cannot resolve instead of failing, so a
broken entry would install nothing without an error. These checks fail
loudly instead. They follow the Agent Plugins 1.0.0 plugin schema
(https://agent-plugins.org/schemas/1.0.0/plugin.schema.json) and the Codex
marketplace format (https://developers.openai.com/plugins/build/plugins).

Usage: python3 scripts/check_manifests.py [REPO_ROOT]
"""

import json
import re
import sys
from pathlib import Path

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
PLUGIN_KEYS = {
    "$schema", "name", "version", "description", "author", "homepage",
    "repository", "license", "keywords", "extensions",
}
AUTHOR_KEYS = {"name", "email", "url"}
NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
# Semantic Versioning 2.0.0, from https://semver.org (no leading "v").
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
INSTALL_POLICIES = {"AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"}
AUTH_POLICIES = {"ON_INSTALL", "ON_USE"}
# Skills that must load only when the user types them, like a slash command,
# and must keep the CLI floor below which a publish is public by default.
COMMAND_SKILLS = {"share", "approve"}
CLI_FLOOR = "3.4.1"

errors = []


def fail(msg):
    errors.append(msg)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"{path}: cannot parse: {exc}")
        return None


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        fail(f"{path}: no YAML frontmatter")
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        fail(f"{path}: frontmatter is not closed")
        return {}
    fields = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and not key.startswith((" ", "\t")):
            fields[key.strip()] = value.strip()
    return fields


def check_plugin(plugin_dir, entry_name):
    manifest_path = plugin_dir / "plugin.json"
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        fail(f"{manifest_path}: must be a JSON object")
        return
    for key in sorted(set(manifest) - PLUGIN_KEYS):
        fail(f"{manifest_path}: unknown top-level field {key!r} (Agent Plugins 1.0.0 allows none)")
    if manifest.get("$schema") != PLUGIN_SCHEMA:
        fail(f"{manifest_path}: $schema must be {PLUGIN_SCHEMA}")
    name = manifest.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > 64:
        fail(f"{manifest_path}: name {name!r} is not a valid plugin name")
    if name != entry_name:
        fail(f"{manifest_path}: name {name!r} differs from the marketplace entry {entry_name!r}")
    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        fail(f"{manifest_path}: version {version!r} is not a semantic version (MAJOR.MINOR.PATCH)")
    for key in ("description", "homepage", "repository", "license"):
        if key in manifest and not isinstance(manifest[key], str):
            fail(f"{manifest_path}: {key} must be a string")
    author = manifest.get("author", {})
    if not isinstance(author, dict) or set(author) - AUTHOR_KEYS or not all(
        isinstance(v, str) for v in author.values()
    ):
        fail(f"{manifest_path}: author must be an object of name, email and url strings")
    keywords = manifest.get("keywords", [])
    if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
        fail(f"{manifest_path}: keywords must be a list of strings")
    extensions = manifest.get("extensions", {})
    if not isinstance(extensions, dict) or not all(isinstance(v, dict) for v in extensions.values()):
        fail(f"{manifest_path}: extensions must map namespaces to objects")
    else:
        interface = extensions.get("com.openai", {}).get("interface", {})
        prompts = interface.get("defaultPrompt", [])
        prompts = [prompts] if isinstance(prompts, str) else prompts
        # Codex drops prompts past these limits (core-plugins manifest.rs).
        if len(prompts) > 3 or any(not isinstance(p, str) or len(p) > 128 for p in prompts):
            fail(f"{manifest_path}: defaultPrompt takes at most 3 strings of at most 128 characters")

    skills_dir = plugin_dir / "skills"
    skills = sorted(p for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []
    if not skills:
        fail(f"{skills_dir}: no skills")
    for skill_dir in skills:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            fail(f"{skill_dir}: no SKILL.md")
            continue
        fields = frontmatter(skill_md)
        if fields.get("name") != skill_dir.name:
            fail(f"{skill_md}: frontmatter name {fields.get('name')!r} must be {skill_dir.name!r}")
        if not fields.get("description"):
            fail(f"{skill_md}: frontmatter needs a description")
    for command in sorted(COMMAND_SKILLS):
        skill_md = skills_dir / command / "SKILL.md"
        policy = skills_dir / command / "agents" / "openai.yaml"
        if not skill_md.is_file():
            fail(f"{skill_md}: missing")
            continue
        if CLI_FLOOR not in skill_md.read_text(encoding="utf-8"):
            fail(f"{skill_md}: must require qURL CLI {CLI_FLOOR} or newer")
        if not policy.is_file() or not re.search(
            r"(?m)^\s+allow_implicit_invocation:\s*false\s*$", policy.read_text(encoding="utf-8")
        ):
            fail(f"{policy}: must set policy.allow_implicit_invocation: false")
    print(f"ok: plugin {name} {version} with skills {', '.join(s.name for s in skills)}")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    market_path = root / ".agents" / "plugins" / "marketplace.json"
    market = load_json(market_path)
    if isinstance(market, dict):
        if not isinstance(market.get("name"), str) or not NAME_RE.match(market["name"]):
            fail(f"{market_path}: name {market.get('name')!r} is not a valid marketplace name")
        plugins = market.get("plugins")
        if not isinstance(plugins, list) or not plugins:
            fail(f"{market_path}: plugins must be a non-empty list")
            plugins = []
        seen = set()
        for i, entry in enumerate(plugins):
            where = f"{market_path}: plugins[{i}]"
            if not isinstance(entry, dict):
                fail(f"{where}: must be an object")
                continue
            entry_name = entry.get("name")
            if entry_name in seen:
                fail(f"{where}: duplicate plugin {entry_name!r}")
            seen.add(entry_name)
            source = entry.get("source")
            path = source.get("path") if isinstance(source, dict) else source
            if isinstance(source, dict) and source.get("source") != "local":
                fail(f"{where}: source.source must be 'local' for a plugin kept in this repo")
            if not isinstance(path, str) or not path.startswith("./"):
                fail(f"{where}: source path must start with ./")
                continue
            plugin_dir = (root / path).resolve()
            if root not in plugin_dir.parents or not plugin_dir.is_dir():
                fail(f"{where}: source path {path} is not a directory inside the repository")
                continue
            policy = entry.get("policy", {})
            if policy.get("installation") not in INSTALL_POLICIES:
                fail(f"{where}: policy.installation must be one of {sorted(INSTALL_POLICIES)}")
            if policy.get("authentication") not in AUTH_POLICIES:
                fail(f"{where}: policy.authentication must be one of {sorted(AUTH_POLICIES)}")
            if not isinstance(entry.get("category"), str):
                fail(f"{where}: category is required")
            if "version" in entry:
                fail(f"{where}: keep the version only in the plugin's plugin.json")
            check_plugin(plugin_dir, entry_name)
    for msg in errors:
        print(f"::error::{msg}")
    if errors:
        sys.exit(1)
    print("ok: marketplace", market_path.relative_to(root))


if __name__ == "__main__":
    main()
