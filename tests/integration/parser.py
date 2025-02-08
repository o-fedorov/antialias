"""Parsing the README.md file to get the test cases."""

from dataclasses import dataclass, field
from pathlib import Path
from pprint import pprint

ROOT = Path(__file__).parent.parent.parent
README = ROOT / "README.md"
TESTCASE_COMMENT = "<!-- testcase -->"
TESTCASE_END_COMMENT = "<!-- endtestcase -->"
CODEBLOCK_FENCE = "```"
SHELL_PROMPT = "$ "


@dataclass
class DocTestCase:
    """A test case in the README.md file."""

    input: str
    output: list[str] = field(default_factory=list)


def get_testcases():
    """Get the test cases from the README.md file."""
    testcases = []
    collect = False
    cur_testcase = None

    for line in README.read_text().splitlines():
        if line == TESTCASE_COMMENT:
            collect = True
            continue
        if line == TESTCASE_END_COMMENT:
            collect = False
            continue

        if not collect:
            continue

        if line.startswith(CODEBLOCK_FENCE):
            if cur_testcase is not None:
                testcases.append(cur_testcase)
                cur_testcase = None
            continue

        if line.startswith(SHELL_PROMPT):
            if cur_testcase is not None:
                testcases.append(cur_testcase)
            test_input = line.removeprefix(SHELL_PROMPT)
            cur_testcase = DocTestCase(input=test_input)
            continue

        assert cur_testcase is not None
        cur_testcase.output.append(line)

    if cur_testcase is not None:
        testcases.append(cur_testcase)
    return testcases


if __name__ == "__main__":
    pprint(get_testcases())  # noqa: T203 Using pprint
