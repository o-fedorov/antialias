"""Definition of integration tests fixtures."""

from pathlib import Path

INTEGRATION_TESTS_DIR = Path(__file__).parent
ROOT = INTEGRATION_TESTS_DIR.parent.parent
DATA_DIR = INTEGRATION_TESTS_DIR / "data"
CONFIG_PATH = DATA_DIR / "config" / "config.json"
BASHRC_PATH = DATA_DIR / "config" / "bashrc"
