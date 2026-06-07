#!/usr/bin/env python
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MOJIBAKE_RE = re.compile(r"(Ã|Â|Ä|Æ|áº|á»|â€|ï»¿)")


def fix_mojibake_text(value: str) -> str:
    if not MOJIBAKE_RE.search(value):
        return value
    for source_encoding in ("latin1", "cp1252"):
        try:
            repaired = value.encode(source_encoding).decode("utf-8")
        except UnicodeError:
            continue
        if repaired != value:
            return repaired.replace("Â·", "-").replace("\ufeff", "")
    return value.replace("Â·", "-").replace("Â", "").replace("\ufeff", "")


def repair_value(value: Any) -> Any:
    if isinstance(value, str):
        return fix_mojibake_text(value)
    if isinstance(value, list):
        return [repair_value(item) for item in value]
    if isinstance(value, dict):
        return {repair_value(key): repair_value(item) for key, item in value.items()}
    return value


def repair_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    data = json.loads(original)
    repaired = json.dumps(repair_value(data), ensure_ascii=False, indent=2)
    if original.rstrip() == repaired.rstrip():
        return False
    path.write_text(f"{repaired}\n", encoding="utf-8")
    return True


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "data"
    changed = 0
    for directory in [root / "runs", root / "jobs"]:
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            if repair_file(path):
                changed += 1
                print(f"repaired {path}")
    print(f"repaired_files={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
