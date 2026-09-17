"""Asset loaders: repository layout, explicit files and fallbacks."""

import json

from app.avatar.assets import (
    CHARACTER_JSON,
    EXPRESSIONS_JSON,
    WINDOW_JSON,
    load_character_config,
    load_expression_set,
    load_window_preferences,
    save_expression_set,
)
from app.avatar.config import AvatarConfig, AvatarProportions
from app.avatar.expression import DEFAULT_EXPRESSIONS
from app.avatar.window import AvatarWindowConfig


def test_repository_asset_files_exist():
    assert CHARACTER_JSON.is_file()
    assert EXPRESSIONS_JSON.is_file()
    assert WINDOW_JSON.is_file()


def test_repository_character_asset_matches_defaults():
    config = load_character_config()
    # Base appearance fields should match defaults
    default = AvatarConfig()
    assert config.body_width == default.body_width
    assert config.body_height == default.body_height
    assert config.body_color == default.body_color
    assert config.outline_color == default.outline_color
    assert config.outline_width == default.outline_width
    assert config.eye_size == default.eye_size
    assert config.eye_spacing == default.eye_spacing
    assert config.eye_color == default.eye_color
    assert config.pupil_size == default.pupil_size
    assert config.pupil_color == default.pupil_color
    assert config.eye_y_offset == default.eye_y_offset
    assert config.mouth_size == default.mouth_size
    assert config.mouth_color == default.mouth_color
    assert config.mouth_y_offset == default.mouth_y_offset
    assert config.arm_length == default.arm_length
    assert config.arm_thickness == default.arm_thickness
    assert config.arm_color == default.arm_color
    assert config.hand_size == default.hand_size
    assert config.leg_length == default.leg_length
    assert config.leg_thickness == default.leg_thickness
    assert config.leg_color == default.leg_color
    assert config.shoe_width == default.shoe_width
    assert config.shoe_height == default.shoe_height
    assert config.shoe_color == default.shoe_color
    assert config.hour_hand_length == default.hour_hand_length
    assert config.minute_hand_length == default.minute_hand_length
    assert config.hand_thickness == default.hand_thickness
    assert config.hand_color == default.hand_color
    assert config.markings_count == default.markings_count
    assert config.markings_length == default.markings_length
    assert config.markings_thickness == default.markings_thickness
    assert config.markings_color == default.markings_color
    assert config.center_pivot_size == default.center_pivot_size
    assert config.center_pivot_color == default.center_pivot_color
    assert config.default_scale == default.default_scale
    # New sprite sheet fields should be configured
    assert config.sprite_sheet is not None
    assert config.sprite_sheet.image_path == "avatar.png"
    assert config.sprite_sheet.frame_width == 50
    assert config.sprite_sheet.frame_height == 303
    assert config.sprite_sheet.columns == 6
    assert config.sprite_sheet.rows == 1
    assert config.sprite_sheet.fps == 8
    assert "idle" in config.sprite_sheet.animations
    assert "talk" in config.sprite_sheet.animations
    assert "walk" in config.sprite_sheet.animations
    assert config.expression_overlays is not None
    assert "neutral" in config.expression_overlays.expressions
    assert "happy" in config.expression_overlays.expressions
    assert "thinking" in config.expression_overlays.expressions


def test_repository_expression_asset_matches_defaults():
    loaded = load_expression_set()
    for name, params in DEFAULT_EXPRESSIONS.items():
        assert loaded.get(name) == params


def test_repository_window_asset_matches_defaults():
    assert load_window_preferences() == AvatarWindowConfig()


def test_custom_character_file(tmp_path):
    payload = {
        "body_width": 250.0,
        "body_height": 200.0,
        "body_color": "#00FF00",
        "outline_color": "#000000",
        "outline_width": 8.0,
        "eye_size": 30.0,
        "eye_spacing": 60.0,
        "eye_color": "#FFFFFF",
        "pupil_size": 12.0,
        "pupil_color": "#000000",
        "eye_y_offset": -10.0,
        "mouth_size": 18.0,
        "mouth_color": "#000000",
        "mouth_y_offset": 30.0,
        "arm_length": 50.0,
        "arm_thickness": 9.0,
        "arm_color": "#00FF00",
        "hand_size": 14.0,
        "leg_length": 40.0,
        "leg_thickness": 11.0,
        "leg_color": "#00FF00",
        "shoe_width": 28.0,
        "shoe_height": 13.0,
        "shoe_color": "#00AAAA",
        "hour_hand_length": 44.0,
        "minute_hand_length": 60.0,
        "hand_thickness": 7.0,
        "hand_color": "#000000",
        "markings_count": 4,
        "markings_length": 10.0,
        "markings_thickness": 4.0,
        "markings_color": "#000000",
        "center_pivot_size": 8.0,
        "center_pivot_color": "#000000",
        "default_scale": 1.2,
    }
    path = tmp_path / "character.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    config = load_character_config(path)
    assert config.body_width == 250.0
    assert config.markings_count == 4
    assert config.default_scale == 1.2
    assert AvatarProportions.from_config(config).body_dominance > 0


def test_missing_asset_falls_back_to_defaults(tmp_path):
    assert load_character_config(tmp_path / "missing.json") == AvatarConfig()
    assert load_window_preferences(tmp_path / "missing.json") == AvatarWindowConfig()


def test_invalid_asset_falls_back_to_defaults(tmp_path):
    broken = tmp_path / "character.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_character_config(broken) == AvatarConfig()


def test_custom_expression_file(tmp_path):
    payload = {
        "calm": {
            "eye_openness": 0.8,
            "pupil_x": 0.0,
            "pupil_y": 0.0,
            "eyebrow_lift": 0.0,
            "mouth_shape": "smile",
            "mouth_openness": 0.2,
            "face_tilt_deg": 0.0,
            "body_tilt_deg": 0.0,
        }
    }
    path = tmp_path / "expressions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    eset = load_expression_set(path)
    assert eset.names() == ("calm",)
    assert eset.get("calm").mouth_shape.value == "smile"


def test_save_expression_set_roundtrip(tmp_path):
    target = tmp_path / "out.json"
    save_expression_set(DEFAULT_EXPRESSIONS, target)
    assert target.is_file()
    reloaded = load_expression_set(target)
    for name, params in DEFAULT_EXPRESSIONS.items():
        assert reloaded.get(name) == params


def test_custom_window_file(tmp_path):
    path = tmp_path / "window.json"
    path.write_text(
        json.dumps({"width": 640, "height": 480, "always_on_top": False, "character_first": False}),
        encoding="utf-8",
    )
    config = load_window_preferences(path)
    assert config.width == 640
    assert config.always_on_top is False
    assert config.character_first is False
