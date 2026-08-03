#!/usr/bin/env python3
"""
Servidor MCP (Model Context Protocol) que expone tu documentación indexada
como una herramienta que un agente (Cline, Claude Code, u otro cliente MCP)
puede invocar por su cuenta durante una tarea de código.

Requiere: pip install "mcp[cli]"

No se corre manualmente: el cliente MCP (ej. Cline) lo lanza como subproceso
via stdio, según la config que le des (ver README).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

import rag_core as rag

mcp = FastMCP("docs-rag")


@mcp.tool()
def list_doc_collections() -> list[str]:
    """Lista las colecciones de documentación disponibles (ej: csharp, go, vue,
    angular, python, flutter, patterns). Usar antes de search_docs si no sabés
    qué colecciones existen."""
    return rag.available_collections()


@mcp.tool()
def search_docs(collections: str, question: str, top_k: int = 5) -> str:
    """Busca en la documentación oficial indexada localmente (C#, Go, Vue,
    Angular, Python, Flutter, patrones de diseño) y devuelve los fragmentos
    más relevantes con su archivo fuente. Usar esto ANTES de escribir código
    o afirmar cómo funciona una API de estas tecnologías, para evitar errores.

    Args:
        collections: nombres de colección separados por coma, ej "go,python".
        question: la consulta o duda técnica.
        top_k: cuántos fragmentos traer por colección (default 5).
    """
    names = [c.strip() for c in collections.split(",") if c.strip()]
    chunks = rag.retrieve(names, question, top_k)
    if not chunks:
        return "Sin resultados relevantes en esas colecciones."
    return rag.format_context(chunks)


if __name__ == "__main__":
    mcp.run(transport="stdio")
