"""What a plugin from a NON-Verified organization may ship to the Claude plugin directory.

The directory's portal refuses, for an organization Anthropic has not marked Verified (and
there is no way to ask to become one), any version whose plugin folder:

  LOCAL_CODE_MCP_SERVER      declares an MCP server that runs on the user's computer
                             (`.mcp.json` with a `command`); only a remote `url` server stays
  LOCAL_CODE_FILE_TYPE       holds a file that is not Markdown, text, JSON, YAML or a PNG / JPEG /
                             GIF / WebP / ICO image; a package-manager configuration file
                             (pyproject.toml, uv.lock, ...); a text file starting with `#!`, not
                             UTF-8, or holding a NUL byte; a path with `:` or `\\`
  LOCAL_CODE_FRONTMATTER_KEY has a SKILL.md frontmatter key outside the allowed list, or
                             frontmatter that is not plain `key: value` lines between two `---`
  UNPINNED_UVX               launches a package (moot once no local server is declared)

These rules came from the portal's findings (2026-11), ahead of the public docs. The allowed
frontmatter list is not published: `name` and a one-line `description` are what every skill
needs and what this module keeps.

`transform` turns a mirrored skill folder into one that passes: frontmatter reduced, T-SQL
helpers carried as Markdown (they are reference scripts a person runs by hand, so a fenced
code block keeps them usable), anything else outside the allowed types dropped. `audit` checks
a finished plugin folder against the same rules, so an export that would be refused never
reaches the public repo.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ALLOWED_SUFFIXES = frozenset({".md", ".txt", ".json", ".yaml", ".yml",
                              ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"})
#: Script types carried as a fenced Markdown file (`x.sql` -> `x.sql.md`), with the fence's
#: language. Anything else outside ALLOWED_SUFFIXES is dropped.
AS_MARKDOWN = {".sql": "sql"}
#: Frontmatter keys a community skill keeps.
FRONTMATTER_KEYS = ("name", "description")
#: Files the plugin root may not hold: a local MCP server, hooks, LSP, monitors.
FORBIDDEN_NAMES = frozenset({".mcp.json", "hooks.json", ".lsp.json", "monitors.json"})


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")   # a T-SQL script saved on Windows


def _yaml_scalar(value: str) -> str:
    """One line, unquoted when YAML reads it back unchanged, else double-quoted."""
    value = " ".join(str(value).split())
    try:
        if yaml.safe_load(f"k: {value}") == {"k": value} and not value.startswith(("'", '"')):
            return value
    except yaml.YAMLError:
        pass
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)


def frontmatter(text: str) -> str:
    """Reduce a SKILL.md frontmatter to FRONTMATTER_KEYS, each a plain one-line value."""
    m = _FM.match(text)
    if not m:
        raise ValueError("SKILL.md has no frontmatter between two --- lines")
    data = yaml.safe_load(m.group(1)) or {}
    missing = [k for k in FRONTMATTER_KEYS if not str(data.get(k) or "").strip()]
    if missing:
        raise ValueError(f"SKILL.md frontmatter lacks {missing}")
    head = "".join(f"{k}: {_yaml_scalar(data[k])}\n" for k in FRONTMATTER_KEYS)
    return f"---\n{head}---\n" + text[m.end():]


def _as_markdown(rel: str, text: str, lang: str) -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    name = rel.rsplit("/", 1)[-1]
    body = text.lstrip("﻿").replace("\r\n", "\n").strip("\n")
    return (f"# {name}\n\nCopy the script below and run it yourself; it is reference "
            f"material, nothing in this plugin runs it.\n\n{fence}{lang}\n{body}\n{fence}\n")


def transform(files: dict[str, bytes], replace=()) -> tuple[dict[str, bytes], dict]:
    """Make one mirrored skill folder community-safe.

    `files` maps a path relative to the mirror root to its bytes. `replace` is a sequence of
    {file, old, new}: an exact text edit on a copied file, for prose that points at a file this
    step drops. Returns (new files, report). Raises if a replacement no longer matches, or a
    dropped file is still named in the folder's text, so a skill never ships a dead pointer.
    """
    out: dict[str, bytes] = {}
    renamed: dict[str, str] = {}
    dropped: list[str] = []
    for rel, data in sorted(files.items()):
        suffix = Path(rel).suffix.lower()
        if suffix in ALLOWED_SUFFIXES:
            out[rel] = data
        elif suffix in AS_MARKDOWN:
            new = rel + ".md"
            out[new] = _as_markdown(rel, _decode(data), AS_MARKDOWN[suffix]).encode("utf-8")
            renamed[rel.rsplit("/", 1)[-1]] = new.rsplit("/", 1)[-1]
        else:
            dropped.append(rel)

    for item in replace or ():
        rel = item["file"]
        if rel not in out:
            raise RuntimeError(f"replace: {rel} is not in the copied folder")
        text = out[rel].decode("utf-8")
        if item["old"] not in text:
            raise RuntimeError(f"replace: the text to change is no longer in {rel}; "
                               f"update publish.yaml: {item['old'][:80]!r}")
        out[rel] = text.replace(item["old"], item["new"]).encode("utf-8")

    converted = {rel + ".md" for rel in files if Path(rel).suffix.lower() in AS_MARKDOWN}
    for rel in list(out):
        if not rel.endswith(".md") or rel in converted:   # a script's own text stays as it is
            continue
        text = out[rel].decode("utf-8")
        for old, new in renamed.items():
            text = re.sub(re.escape(old) + r"(?!\.md)", new, text)
        if rel.rsplit("/", 1)[-1] == "SKILL.md":
            text = frontmatter(text)
        out[rel] = text.encode("utf-8")

    for rel in dropped:
        base = rel.rsplit("/", 1)[-1]
        named = [r for r, d in out.items() if r.endswith(".md") and base in d.decode("utf-8")]
        if named:
            raise RuntimeError(f"{rel} is not shipped in the plugin but {named[0]} still names "
                               f"it; add a `replace` for that text in publish.yaml")
    return out, {"converted": sorted(renamed), "dropped": dropped}


def audit(plugin_dir: Path) -> list[str]:
    """Every reason the directory would refuse this plugin folder from a community org."""
    problems: list[str] = []
    for path in sorted(p for p in plugin_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(plugin_dir).as_posix()
        name, suffix = path.name, path.suffix.lower()
        if name in FORBIDDEN_NAMES:
            problems.append(f"{rel}: {name} is refused from a community organization")
            continue
        if ":" in rel or "\\" in rel:
            problems.append(f"{rel}: path holds ':' or '\\'")
        if suffix not in ALLOWED_SUFFIXES:
            problems.append(f"{rel}: file type {suffix or '(none)'} is not allowed")
            continue
        if suffix in IMAGE_SUFFIXES:
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            problems.append(f"{rel}: holds a NUL byte")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{rel}: not UTF-8")
            continue
        if text.startswith("#!"):
            problems.append(f"{rel}: starts with #!")
        if name == "SKILL.md":
            m = _FM.match(text)
            if not m:
                problems.append(f"{rel}: no frontmatter")
                continue
            lines = [l for l in m.group(1).splitlines() if l.strip()]
            keys = [l.split(":", 1)[0] for l in lines]
            extra = [k for k in keys if k not in FRONTMATTER_KEYS]
            if extra or any(l[:1].isspace() or ":" not in l for l in lines):
                problems.append(f"{rel}: frontmatter must be plain {list(FRONTMATTER_KEYS)} "
                                f"lines (found {keys})")
    return problems


def main(argv: list[str] | None = None) -> int:
    """`check-plugin.py <plugin folder>`: print every refusal reason, exit 1 if any."""
    import sys

    args = sys.argv[1:] if argv is None else argv
    folder = Path(args[0] if args else "plugin")
    if not (folder / ".claude-plugin" / "plugin.json").is_file():
        print(f"{folder}: no .claude-plugin/plugin.json here")
        return 1
    problems = audit(folder)
    for line in problems:
        print(line)
    print(f"{folder}: {'clean' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
