import json

import pytest

from attack_shark_x68he.errors import UnsafeCommandError
from attack_shark_x68he.flash_guard import check_flash_write, record_flash_write

PATTERN = ((0, 0, 0),) * 126


def test_flash_guard_requires_confirmation_and_deduplicates(tmp_path) -> None:
    path = tmp_path / "guard.json"
    with pytest.raises(UnsafeCommandError, match="confirmation"):
        check_flash_write(PATTERN, confirmed=False, path=path, now=1000)

    decision = check_flash_write(PATTERN, confirmed=True, path=path, now=1000)
    assert decision.unchanged is False
    record_flash_write(decision, path=path, now=1000)
    assert check_flash_write(PATTERN, confirmed=True, path=path, now=1001).unchanged is True


def test_flash_guard_rate_limits_changed_patterns(tmp_path) -> None:
    path = tmp_path / "guard.json"
    path.write_text(json.dumps({"sha256": "different", "written_at": 1000}))

    with pytest.raises(UnsafeCommandError, match="wait 570.0s"):
        check_flash_write(PATTERN, confirmed=True, path=path, now=1030)
    assert check_flash_write(PATTERN, confirmed=True, path=path, now=1600).unchanged is False
