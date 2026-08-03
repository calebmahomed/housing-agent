import json
from pathlib import Path


def load(path: str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text())


def save(path: str, data: list) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True))
