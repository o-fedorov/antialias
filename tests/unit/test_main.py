"""Tests for the main functionality."""

import pytest

from tests.conftest import assert_result


@pytest.mark.parametrize("use_default_config", [False])
def test_smoke(run_cli):
    result = run_cli("list")
    assert_result(
        result,
        """\
        Special functions:
          --dump-config: Dump config to a file.
          --list: List all available functions.
        """,
    )


def test_smoke_default_config(run_cli):
    result = run_cli("list")
    assert_result(
        result,
        """\
        Path: ~/code/antialias/tests/data/scripts/executable

          run-test (original: run_test_script.sh, alias: run-test-script): This is a help message for run_test_script.sh

        Path: ~/code/antialias/tests/data/scripts/test_source1.sh

          f1 (original: f_1): Help message is extracted from comment.

        Path: ~/code/antialias/tests/data/scripts/test_source2.sh

          f-2 (original: f_2)
          f_3: This is a help message for f_3

        Special functions:
          --dump-config: Dump config to a file.
          --list: List all available functions.
        """,  # noqa: E501 Line too long
    )
