import pytest

from attack_shark_x68he.layers import GlobalLayerCompositor


def test_priority_and_equal_priority_newer_update_wins() -> None:
    layers = GlobalLayerCompositor()
    layers.set_layer("a", "low", 1, (10, 20, 30))
    layers.set_layer("a", "high", 2, (40, 50, 60))
    assert layers.compose(now=0) == (40, 50, 60)
    layers.set_layer("b", "tie", 2, (70, 80, 90))
    assert layers.compose(now=0) == (70, 80, 90)


def test_alpha_and_add_blends_are_clamped() -> None:
    layers = GlobalLayerCompositor()
    layers.set_layer("a", "base", 1, (100, 0, 200))
    layers.set_layer("b", "alpha", 2, (200, 100, 0), opacity=0.5, blend_mode="alpha")
    layers.set_layer("c", "add", 3, (255, 255, 255), opacity=0.8, blend_mode="add")
    assert layers.compose(now=0) == (255, 254, 255)


def test_expiration_and_fade_out() -> None:
    layers = GlobalLayerCompositor()
    layers.set_layer("a", "fade", 1, (100, 0, 0), expires_at=10, fade_out_seconds=4)
    assert layers.compose(now=8) == (50, 0, 0)
    assert layers.compose(now=10) is None
    assert layers.snapshot(now=10) == []


def test_deletion_and_snapshot() -> None:
    layers = GlobalLayerCompositor()
    layers.set_layer("source", "name", 3, [1, 2, 3])
    assert layers.snapshot(now=0) == [
        {
            "source_id": "source",
            "layer_id": "name",
            "priority": 3,
            "color": (1, 2, 3),
            "opacity": 1.0,
            "blend_mode": "replace",
            "expires_at": None,
            "fade_out_seconds": 0.0,
        }
    ]
    assert layers.remove_layer("source", "name") is True
    assert layers.remove_layer("source", "name") is False
    layers.set_layer("s", "one", 1, (1, 1, 1))
    layers.set_layer("s", "two", 1, (2, 2, 2))
    assert layers.remove_source("s") == 2
    assert layers.compose(now=0) is None
    layers.set_layer("s", "one", 1, (1, 1, 1))
    assert layers.clear() == 1
    assert layers.clear() == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"priority": 1, "color": (1, 2)}, "color"),
        ({"priority": True, "color": (1, 2, 3)}, "priority"),
        ({"priority": 1, "color": (1, 2, 3), "opacity": 2}, "opacity"),
        ({"priority": 1, "color": (1, 2, 3), "blend_mode": "bad"}, "blend_mode"),
        ({"priority": 1, "color": (1, 2, 3), "fade_out_seconds": -1}, "fade_out_seconds"),
    ],
)
def test_validation(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        GlobalLayerCompositor().set_layer("source", "name", **kwargs)
