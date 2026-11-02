"""Repository rules that keep the project self-contained and the core industry neutral.

    python scripts/ci/check_repo.py

1. The core (apps/project_manager) never imports an industry layer (pm_construction).
2. No absolute machine paths and no references to sibling repositories in code, compose or scripts.
3. Every variable that docker compose requires (${VAR:?}) has an entry in docker/.env.example.
Exit code 1 when a rule is broken.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_PARTS = {"node_modules", ".git", "__pycache__", "spa", "dist"}
TEXT_SUFFIXES = {".py", ".js", ".vue", ".json", ".yml", ".yaml", ".sh", ".ps1", ".html", ".cnf", ".toml", ".txt"}

LAYER_IMPORT = re.compile(r"^\s*(from|import)\s+pm_construction\b|[\"']pm_construction\.", re.M)
FOREIGN_PATH = re.compile(
    r"[A-Za-z]:[\\/]+(Users|Documents)\b|/home/(?!frappe\b)[a-z]|document-manager-project|frappe_docker\b"
)
REQUIRED_VAR = re.compile(r"\$\{([A-Z0-9_]+):\?")


def files(*folders, suffixes=TEXT_SUFFIXES):
    for folder in folders:
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix in suffixes and not SKIP_PARTS & set(path.parts):
                yield path


def main() -> int:
    problems = []

    for path in files("apps/project_manager", suffixes={".py", ".js", ".vue", ".json"}):
        for match in LAYER_IMPORT.finditer(path.read_text(encoding="utf-8")):
            problems.append(f"{path.relative_to(ROOT)}: the core must not use the industry layer ({match.group(0).strip()})")

    for path in files("apps", "docker", "scripts"):
        if path.resolve() == Path(__file__).resolve():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if FOREIGN_PATH.search(line):
                problems.append(f"{path.relative_to(ROOT)}:{number}: path outside the repository: {line.strip()[:120]}")

    example = (ROOT / "docker" / ".env.example").read_text(encoding="utf-8")
    declared = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line and not line.startswith("#")}
    for path in (ROOT / "docker").glob("docker-compose*.yml"):
        for name in sorted(set(REQUIRED_VAR.findall(path.read_text(encoding="utf-8"))) - declared):
            problems.append(f"docker/{path.name}: ${{{name}}} is required but missing from docker/.env.example")

    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
