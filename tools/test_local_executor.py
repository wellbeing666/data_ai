import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.sandbox.local_executor import (  # noqa: E402
    WINDOWS_CONTROL_C_EXIT,
    WINDOWS_CONTROL_C_EXIT_SIGNED,
    _is_environment_interruption,
    _subprocess_creation_flags,
)


def test_environment_interruption_detection():
    assert _is_environment_interruption(WINDOWS_CONTROL_C_EXIT, "") is True
    assert _is_environment_interruption(WINDOWS_CONTROL_C_EXIT_SIGNED, "") is True
    assert _is_environment_interruption(1, "Traceback...\nKeyboardInterrupt\n") is True
    assert _is_environment_interruption(1, "ValueError: bad data") is False
    assert _is_environment_interruption(0, "") is False


def test_creation_flags_is_integer():
    assert isinstance(_subprocess_creation_flags(), int)


if __name__ == "__main__":
    test_environment_interruption_detection()
    test_creation_flags_is_integer()
    print("Local executor tests passed.")
