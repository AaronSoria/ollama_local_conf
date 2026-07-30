#!/usr/bin/env python3
"""
Recorre docs-sources/, detecta archivos nuevos/modificados/borrados (por hash),
los divide en chunks, genera embeddings con un modelo de Ollama y los guarda
en ChromaDB (una colección por fuente/tecnología).

Es incremental: si un archivo no cambió desde la última corrida, no se re-embebe.

Uso:
    python3 index.py                # indexa todas las fuentes
    python3 index.py --only go,vue  # indexa solo algunas
    python3 index.py --rebuild go   # fuerza reindexado completo de una fuente
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import chromadb
import ollama
import yaml
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(manifest_path: Path) -> dict:
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest_path: Path, manifest: dict):
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Chunking simple por párrafos, acumulando hasta chunk_size caracteres,
    con solapamiento de `overlap` caracteres entre chunks consecutivos."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            # arranca el siguiente chunk con el "tail" del anterior como overlap
            tail = current[-overlap:] if len(current) > overlap else current
            current = f"{tail}\n\n{para}" if tail else para
            # si un solo párrafo ya supera chunk_size, lo cortamos a la fuerza
            while len(current) > chunk_size * 1.5:
                chunks.append(current[:chunk_size])
                current = current[chunk_size - overlap:]

    if current:
        chunks.append(current)

    return chunks


def collect_files(source_dir: Path, sparse_path: str, extensions: list[str]) -> list[Path]:
    base = source_dir / sparse_path if sparse_path else source_dir
    if not base.exists():
        return []
    files = []
    for ext in extensions:
        files.extend(base.rglob(f"*{ext}"))
    # ignorar la carpeta .git
    return [f for f in files if ".git" not in f.parts]


def index_source(source, docs_dir: Path, db_dir: Path, client, embedding_model: str,
                  chunk_size: int, overlap: int, force_rebuild: bool):
    name = source["name"]
    source_dir = docs_dir / name
    manifest_path = docs_dir / f".manifest_{name}.json"

    print(f"\n=== Indexando: {name} ===")

    if not source_dir.exists():
        print(f"[{name}] no existe {source_dir}, corré sync_docs.py primero. Saltando.")
        return

    collection = client.get_or_create_collection(name=name)
    manifest = {} if force_rebuild else load_manifest(manifest_path)

    if force_rebuild:
        print(f"[{name}] --rebuild: borrando colección existente...")
        client.delete_collection(name=name)
        collection = client.get_or_create_collection(name=name)

    files = collect_files(source_dir, source.get("sparse_path", ""), source["extensions"])
    current_relpaths = set()

    new_or_changed = []
    for f in files:
        relpath = str(f.relative_to(source_dir))
        current_relpaths.add(relpath)
        h = file_hash(f)
        if manifest.get(relpath) != h:
            new_or_changed.append((f, relpath, h))

    deleted = [rp for rp in manifest.keys() if rp not in current_relpaths]

    print(f"[{name}] {len(files)} archivos encontrados, "
          f"{len(new_or_changed)} nuevos/modificados, {len(deleted)} borrados.")

    # Borrar embeddings de archivos eliminados o modificados (se re-crean después)
    to_purge = deleted + [rp for _, rp, _ in new_or_changed]
    for relpath in to_purge:
        collection.delete(where={"source_file": relpath})
        manifest.pop(relpath, None)

    # Procesar archivos nuevos/modificados
    for f, relpath, h in tqdm(new_or_changed, desc=f"Embebiendo {name}"):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"  [WARN] no se pudo leer {f}: {e}")
            continue

        chunks = chunk_text(text, chunk_size, overlap)
        if not chunks:
            manifest[relpath] = h
            continue

        ids, embeddings, documents, metadatas = [], [], [], []
        for i, chunk in enumerate(chunks):
            try:
                resp = ollama.embeddings(model=embedding_model, prompt=chunk)
            except Exception as e:
                print(f"  [ERROR] embedding falló en {relpath} chunk {i}: {e}")
                continue
            ids.append(f"{relpath}::chunk{i}")
            embeddings.append(resp["embedding"])
            documents.append(chunk)
            metadatas.append({"source_file": relpath, "chunk_index": i})

        if ids:
            collection.upsert(ids=ids, embeddings=embeddings,
                               documents=documents, metadatas=metadatas)

        manifest[relpath] = h

    save_manifest(manifest_path, manifest)
    print(f"[{name}] listo. Colección tiene {collection.count()} chunks.")


def main():
    parser = argparse.ArgumentParser(description="Indexa la documentación en ChromaDB")
    parser.add_argument("--only", help="Lista de nombres separados por coma, ej: go,vue")
    parser.add_argument("--rebuild", help="Nombre de una fuente para forzar reindexado total")
    args = parser.parse_args()

    config = load_config()
    docs_dir = ROOT / config["docs_dir"].lstrip("./")
    db_dir = ROOT / config["db_dir"].lstrip("./")
    db_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(db_dir))

    sources = config["sources"]
    if args.only:
        wanted = set(n.strip() for n in args.only.split(","))
        sources = [s for s in sources if s["name"] in wanted]

    for source in sources:
        force = args.rebuild == source["name"]
        index_source(
            source, docs_dir, db_dir, client,
            embedding_model=config["embedding_model"],
            chunk_size=config["chunk_size"],
            overlap=config["chunk_overlap"],
            force_rebuild=force,
        )

    print("\nIndexado completo.")


if __name__ == "__main__":
    main()
