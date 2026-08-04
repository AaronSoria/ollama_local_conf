#!/usr/bin/env python3
"""
Servidor MCP (Model Context Protocol) que expone tu documentación indexada
como una herramienta que un agente (Cline, Claude Code, u otro cliente MCP)
puede invocar por su cuenta durante una tarea de código.

Requiere: pip install fastmcp

No se corre manualmente: el cliente MCP (ej. Cline) lo lanza como subproceso
via stdio, según la config que le des (ver README).
"""
import logging
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import FastMCP

import rag_core as rag

LOG_PATH = Path(__file__).resolve().parent.parent / "mcp_server.log"
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("docs-rag-mcp")

mcp = FastMCP("docs-rag")


@mcp.tool()
def list_doc_collections() -> list[str]:
    """Lista las colecciones de documentación disponibles (ej: csharp, go, vue,
    angular, python, flutter, patterns). Usar antes de search_docs si no sabés
    qué colecciones existen."""
    log.info("list_doc_collections() llamado")
    try:
        result = rag.available_collections()
        log.info(f"list_doc_collections() -> {result}")
        return result
    except Exception:
        log.error("list_doc_collections() falló:\n" + traceback.format_exc())
        return []


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
    log.info(f"search_docs(collections={collections!r}, question={question!r}, top_k={top_k})")
    try:
        names = [c.strip() for c in collections.split(",") if c.strip()]
        chunks = rag.retrieve(names, question, top_k)
        log.info(f"search_docs -> {len(chunks)} chunks encontrados")
        if not chunks:
            return "Sin resultados relevantes en esas colecciones."
        return rag.format_context(chunks)
    except Exception:
        error_trace = traceback.format_exc()
        log.error("search_docs() falló:\n" + error_trace)
        return (f"ERROR interno buscando en la documentación: {error_trace.splitlines()[-1]}. "
                f"Revisar mcp_server.log en el servidor para el detalle completo.")


if __name__ == "__main__":
    log.info("=== mcp_server arrancando (nueva conexión de un cliente MCP) ===")
    mcp.run()
