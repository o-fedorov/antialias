"""Pytest configuration for the antialias package."""

import json
from dataclasses import asdict
from textwrap import dedent

import pytest
from click.testing import CliRunner, Result

from antialias.__main__ import Config, cli


@pytest.fixture
def config_overrides():
    return {}


@pytest.fixture
def config(config_overrides):
    return Config.from_dict(config_overrides)


@pytest.fixture
def config_path(config, tmpdir):
    path = tmpdir / "config.json"
    config_dict = asdict(config)
    path.write_text(json.dumps(config_dict, indent=4), "utf-8")
    return path


@pytest.fixture
def run_cli(config_path):
    runner = CliRunner()

    def run(*args: tuple, **kwargs: dict) -> Result:
        return runner.invoke(cli, ["--config", config_path, *args], **kwargs)

    return run


def assert_result(
    result: Result, expected_output: str | None = None, expected_exit_code: int = 0
):
    assert result.exit_code == expected_exit_code, result.output
    if expected_output is not None:
        assert dedent(result.output).strip() == dedent(expected_output).strip()
