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

import rag_core as rag


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

    collections = [c.strip() for c in args.collection.split(",")]

    if args.show_context:
        chunks = rag.retrieve(collections, question, args.top_k)
        print("=" * 60)
        print("CONTEXTO RECUPERADO:")
        print(rag.format_context(chunks))
        print("=" * 60, "\n")

    for token in rag.ask(collections, question, args.top_k, stream=True):
        print(token, end="", flush=True)
    print()


if __name__ == "__main__":
    main()
