"""Carga de configuración desde YAML con valores por defecto."""

from pathlib import Path
from typing import Any, Dict

import yaml

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: Dict[str, Any] = {
    "camera": {
        "device_index": -1,
        "width": 1280,
        "height": 720,
        "fps": 30,
    },
    "display": {
        "screen_index": 1,
        "fullscreen": True,
    },
    "avatar": {
        "size_ratio": 0.70,
        "size": None,
        "smooth_factor": 0.22,
        "look_limit": 1.0,
        "gaze_w_pos": 0.75,
        "gaze_w_vel": 2.4,
        "idle_enabled": True,
        "idle_min_gap": 5.0,
        "idle_max_gap": 12.0,
    },
    "gaze": {
        # Ganancia del desplazamiento del iris -> -1..1, y velocidad de
        # aprendizaje de la postura neutra (mas bajo = se adapta mas lento).
        "gain_x": 9.0,
        "gain_y": 7.0,
        "base_k": 0.03,
        "deadzone": 0.02,
    },
    "gestures": {
        "enabled": True,
        "cooldown_ms": 800,
        "min_hold_frames": 3,
    },
    "audio": {
        "enabled": True,
        "volume": 0.7,
    },
    "debug": {
        "show_landmarks": False,
        "show_fps": False,
        "show_camera_preview": False,
    },
}


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> Dict[str, Any]:
    cfg_path = path or ROOT / "config" / "config.yaml"
    data: Dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8-sig") as fh:
            data = yaml.safe_load(fh) or {}
    return _merge(DEFAULTS, data)


def load_gestures(path: Path | None = None) -> list[Dict[str, Any]]:
    g_path = path or ROOT / "config" / "gestures.yaml"
    if not g_path.exists():
        return []
    with open(g_path, "r", encoding="utf-8-sig") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("gestures", [])
