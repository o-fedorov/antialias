"""Pytest configuration for the antialias package."""

import json
from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner, Result

from antialias.__main__ import cli
from antialias._core import Config

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "tests" / "data"
CONFIG_PATH = DATA_DIR / "config" / "config.json"


@pytest.fixture
def use_default_config():
    return True


@pytest.fixture
def config_overrides():
    return {}


@pytest.fixture
def config(config_overrides, use_default_config):
    if use_default_config:
        config_data = json.loads(CONFIG_PATH.read_text())
        config_overrides = config_data | config_overrides
    return Config.from_dict(config_overrides, files_root=DATA_DIR)


@pytest.fixture
def config_path(config, tmpdir):
    path = tmpdir / "config.json"
    path.write_text(config.to_json(), "utf-8")
    return path


@pytest.fixture
def run_cli(config_path):
    runner = CliRunner()

    def run(*args: str) -> Result:
        return runner.invoke(cli, ["--config", str(config_path), *args])

    return run


def assert_result(
    result: Result, expected_output: str | None = None, expected_exit_code: int = 0
):
    assert result.exit_code == expected_exit_code, result.output
    if expected_output is not None:
        assert dedent(result.output).strip() == dedent(expected_output).strip()
