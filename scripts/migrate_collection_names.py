#!/usr/bin/env python3
"""
Migración de una sola vez.

Si indexaste alguna fuente ANTES del fix de nombres de colección (cuando
nombres cortos como "go" fallaban por tener menos de 3 caracteres en
ChromaDB), esto renombra las colecciones ya existentes al nuevo esquema
con prefijo 'docs_' — sin recalcular ningún embedding, solo un rename.

Uso:
    python3 scripts/migrate_collection_names.py
"""
import chromadb

import rag_core as rag


def main():
    config = rag.load_config()
    db_dir = rag.resolve_path(config["db_dir"])
    client = chromadb.PersistentClient(path=str(db_dir))

    known_names = {s["name"] for s in config["sources"]}
    existing = client.list_collections()

    if not existing:
        print("No hay colecciones en la base. Nada que migrar.")
        return

    for col in existing:
        if col.name in known_names:
            new_name = rag.chroma_name(col.name)
            print(f"Renombrando '{col.name}' -> '{new_name}' ({col.count()} chunks)...")
            col.modify(name=new_name)
        elif col.name.startswith(rag._CHROMA_PREFIX):
            print(f"'{col.name}' ya está en el esquema nuevo, se deja como está.")
        else:
            print(f"'{col.name}' no coincide con ninguna fuente en config.yaml, se ignora.")

    print("\nMigración completa. Corré 'python3 scripts/index.py' normalmente.")


if __name__ == "__main__":
    main()
