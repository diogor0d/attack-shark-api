import pytest

from attack_shark_x68he.errors import DeviceBusyError
from attack_shark_x68he.ownership import named_mutex


def test_named_mutex_rejects_a_duplicate_api_instance():
    with (
        named_mutex("AttackSharkX68HE-test-api"),
        pytest.raises(DeviceBusyError),
        named_mutex("AttackSharkX68HE-test-api"),
    ):
        pass
