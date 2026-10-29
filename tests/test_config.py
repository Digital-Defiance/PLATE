import pytest
from plate.config import Config, load


def test_preset_then_cli_override():
    cfg = load("logo", simplify=2.5)
    assert cfg.max_colors == 8 and cfg.simplify == 2.5


def test_unknown_key_rejected():
    with pytest.raises(KeyError):
        Config().merged(nonsense=1)
