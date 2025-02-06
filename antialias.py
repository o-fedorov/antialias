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
# requires-python = ">=3.10"
# dependencies = [
#   "click~=8.1",
# ]
# ///
import itertools
import json
import os
import re
import shlex
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

import click

T = TypeVar("T")

SPECIAL_FUNCTIONS = MappingProxyType(
    {
        "--dump-config": ("dump-config", "Dump config to a file."),
        "--list": ("list", "List all available functions."),
    },
)

CWD = Path.cwd().resolve()
HOME_DIR = Path.home()
EVAL_COMMAND = "eval"
BASH_COMPLETION_TEMPLATE = """
_{wrapper_name}_completion() {{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    opts="{names}"

    if [[ ${{COMP_CWORD}} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${{opts}}" -- "${{cur}}") )
    fi
}}

complete -F _{wrapper_name}_completion {wrapper_name}
"""

ZSH_COMPLETION_TEMPLATE = """
#compdef {wrapper_name}

_{wrapper_name}_completion() {{
    local -a subcommands
    subcommands=(
        {subcommands}
    )

    _arguments '1:subcommand:->subcmds' && return 0

    case $state in
        subcmds)
            _describe 'subcommands' subcommands
            ;;
    esac
}}

compdef _{wrapper_name}_completion {wrapper_name}
"""


@dataclass
class Override:
    """Function definition override."""

    name: str = None
    help: str = None
    aliases: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.aliases = set(self.aliases)
        if self.name is not None:
            self.aliases.add(self.name)


_NULL_OVERRIDE = Override()


@dataclass
class Config:
    """Configuration for the application."""

    source_files: list[Path] = field(default_factory=list)
    script_directories: list[Path] = field(default_factory=list)
    underscore_to_dash: bool = False
    keep_original_name: bool = False
    function_regexp: str = (
        r"^\s*(?:function\s+)?(?P<function_name>\w+)\s*(?:\(\))?"
        + r"\s*\{\s*(?:#\s*(?P<comment>.*))?$"
    )
    overrides: dict[Path | None, dict[str, Override]] = field(
        default_factory=lambda: {"*": {}}
    )

    @classmethod
    def from_dict(cls, data: dict, *, files_root: Path = Path()) -> "Config":
        """Create a Config object from a dictionary."""
        data = data.copy()
        source_files = data.pop("source_files", [])
        script_directories = data.pop("script_directories", [])
        overrides = data.pop("overrides", {})

        resolved_source_files = cls._resolve_paths(files_root, source_files)
        resolved_script_directories = cls._resolve_paths(files_root, script_directories)

        initialized_overrides = {}
        for input_path, overrides_data in overrides.items():
            if input_path == "*":
                path = None
            else:
                path = cls._resolve_one_path(files_root, input_path)

            initialized_overrides[path] = {
                name: Override(**override_data)
                for name, override_data in overrides_data.items()
            }

        return cls(
            source_files=resolved_source_files,
            script_directories=resolved_script_directories,
            overrides=initialized_overrides,
            **data,
        )

    @classmethod
    def _resolve_paths(cls, files_root, files):
        resolved_files = []
        for path_str in files:
            path = cls._resolve_one_path(files_root, path_str)
            resolved_files.append(path)
        return resolved_files

    @classmethod
    def _resolve_one_path(cls, files_root, path_str):
        path = Path(path_str).expanduser()
        if not path.is_absolute():
            path = files_root / path
        return path.resolve()


@dataclass
class AbstractFunctionRecord:
    """Base function's metadata implementation."""

    name: str
    original_name: str
    help: str = None
    aliases: set[str] = field(default_factory=set)

    def __post_init__(self):
        if self.help is None:
            self.help = ""

    def format_command(self, args: tuple[str], *, name: str | None = None) -> str:
        """Format the command to be executed."""
        if name is None:
            name = self.original_name
        args_str = shlex.join(args)
        return f"{name} {args_str}"


@dataclass
class SpecialFunctionRecord(AbstractFunctionRecord):
    """Metadata for a special function."""

    def format_command(self, args: tuple[str], **_) -> str:
        """Format the command to execute the actual subcommand."""
        func_name = self.original_name
        original_args = tuple(
            itertools.takewhile(lambda a: a != EVAL_COMMAND, sys.argv)
        )
        actual_name, *actual_args = (*original_args, func_name, *args)

        return super().format_command(actual_args, name=actual_name)


