from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(name: str) -> dict:
    path = ROOT / "config" / name
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping")
    return data
