"""Integration tests for the README.md file."""
import re
from subprocess import STDOUT, CalledProcessError, check_output

from tests.integration.fixtures import BASHRC_PATH, DATA_DIR, INTEGRATION_TESTS_DIR
from tests.integration.parser import get_testcases

REPLACEMENTS = (
    (r"^/.*/bash\b", "/bin/bash"),
)

def pytest_generate_tests(metafunc):
    if "doc_testcase" in metafunc.fixturenames:
        metafunc.parametrize("doc_testcase", get_testcases(), ids=lambda x: x.input)


def test_readme(doc_testcase):
    """Test the README.md file."""
    output = _run(doc_testcase.input)
    expected_output = _normalize_output("\n".join(doc_testcase.output))
    assert _normalize_output(output) == expected_output


def _run(cmd: str) -> str:
    """Run the input and return the output."""
    script = f"bash -c 'source {BASHRC_PATH}; {cmd}'"
    try:
        return check_output(  # noqa: S602 `subprocess` call with `shell=True` identified, security issue
            script,
            shell=True,
            text=True,
            stderr=STDOUT,
            cwd=INTEGRATION_TESTS_DIR,
        )
    except CalledProcessError as e:
        return e.output


def _normalize_output(output: str) -> str:
    """Normalize the output."""
    data_dir_str = str(DATA_DIR)
    if not data_dir_str.endswith("/"):
        data_dir_str += "/"
    output = output.strip().replace(data_dir_str, "")

    for pattern, replacement in REPLACEMENTS:
        output = re.sub(pattern, replacement, output)

    return output