@dataclass
class SourceFunctionRecord(AbstractFunctionRecord):
    """Metadata for a function defined in a source file."""

    path: Path = field(kw_only=True)

    @classmethod
    def build_all(
        cls: type[T],
        original_name: str,
        path: Path,
        config: Config,
        *,
        comment: str | None = None,
    ) -> dict[str, T]:
        """Build the records according to a config."""
        names = cls._get_names(original_name, path, config)
        overridden_help = cls._get_override(original_name, path, config).help

        functions = {}
        for name in names:
            functions[name] = cls(
                name=name,
                original_name=original_name,
                help=overridden_help or comment,
                path=path,
                aliases=names,
            )

        return functions

    @classmethod
    def _get_names(cls, original_name: str, path: Path, config: Config) -> set[str]:
        names = set()
        override = config.overrides.get(path, {}).get(original_name)
        if override is None:
            override = config.overrides.get(None, {}).get(original_name)

        if override is _NULL_OVERRIDE:
            names.update(override.aliases)
        elif config.underscore_to_dash:
            names.add(original_name.replace("_", "-"))
        else:
            names.add(original_name)

        if config.keep_original_name:
            names.add(original_name)

        return names

    @classmethod
    def _get_override(cls, original_name: str, path: Path, config: Config) -> Override:
        override = config.overrides.get(path, {}).get(original_name)
        if override is None:
            override = config.overrides.get(None, {}).get(original_name)
        return override or _NULL_OVERRIDE


@dataclass
class ScriptFunctionRecord(SourceFunctionRecord):
    """Metadata for a function defined in a source file."""

    def format_command(self, args: tuple[str], **_) -> str:
        """Format the command for an executable file in a directory."""
        name = self.path / self.original_name
        return super().format_command(args, name=name)

    @classmethod
    def _get_names(cls, original_name, path, config):
        names = super()._get_names(original_name, path, config)
        for name in names.copy():
            # Drop an extension, if it exists.
            if name != original_name or not config.keep_original_name:
                names.discard(name)
                names.add(Path(name).stem)
        return names


