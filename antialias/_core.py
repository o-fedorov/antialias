"""Core functionality for the application."""

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
from typing import Literal, Self, TypeVar

FunctionRecordType = TypeVar("FunctionRecordType", bound="AbstractFunctionRecord")
Asterisk = Literal["*"]

SPECIAL_FUNCTIONS = MappingProxyType(
    {
        "--dump-config": ("dump-config", "Dump config to a file."),
        "--list": ("list", "List all available functions."),
    },
)

EVAL_COMMAND = "eval"


@dataclass
class Override:
    """Function definition override."""

    name: str | None = None
    help: str | None = None
    aliases: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.aliases = set(self.aliases)
        if self.name is not None:
            self.aliases.add(self.name)


_NULL_OVERRIDE = Override()
OverrideSections = dict[str, dict[str, Override]]


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
    overrides: dict[Path | Asterisk | None, OverrideSections] = field(
        default_factory=lambda: {"*": {"functions": {}}}
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
            if input_path in {"*", None}:
                path = None
            else:
                path = cls._resolve_one_path(files_root, input_path)

            function_overrides = overrides_data.pop("functions", {})

            initialized_overrides[path] = {"functions": {}}
            initialized_overrides[path]["functions"] = {
                name: Override(**override_data)
                for name, override_data in function_overrides.items()
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

    def extract[T](
        self, first_key: str | Path, path: list[str | Path | None]
    ) -> T | None:
        """Extract the config using the path.

        Returns:
            The value at the path, or None if it doesn't exist.
        """
        data = getattr(self, str(first_key))
        for key in path:
            if key not in data:
                return None
            data = data[key]
        return data

    def to_dict(self):
        """Convert the config to a dictionary string."""
        config_dict = asdict(self)
        overrides = config_dict.get("overrides", {})
        new_overrides = {}
        for k, v in overrides.items():
            if isinstance(k, Path):
                k = str(k)  # noqa: PLW2901 Loop variable override
            elif k is None:
                k = "*"  # noqa: PLW2901 Loop variable override
            new_overrides[k] = v

        config_dict["overrides"] = new_overrides
        return config_dict

    def to_json(self, indent=2):
        """Convert the config to a json string."""
        data_dict = self.to_dict()
        return json.dumps(data_dict, indent=indent, default=self._json_default)

    @staticmethod
    def _json_default(obj):
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, set):
            return sorted(obj)
        obj_type = type(obj).__name__
        message = f"Object of type {obj_type} is not JSON serializable."
        raise TypeError(message)


@dataclass
class AbstractFunctionRecord:
    """Base function's metadata implementation."""

    name: str
    original_name: str
    help: str | None = None
    aliases: set[str] = field(default_factory=set)

    def __post_init__(self):
        if self.help is None:
            self.help = ""

    def format_command(self, args: tuple[str, ...], *, name: str | None = None) -> str:
        """Format the command to be executed."""
        if name is None:
            name = self.original_name
        args_str = shlex.join(args)
        return f"{name} {args_str}"


@dataclass
class SpecialFunctionRecord(AbstractFunctionRecord):
    """Metadata for a special function."""

    def format_command(self, args: tuple[str, ...], **_) -> str:
        """Format the command to execute the actual subcommand."""
        func_name = self.original_name
        original_args: tuple[str, ...] = tuple(
            itertools.takewhile(lambda a: a != EVAL_COMMAND, sys.argv)
        )
        actual_name, *actual_args = (*original_args, func_name, *args)

        return super().format_command(tuple(actual_args), name=actual_name)


@dataclass
class SourceFunctionRecord(AbstractFunctionRecord):
    """Metadata for a function defined in a source file."""

    path: Path = field(kw_only=True)

    @classmethod
    def build_all(
        cls,
        original_name: str,
        path: Path,
        config: Config,
        *,
        comment: str | None = None,
    ) -> dict[str, Self]:
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
        override = cls._get_override(original_name, path, config)

        if override is not _NULL_OVERRIDE:
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
        override = config.extract("overrides", [path, "functions", original_name])

        if override is None:
            override = config.extract("overrides", [None, "functions", original_name])
        return override or _NULL_OVERRIDE


@dataclass
class ScriptFunctionRecord(SourceFunctionRecord):
    """Metadata for a function defined as an executable file."""

    def format_command(self, args: tuple[str, ...], **_) -> str:
        """Format the command for an executable file in a directory."""
        name = self.path / self.original_name
        return super().format_command(args, name=str(name))

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

        text = path.read_text(encoding="utf-8")
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
        """Get a function record by name.

        Raises:
            KeyError: If the function record is not found.
        """
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
        function_records: Iterable[SourceFunctionRecord] = itertools.chain(
            self.source_functions.values(), self.script_functions.values()
        )
        records: list[SourceFunctionRecord] = sorted(
            function_records, key=lambda r: (r.path, r.name)
        )

        path: Path
        group: Iterable[SourceFunctionRecord]
        for path, group in itertools.groupby(records, key=lambda r: r.path):
            group_list: list[SourceFunctionRecord] = list(
                _generate_unique_records(group)
            )
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


def _generate_unique_records[FunctionRecordType: AbstractFunctionRecord](
    records: Iterable[FunctionRecordType],
) -> Iterator[FunctionRecordType]:
    """Get unique function records."""
    seen: set[str] = set()
    for record in records:
        if record.original_name not in seen:
            yield record
        seen.add(record.original_name)
