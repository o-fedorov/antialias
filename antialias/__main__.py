"""The main entrypoint."""

import json
import os
import shlex
import sys
from dataclasses import asdict
from pathlib import Path

import click

from antialias._core import EVAL_COMMAND, AbstractFunctionRecord, Config, Registry

CWD = Path.cwd().resolve()
HOME_DIR = Path.home()
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


@click.group()
@click.option(
    "-c",
    "--config",
    default=f"{HOME_DIR}/.antialias.json",
    envvar="ANTIALIAS_CONFIG",
    type=click.Path(dir_okay=False, path_type=Path, resolve_path=True),
    help="Path to config file",
)
@click.option(
    "-r",
    "--files-root",
    default=str(CWD),
    envvar="ANTIALIAS_FILES_ROOT",
    type=click.Path(exists=True, resolve_path=True, path_type=Path),
    help="Root directory for source_files, if a relative paths are used.",
)
@click.pass_context
def cli(ctx: click.Context, config: Path, files_root: Path):
    """The main entrypoint for the command."""
    ctx.ensure_object(dict)

    if config.exists():
        config_dict = json.loads(config.read_text(encoding="utf-8"))
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

        env | sort > /tmp/antialias/env-before-$PID
        {command}
        env | sort > /tmp/antialias/env-after-$PID
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

    config_path.write_text(config.to_json())
    click.echo(f"Config file updated: {config_path}")


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
