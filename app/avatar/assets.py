"""Asset loaders.

Behaviour lives in ``app.avatar``; visual data/config lives under
``ui/avatar/assets/``. These helpers load character, expression and window
data from that layout, falling back to built-in defaults when the repository
asset files are absent (so the avatar engine has no hard filesystem
dependency).
"""

import json
import logging
from pathlib import Path
from typing import Any, Mapping

from app.avatar.config import AvatarConfig
from app.avatar.expression import DEFAULT_EXPRESSIONS, AvatarExpression, ExpressionSet
from app.avatar.window import AvatarWindowConfig

logger = logging.getLogger(__name__)

_ASSETS_ROOT = Path(__file__).resolve().parents[2] / "ui" / "avatar" / "assets"

CHARACTER_JSON = _ASSETS_ROOT / "character" / "character.json"
EXPRESSIONS_JSON = _ASSETS_ROOT / "expressions" / "expressions.json"
WINDOW_JSON = _ASSETS_ROOT / "ui" / "window.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        logger.info("Asset file %s not found, falling back to defaults", path)
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:  # json.JSONDecodeError subclasses ValueError
        logger.warning("Failed to load asset file %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("Asset file %s is not a JSON object", path)
        return None
    return data


def load_character_config(path: str | Path | None = None) -> AvatarConfig:
    """Load an ``AvatarConfig`` from JSON, or the code defaults."""
    data = _read_json(Path(path) if path is not None else CHARACTER_JSON)
    if data is None:
        return AvatarConfig()
    return AvatarConfig.model_validate(data)


def load_expression_set(path: str | Path | None = None) -> ExpressionSet:
    """Load a named expression set from JSON, or the defaults."""
    data = _read_json(Path(path) if path is not None else EXPRESSIONS_JSON)
    if data is None:
        return ExpressionSet(DEFAULT_EXPRESSIONS)
    captured: dict[str, AvatarExpression] = {}
    for name, params in data.items():
        captured[str(name)] = AvatarExpression.model_validate(params)
    return ExpressionSet(captured)


def load_window_preferences(path: str | Path | None = None) -> AvatarWindowConfig:
    """Load window preferences from JSON, or the defaults."""
    data = _read_json(Path(path) if path is not None else WINDOW_JSON)
    if data is None:
        return AvatarWindowConfig()
    return AvatarWindowConfig.model_validate(data)


def save_expression_set(expressions: Mapping[str, AvatarExpression], path: str | Path) -> None:
    """Persist an expression set to JSON (used by tooling/tests)."""
    payload = {name: params.model_dump() for name, params in expressions.items()}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
