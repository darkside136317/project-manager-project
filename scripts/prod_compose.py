"""Run docker compose on the production stack: docker/.env.prod, checked, with the production overlays.

    python3 scripts/prod_compose.py ps
    python3 scripts/prod_compose.py logs -f backend
    python3 scripts/prod_compose.py exec backend bench --site <site> migrate

Copied from document_manager (scripts/prod_compose.py, see docs/NGUON_GOC.md) and adapted: MinIO is part of the base
stack here; DATA_ROOT adds the host-folder overlay.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_prod_env import read_env, validate  # noqa: E402


def command(arguments: list[str]) -> tuple[list[str], dict, Path] | None:
    docker_dir = Path(__file__).resolve().parents[1] / "docker"
    env_path = docker_dir / ".env.prod"
    problems = validate(env_path)
    if problems:
        for problem in problems:
            print(f"Invalid production environment: {problem}", file=sys.stderr)
        return None
    values = read_env(env_path)
    files = ["-f", "docker-compose.yml", "-f", "docker-compose.prod.yml"]
    if values.get("DATA_ROOT"):
        files += ["-f", "docker-compose.prod.bind.yml"]
    environment = os.environ.copy()
    environment.update(values)  # the file's values win over the shell's
    environment.pop("COMPOSE_FILE", None)
    return ["docker", "compose", "--env-file", str(env_path), *files, *arguments], environment, docker_dir


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/prod_compose.py <docker compose arguments>", file=sys.stderr)
        return 2
    built = command(sys.argv[1:])
    if not built:
        return 2
    args, environment, docker_dir = built
    return subprocess.run(args, cwd=docker_dir, env=environment, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
