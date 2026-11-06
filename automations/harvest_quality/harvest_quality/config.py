from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

_JOB_KEYS = (
    "timezone",
    "hours",
    "grace_minutes",
    "proceso",
    "report_url",
    "empty_marker",
    "pdf_name",
)
_N8N_KEYS = (
    "production_url",
    "test_url",
    "file_field",
    "force_field",
    "force_value",
)


def load_yaml(name: str) -> dict:
    path = ROOT / "config" / name
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping")
    return data


def webhook_url(url: str) -> str:
    """The POST target is the n8n webhook. The workflow editor URL is not."""
    text = (url or "").strip()
    if text.startswith("https://") and "/webhook/" in text and "/workflow/" not in text:
        return text
    raise ValueError("n8n production_url must be the webhook, not the workflow editor")


def load_profile(name: str | None) -> tuple[dict, dict]:
    """None is the original report. A name loads config/reports/<name>.yaml."""
    if not name:
        job = load_yaml("job.yaml")
        job.setdefault("pdf_name", "calidad-cosecha.pdf")
        return job, load_yaml("n8n.yaml")
    if not name.replace("-", "").isalnum() or name != name.lower():
        raise ValueError(f"unknown profile {name}")
    path = ROOT / "config" / "reports" / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"unknown profile {name}")
    data = load_yaml(f"reports/{name}.yaml")
    missing = [key for key in (*_JOB_KEYS, *_N8N_KEYS) if key not in data]
    if missing:
        raise ValueError(f"{path} missing {', '.join(missing)}")
    job = {key: data[key] for key in _JOB_KEYS}
    n8n = {key: data[key] for key in _N8N_KEYS}
    return job, n8n
