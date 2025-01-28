#!/usr/bin/env -S uv --quiet run
"""A tool to invoke sh functions from multiple scripts.

MIT License

Copyright (c) 2025 Oleksandr Fedorov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "click~=8.1",
# ]
# ///
import itertools
import json
import re
import shlex
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType

import click

SPECIAL_FUNCTIONS = MappingProxyType(
    {
        "--list": ("list", "List all available functions."),
        "--dump-config": ("dump-config", "Dump config to a file."),
    },
)


@dataclass
class Config:
    """Configuration for the application."""

    source_files: list[Path] = field(default_factory=list)
    underscore_to_dash: bool = False
    keep_original_name: bool = False
    function_regexp: str = (
        r"^\s*(?:function\s+)?(?P<function_name>\w+)\s*(?:\(\))?"
        + r"\s*\{\s*(?:#\s*(?P<comment>.*))?$"
    )

    @classmethod
    def from_dict(cls, data: dict, *, files_root: Path = Path()) -> "Config":
        """Create a Config object from a dictionary."""
        data = data.copy()
        source_files = data.pop("source_files")
        resolved_source_files = []

        for path_str in source_files:
            path = Path(path_str).expanduser()

            if not path.is_absolute():
                path = files_root / path
            resolved_source_files.append(path.resolve())

        return cls(
            source_files=resolved_source_files,
            **data,
        )


@dataclass
class FunctionRecord:
    """Function's metadata."""

    name: str
    original_name: str
    help: str
    file: Path
    aliases: set[str] = field(default_factory=set)
    is_special: bool = False


@click.group()
@click.option(
    "-c",
    "--config",
    default="~/.antialias.json",
    type=click.Path(dir_okay=False, path_type=Path, resolve_path=True),
    help="Path to config file",
)
@click.option(
    "-r",
    "--files-root",
    default=".",
    type=click.Path(exists=True, resolve_path=True, path_type=Path),
    help="Root directory for source_files, if a relative paths are used.",
)
@click.pass_context
def cli(ctx, config, files_root):
    """The main entrypoint for the command."""
    ctx.ensure_object(dict)

    if config.exists():
        config_dict = json.loads(config.read_text())
        config_obj = Config.from_dict(config_dict, files_root=files_root)
    else:
        config_obj = Config()

    ctx.obj["config_path"] = config
    ctx.obj["config"] = config_obj
    ctx.obj["registry"] = _collect_functions(config_obj)


def _collect_functions(config: Config) -> dict[str, FunctionRecord]:
    registry = {}
    for path in config.source_files:
        text = path.read_text()
        for match in re.finditer(
            config.function_regexp, text, flags=re.MULTILINE | re.IGNORECASE
        ):
            original_name = match.group("function_name")
            comment = match.group("comment")

            if config.underscore_to_dash:
                name = original_name.replace("_", "-")
            else:
                name = original_name

            func_record = FunctionRecord(
                name=name,
                original_name=original_name,
                help=comment,
                file=path,
                aliases={name},
            )
            registry[name] = func_record
            if config.keep_original_name:
                registry[original_name] = func_record
                func_record.aliases.add(original_name)

    for special_name, (name, comment) in SPECIAL_FUNCTIONS.items():
        registry[special_name] = FunctionRecord(
            name=special_name,
            original_name=name,
            help=comment,
            file=Path(),
            is_special=True,
        )
    return registry


@cli.command(name="eval")
@click.argument("function")
@click.argument("args", nargs=-1)
@click.pass_context
def eval_(ctx, function, args):
    """Generate scripts for the shell to evaluate."""
    config = ctx.obj["config"]
    registry = ctx.obj["registry"]
    if function not in registry:
        click.echo(f"Error: function {function} not found.", err=True)
        sys.exit(1)

    prepared_files = [shlex.quote(str(file)) for file in config.source_files]
    source_commands = "\n".join([f"source {file}" for file in prepared_files])

    record: FunctionRecord = registry[function]

    if record.is_special:
        func_name, *original_args = itertools.takewhile(
            lambda a: a != ctx.info_name, sys.argv
        )
        args = (*original_args, record.original_name, *args)
    else:
        func_name = record.original_name

    args_str = shlex.join(args)

    click.echo(f"""
    (
        {source_commands}

        {func_name} {args_str}
    )
    """)


@cli.command(name="list")
@click.pass_context
def list_(ctx):
    """Show available commands."""
    config = ctx.obj["config"]
    registry = ctx.obj["registry"]

    records = sorted(registry.values(), key=lambda r: (r.is_special, r.file, r.name))
    for key, group in itertools.groupby(records, key=lambda r: (r.is_special, r.file)):
        is_special, path = key

        group_list = list(group)
        if not group_list:
            continue

        click.echo("Special Functions:" if is_special else f"File: {path}\n")

        seen = set()
        for record in group_list:
            if record.name in seen:
                continue
            seen.add(record.name)

            help_string = f": {record.help}" if record.help else ""

            extras = []
            if (
                not record.is_special
                and record.original_name != record.name
                and not config.keep_original_name
            ):
                extras.append(f"original: {record.original_name}")

            if len(record.aliases) > 1:
                aliases_list_str = ", ".join(record.aliases - {record.name})
                prefix = "alias" if len(record.aliases) == 2 else "aliases"  # noqa: PLR2004 Magic value used
                extras.append(f"{prefix}: {aliases_list_str}")

            if extras:
                extras_base_str = ", ".join(extras)
                extras_str = f" ({extras_base_str})"
            else:
                extras_str = ""

            click.echo(f"  {record.name}{extras_str}{help_string}")

        click.echo("")


@cli.command
@click.pass_context
def dump_config(ctx):
    """Dump config to a file."""
    config_path = ctx.obj["config_path"]
    config = ctx.obj["config"]

    config_dict = asdict(config)

    try:
        original_config = json.loads(config_path.read_text())
    except FileNotFoundError:
        original_config = {}

    config_dict.update(original_config)

    config_path.write_text(json.dumps(config_dict, indent=2, default=_path_to_json))
    click.echo(f"Config file updated: {config_path}")


def _path_to_json(obj):
    if isinstance(obj, Path):
        return str(obj)
    obj_type = type(obj).__name__
    message = f"Object of type {obj_type} is not JSON serializable."
    raise TypeError(message)


if __name__ == "__main__":
    cli(auto_envvar_prefix="ANTIALIAS")
