"""Integration tests for the READEME.md file."""

from tests.integration.parser import get_testcases


def pytest_generate_tests(metafunc):
    if "doc_testcase" in metafunc.fixturenames:
        metafunc.parametrize("doc_testcase", get_testcases(), ids=lambda x: x.input)


def test_readme(doc_testcase):
    """Test the README.md file."""
