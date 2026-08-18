from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM_MCP = ROOT / "upstream" / "playwright" / "tests" / "mcp"
TARGET = ROOT / "tests" / "conformance" / "upstream" / "specs"

FILES = [
    "capabilities.spec.ts",
    "core.spec.ts",
    "click.spec.ts",
]


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for file_name in FILES:
        shutil.copy2(UPSTREAM_MCP / file_name, TARGET / file_name)


if __name__ == "__main__":
    main()
