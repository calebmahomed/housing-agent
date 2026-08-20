import json
from pathlib import Path


def load(path: str, default=list):
    p = Path(path)
    if not p.exists():
        return default()
    return json.loads(p.read_text())


def save(path: str, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True))
