"""Repository rules that keep the project self-contained and the core industry neutral.

    python scripts/ci/check_repo.py

1. The core (apps/project_manager) never imports an industry layer (pm_construction, pm_archive...), and a layer never
   imports another layer: they meet only through the core's hooks.
2. No absolute machine paths and no references to sibling repositories in code, compose or scripts.
3. Every variable that docker compose requires (${VAR:?}) has an entry in docker/.env.example (the production
   overlays: in docker/.env.prod.example).
Exit code 1 when a rule is broken.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_PARTS = {"node_modules", ".git", "__pycache__", "spa", "dist"}
TEXT_SUFFIXES = {".py", ".js", ".vue", ".json", ".yml", ".yaml", ".sh", ".ps1", ".html", ".cnf", ".toml", ".txt"}

CORE = "project_manager"
LAYERS = sorted(p.name for p in (ROOT / "apps").iterdir() if p.name != CORE and (p / p.name / "hooks.py").is_file())


def layer_import(names):
    alternatives = "|".join(re.escape(name) for name in names)
    return re.compile(rf"^\s*(from|import)\s+({alternatives})\b|[\"']({alternatives})\.", re.M)

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

    for app in (CORE, *LAYERS):
        others = [layer for layer in LAYERS if layer != app]
        if not others:
            continue
        pattern = layer_import(others)
        who = "the core" if app == CORE else f"the layer {app}"
        for path in files(f"apps/{app}", suffixes={".py", ".js", ".vue", ".json"}):
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                problems.append(f"{path.relative_to(ROOT)}: {who} must not use another layer ({match.group(0).strip()})")

    for path in files("apps", "docker", "scripts"):
        if path.resolve() == Path(__file__).resolve():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if FOREIGN_PATH.search(line):
                problems.append(f"{path.relative_to(ROOT)}:{number}: path outside the repository: {line.strip()[:120]}")

    def declared(name):
        example = (ROOT / "docker" / name).read_text(encoding="utf-8")
        return {line.split("=", 1)[0] for line in example.splitlines() if "=" in line and not line.startswith("#")}

    for path in (ROOT / "docker").glob("docker-compose*.yml"):
        template = ".env.prod.example" if path.name.startswith("docker-compose.prod") else ".env.example"
        names = set(REQUIRED_VAR.findall(path.read_text(encoding="utf-8")))
        if template == ".env.prod.example":  # the base file's variables come along with the overlay
            names |= set(REQUIRED_VAR.findall((ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")))
        for name in sorted(names - declared(template)):
            problems.append(f"docker/{path.name}: ${{{name}}} is required but missing from docker/{template}")

    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
