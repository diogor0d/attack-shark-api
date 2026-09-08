from attack_shark_x68he.led_map import LED_MAP, MAPPING_VERIFIED, led_by_name


def test_map_has_66_unique_leds_with_partial_capture_verified_slots():
    assert len(LED_MAP) == 66
    assert len({led.name for led in LED_MAP}) == 66
    assert {led.name: led.matrix_slot for led in LED_MAP if led.matrix_slot is not None} == {
        "escape": 1,
        "a": 9,
        "space": 41,
        "arrow_right": 89,
    }
    assert MAPPING_VERIFIED is False
    assert led_by_name("space").row == 4
