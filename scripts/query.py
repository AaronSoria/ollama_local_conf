#!/usr/bin/env python3
"""
Consulta una o varias colecciones (fuentes) y le pasa el contexto recuperado
al modelo de chat de Ollama, para que responda basado en la documentación real.

Uso:
    python3 query.py --collection csharp "como hago una interfaz generica en C#"
    python3 query.py --collection go,python "diferencia entre goroutines y threads de python"
    echo "que es un singleton" | python3 query.py --collection patterns
"""
import argparse
import sys
from pathlib import Path

import chromadb
import ollama
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

SYSTEM_PROMPT = """Sos un asistente técnico. Respondé ÚNICAMENTE en base al CONTEXTO \
provisto abajo, extraído de documentación oficial. Si el contexto no alcanza para \
responder con seguridad, decilo explícitamente en vez de inventar información. \
Cuando generes código, basate en los ejemplos y convenciones del contexto. \
Al final de tu respuesta, listá los archivos fuente que usaste (campo "Fuentes")."""


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_context(client, collections: list[str], question: str,
                   embedding_model: str, top_k: int):
    q_emb = ollama.embeddings(model=embedding_model, prompt=question)["embedding"]

    all_chunks = []
    for name in collections:
        try:
            collection = client.get_collection(name=name)
        except Exception:
            print(f"[WARN] la colección '{name}' no existe todavía. "
                  f"Corré sync_docs.py + index.py primero.", file=sys.stderr)
            continue
        result = collection.query(query_embeddings=[q_emb], n_results=top_k)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        for doc, meta in zip(docs, metas):
            all_chunks.append((f"{name}/{meta.get('source_file', '?')}", doc))

    return all_chunks


def main():
    parser = argparse.ArgumentParser(description="Consulta RAG sobre la documentación indexada")
    parser.add_argument("question", nargs="?", help="Pregunta (si no se pasa, se lee de stdin)")
    parser.add_argument("--collection", required=True,
                         help="Nombre(s) de colección separados por coma, ej: go,python")
    parser.add_argument("--top-k", type=int, default=None, help="Overrides top_k de config.yaml")
    parser.add_argument("--show-context", action="store_true",
                         help="Imprime los chunks recuperados antes de la respuesta")
    args = parser.parse_args()

    question = args.question or sys.stdin.read().strip()
    if not question:
        print("No se recibió ninguna pregunta.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    db_dir = ROOT / config["db_dir"].lstrip("./")
    client = chromadb.PersistentClient(path=str(db_dir))

    collections = [c.strip() for c in args.collection.split(",")]
    top_k = args.top_k or config["top_k"]

    chunks = build_context(client, collections, question,
                            config["embedding_model"], top_k)

    if not chunks:
        print("No se encontró contexto relevante en las colecciones indicadas.")
        sys.exit(1)

    context_text = "\n\n---\n\n".join(f"[Fuente: {src}]\n{doc}" for src, doc in chunks)

    if args.show_context:
        print("=" * 60)
        print("CONTEXTO RECUPERADO:")
        print(context_text)
        print("=" * 60, "\n")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"CONTEXTO:\n{context_text}\n\nPREGUNTA:\n{question}"},
    ]

    stream = ollama.chat(model=config["chat_model"], messages=messages, stream=True)
    for part in stream:
        print(part["message"]["content"], end="", flush=True)
    print()


if __name__ == "__main__":
    main()