@dataclass
class Registry:
    """Registry of functions."""

    config: Config
    source_functions: dict[str, SourceFunctionRecord] = field(default_factory=dict)
    script_functions: dict[str, ScriptFunctionRecord] = field(default_factory=dict)
    special_functions: dict[str, SpecialFunctionRecord] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize the registry."""
        for path in self.config.source_files:
            functions = self._get_source_functions(path)
            self.source_functions.update(functions)

        for special_name, (name, comment) in SPECIAL_FUNCTIONS.items():
            self.special_functions[special_name] = SpecialFunctionRecord(
                name=special_name,
                original_name=name,
                help=comment,
            )

        for path in self.config.script_directories:
            for subpath in path.iterdir():
                if subpath.is_file() and os.access(subpath, os.X_OK):
                    functions = self._get_script_functions(subpath)
                    self.script_functions.update(functions)

    def _get_source_functions(self, path: Path) -> dict[str, SourceFunctionRecord]:
        functions = {}

        text = path.read_text()
        for match in re.finditer(
            self.config.function_regexp, text, flags=re.MULTILINE | re.IGNORECASE
        ):
            original_name = match.group("function_name")
            comment = match.group("comment")

            functions.update(
                SourceFunctionRecord.build_all(
                    original_name,
                    path,
                    self.config,
                    comment=comment,
                )
            )
        return functions

    def _get_script_functions(self, path: Path) -> dict[str, ScriptFunctionRecord]:
        return ScriptFunctionRecord.build_all(path.name, path.parent, self.config)

    def get(self, name: str) -> AbstractFunctionRecord:
        """Get a function record by name."""
        for registry in (
            self.special_functions,
            self.source_functions,
            self.script_functions,
        ):
            if name in registry:
                return registry[name]
        raise KeyError(name)

    def iter_user_functions(
        self,
    ) -> Iterator[tuple[Path, list[SourceFunctionRecord]]]:
        """Iterate over functions defined by the user."""
        function_records = itertools.chain(
            self.source_functions.values(), self.script_functions.values()
        )
        records = sorted(function_records, key=lambda r: (r.path, r.name))
        for path, group in itertools.groupby(records, key=lambda r: r.path):
            group_list = list(_generate_unique_records(group))
            if group_list:
                yield path, group_list

    def iter_all(self):
        """Iterate over all functions."""
        yield from self.source_functions.values()
        yield from self.script_functions.values()
        yield from self.special_functions.values()

    def __contains__(self, name: str) -> bool:
        """Check if the function record is in the registry."""
        return (
            name in self.source_functions
            or name in self.special_functions
            or name in self.script_functions
        )


def _generate_unique_records(
    records: Iterable[AbstractFunctionRecord],
) -> Iterator[AbstractFunctionRecord]:
    """Get unique function records."""
    seen = set()
    for record in records:
        if record.original_name not in seen:
            yield record
        seen.add(record.original_name)


@click.group()
@click.option(
    "-c",
    "--config",
    default=f"{HOME_DIR}/.antialias.json",
    type=click.Path(dir_okay=False, path_type=Path, resolve_path=True),
    help="Path to config file",
)
@click.option(
    "-r",
    "--files-root",
    default=str(CWD),
    type=click.Path(exists=True, resolve_path=True, path_type=Path),
    help="Root directory for source_files, if a relative paths are used.",
)
@click.pass_context
def cli(ctx: click.Context, config: str, files_root: Path):
    """The main entrypoint for the command."""
    ctx.ensure_object(dict)

    if config.exists():
        config_dict = json.loads(config.read_text())
        config_obj = Config.from_dict(config_dict, files_root=files_root)
    else:
        config_obj = Config()

    ctx.obj["config_path"] = config
    ctx.obj["config"] = config_obj
    ctx.obj["registry"] = Registry(config_obj)


@cli.command(name=EVAL_COMMAND)
@click.argument("function")
@click.argument("args", nargs=-1)
@click.pass_context
def eval_(ctx: click.Context, function: str, args: tuple[str]):
    """Generate scripts for the shell to evaluate."""
    config = ctx.obj["config"]
    registry = ctx.obj["registry"]

    if function not in registry:
        click.echo(f"Error: function {function} not found.", err=True)
        sys.exit(1)

    prepared_files = [
        shlex.quote(str(file)) for file in config.source_files if file.is_file()
    ]
    source_commands = "\n".join([f"source {file}" for file in prepared_files])

    record: AbstractFunctionRecord = registry.get(function)
    command = record.format_command(args)

    click.echo(f"""
    PID=$$
    mkdir -p /tmp/antialias
    (
        {source_commands}

        env > /tmp/antialias/env-before-$PID
        {command}
        env > /tmp/antialias/env-after-$PID
    )
    new_env=$(comm -13 /tmp/antialias/env-before-$PID /tmp/antialias/env-after-$PID)

    while IFS= read -r line; do
        [ -n "$line" ] && export "$line"
    done <<< "$new_env"
    """)


@cli.command(name="list")
@click.pass_context
def list_(ctx: click.Context):
    """Show available commands."""
    config: Config = ctx.obj["config"]
    registry: Registry = ctx.obj["registry"]

    for path, group in registry.iter_user_functions():
        short_path = _shrink_path(path)

        click.echo(f"Path: {short_path}\n")

        for record in group:
            help_string = f": {record.help}" if record.help else ""

            extras = []
            if record.original_name != record.name and not config.keep_original_name:
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

    click.echo("Special functions:")
    for special_name, record in registry.special_functions.items():
        click.echo(f"  {special_name}: {record.help}")


def _shrink_path(path: Path) -> Path:
    """Shrink the path to make it more readable."""
    if path.is_relative_to(HOME_DIR):
        return "~" / path.relative_to(HOME_DIR)
    return path


@cli.command
@click.pass_context
def dump_config(ctx: click.Context):
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


@cli.command
@click.option("--zsh", "shell", flag_value="zsh")
@click.option("--bash", "shell", flag_value="bash")
@click.option(
    "-n", "--name", help="Name of the wrapper that calls the eval comand", default="als"
)
@click.pass_context
def completion(ctx: click.Context, shell: str | None, name: str):
    """Generate autocompletion code."""
    if not shell:
        shell = Path(os.getenv("SHELL", "")).name

    registry = ctx.obj["registry"]

    if shell == "bash":
        names = [record.name for record in registry.iter_all()]
        click.echo(
            BASH_COMPLETION_TEMPLATE.format(names=shlex.join(names), wrapper_name=name)
        )
    elif shell == "zsh":
        subcommands = [
            f"{r.name}: {r.help or r.original_name}" for r in registry.iter_all()
        ]
        click.echo(
            ZSH_COMPLETION_TEMPLATE.format(
                subcommands=shlex.join(subcommands), wrapper_name=name
            )
        )
    else:
        cmd = shlex.join(sys.argv)
        click.echo(f"Error: {cmd}: Unsupported shell: {shell}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli(auto_envvar_prefix="ANTIALIAS")
