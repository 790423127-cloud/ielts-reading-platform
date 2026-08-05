from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
OUTPUT = ROOT / "tmp" / "contracts-openapi.json"
HASH_OUTPUT = ROOT / "packages" / "contracts" / "openapi.sha256"

sys.path.insert(0, str(API_ROOT))

from app.main import create_app  # noqa: E402


def main() -> None:
    """Export the API contract without starting services or touching user data."""
    schema = create_app().openapi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    canonical = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    HASH_OUTPUT.write_text(hashlib.sha256(canonical).hexdigest() + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
