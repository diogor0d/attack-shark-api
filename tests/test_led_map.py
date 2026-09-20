from attack_shark_x68he.led_map import LED_MAP, MAPPING_VERIFIED, led_by_name


def test_map_has_66_unique_leds_with_driver_derived_slots_and_capture_anchors():
    assert len(LED_MAP) == 66
    assert len({led.name for led in LED_MAP}) == 66
    assert len({led.matrix_slot for led in LED_MAP}) == 66
    anchors = {
        led.name: led.matrix_slot
        for led in LED_MAP
        if led.name in {"escape", "a", "space", "arrow_right"}
    }
    assert anchors == {
        "escape": 1,
        "a": 9,
        "space": 41,
        "arrow_right": 89,
    }
    assert MAPPING_VERIFIED is True
    assert led_by_name("space").row == 4
