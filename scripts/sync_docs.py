#!/usr/bin/env python3
"""
Descarga o actualiza (git pull) cada fuente de documentación definida en config.yaml.

Usa git sparse-checkout para traer solo la subcarpeta de docs cuando el repo
es muy grande (go, angular, cpython), en vez de clonar el repo completo.

Uso:
    python3 sync_docs.py                # sincroniza todas las fuentes
    python3 sync_docs.py --only go,vue  # sincroniza solo algunas
"""
import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(cmd, cwd=None):
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr.strip()}", file=sys.stderr)
    return result


def sync_source(source, docs_dir: Path):
    name = source["name"]
    repo = source["repo"]
    branch = source.get("branch", "main")
    sparse_path = source.get("sparse_path", "")
    target = docs_dir / name

    print(f"\n=== {name} ===")

    if target.exists():
        print(f"[{name}] repo ya existe, actualizando (git pull)...")
        res = run(["git", "pull", "--ff-only"], cwd=target)
        if res.returncode != 0:
            print(f"[{name}] pull falló, probablemente hay cambios locales. "
                  f"Revisá manualmente {target}", file=sys.stderr)
        else:
            print(f"[{name}] actualizado OK.")
        return

    print(f"[{name}] clonando por primera vez...")
    target.parent.mkdir(parents=True, exist_ok=True)

    if sparse_path:
        # Clone sin checkout completo, filtrando blobs, y activamos sparse-checkout
        # cone-mode para traer solo la carpeta que nos interesa.
        run(["git", "clone", "--filter=blob:none", "--no-checkout",
             "--depth", "1", "--branch", branch, repo, str(target)])
        run(["git", "sparse-checkout", "init", "--cone"], cwd=target)
        run(["git", "sparse-checkout", "set", sparse_path], cwd=target)
        run(["git", "checkout", branch], cwd=target)
    else:
        run(["git", "clone", "--depth", "1", "--branch", branch, repo, str(target)])

    print(f"[{name}] listo.")


def main():
    parser = argparse.ArgumentParser(description="Sincroniza fuentes de documentación")
    parser.add_argument("--only", help="Lista de nombres separados por coma, ej: go,vue")
    args = parser.parse_args()

    config = load_config()
    docs_dir = ROOT / config["docs_dir"].lstrip("./")
    docs_dir.mkdir(parents=True, exist_ok=True)

    sources = config["sources"]
    if args.only:
        wanted = set(n.strip() for n in args.only.split(","))
        sources = [s for s in sources if s["name"] in wanted]
        if not sources:
            print(f"No hay fuentes que coincidan con: {args.only}", file=sys.stderr)
            sys.exit(1)

    for source in sources:
        sync_source(source, docs_dir)

    print("\nSincronización completa. Ahora corré index.py para (re)generar los embeddings.")


if __name__ == "__main__":
    main()
