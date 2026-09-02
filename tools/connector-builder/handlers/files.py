"""Generated-file + artifact actions: versions, content read/write, downloads.

The compiled `.nupkg` (download-artifact) is the bridge to PROCESIO: hand it to
`procesio customaction-upload --file <nupkg>` to install the connector for live
testing.
"""
from __future__ import annotations

import argparse

from actiondef import ActionDef
from errors import UsageError
from handlers.common import add_build_id, load_text_or_file


def list_file_versions(client, args) -> dict:
    return client.get(f"/builds/{args.build_id}/files/versions")


def get_file_version(client, args) -> dict:
    return client.get(
        f"/builds/{args.build_id}/files/{args.filename}/versions/{args.version}")


def update_file(client, args) -> dict:
    content = load_text_or_file(args.content, args.content_file, what="content")
    if content is None:
        raise UsageError("provide --content or --content-file")
    return client.put(f"/builds/{args.build_id}/files/{args.filename}",
                      {"content": content})


def set_file_instructions(client, args) -> dict:
    return client.put(
        f"/builds/{args.build_id}/files/{args.filename}/instructions",
        {"instructions": args.instructions})


def download_file(client, args) -> dict:
    return client.download(
        f"/builds/{args.build_id}/files/{args.filename}/download", args.out)


def download_all(client, args) -> dict:
    return client.download(f"/builds/{args.build_id}/files/download-all", args.out)


def download_artifact(client, args) -> dict:
    """Download the compiled .nupkg (or .zip fallback). This is the package you
    upload to PROCESIO via `procesio customaction-upload`."""
    return client.download(f"/builds/{args.build_id}/artifact", args.out)


def _versions_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)


def _get_file_version_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--filename", required=True)
    p.add_argument("--version", required=True, help="Version number")


def _update_file_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--filename", required=True)
    p.add_argument("--content", help="New file content (inline)")
    p.add_argument("--content-file", dest="content_file",
                   help="Read new content from this path")


def _set_file_instructions_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--filename", required=True)
    p.add_argument("--instructions", required=True)


def _download_file_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--filename", required=True)
    p.add_argument("--out", required=True, help="Output file path")


def _download_target_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--out", required=True, help="Output file path")


ACTIONS: dict[str, ActionDef] = {
    "list-file-versions": ActionDef(
        list_file_versions, _versions_args,
        description="Version metadata for every file in a build (no content)."),
    "get-file-version": ActionDef(
        get_file_version, _get_file_version_args,
        description="Full content of one file at a specific version."),
    "update-file": ActionDef(
        update_file, _update_file_args,
        description="Overwrite a file's content (inline or from --content-file)."),
    "set-file-instructions": ActionDef(
        set_file_instructions, _set_file_instructions_args,
        description="Save per-file regeneration instructions."),
    "download-file": ActionDef(
        download_file, _download_file_args,
        description="Download one generated file to --out."),
    "download-all": ActionDef(
        download_all, _download_target_args,
        description="Download all generated files as a zip to --out."),
    "download-artifact": ActionDef(
        download_artifact, _download_target_args,
        description="Download the compiled .nupkg to --out (upload to PROCESIO)."),
}
