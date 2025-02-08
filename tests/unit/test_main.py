"""Tests for the main functionality."""

from tests.conftest import assert_result


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
