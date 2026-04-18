"""Regenerate manifest.schema.json from the Pydantic model."""

import json
from pathlib import Path

from artifact_schema.manifest import Manifest


def main() -> None:
    schema = Manifest.model_json_schema()
    out = Path(__file__).parents[1] / "jsonschema" / "manifest.schema.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
