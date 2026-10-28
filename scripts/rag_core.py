"""
Lógica compartida de RAG: carga de config, retrieval en ChromaDB y llamada
al modelo de chat de Ollama. La usan query.py (CLI), api_server.py (HTTP,
para Continue.dev) y mcp_server.py (MCP, para Cline / Claude Code / etc).
"""
import sys
from pathlib import Path

import chromadb
import ollama
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

SYSTEM_PROMPT = """Sos un asistente técnico integrado en un editor de código. Respondé \
ÚNICAMENTE en base al CONTEXTO provisto abajo, extraído de documentación oficial. Si el \
contexto no alcanza para responder con seguridad, decilo explícitamente en vez de \
inventar información. Cuando generes código, basate en los ejemplos y convenciones del \
contexto. Al final de tu respuesta, listá los archivos fuente que usaste (campo "Fuentes")."""

SCAFFOLD_SYSTEM_PROMPT = """Sos un generador de código repetitivo (boilerplate) dentro de un \
pipeline de desarrollo. Te dan un ARCHIVO MOLDE (código real ya existente en el proyecto) y \
un PEDIDO que describe una pieza nueva y análoga a generar.

Reglas estrictas:
- Copiá EXACTAMENTE el estilo del molde: naming, indentación, imports, manejo de errores, \
capas, convenciones de nombres de archivo/clase, comentarios (o ausencia de ellos).
- No inventes arquitectura nueva ni "mejores prácticas" que no estén en el molde. Si el \
molde no usa algo (ej. validación, logging), el resultado tampoco lo usa, salvo que el \
PEDIDO lo pida explícitamente.
- Adaptá únicamente lo que el PEDIDO especifica (nombres de entidad/campos/relaciones), \
dejando todo lo demás estructuralmente idéntico al molde.
- Devolvé ÚNICAMENTE el código resultante, sin explicaciones ni texto envolvente, sin \
```fences``` de markdown."""

_config_cache = None
_client_cache = None

_CHROMA_PREFIX = "docs_"


def chroma_name(friendly_name: str) -> str:
    """Chroma exige nombres de 3-512 chars [a-zA-Z0-9._-]. Nombres cortos como
    'go' (2 chars) no son válidos, así que siempre anteponemos un prefijo fijo."""
    return f"{_CHROMA_PREFIX}{friendly_name}"


def friendly_name(chroma_collection_name: str) -> str:
    return chroma_collection_name.removeprefix(_CHROMA_PREFIX)


def load_config():
    global _config_cache
    if _config_cache is None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f)
    return _config_cache


def resolve_path(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    return p if p.is_absolute() else (ROOT / p).resolve()


def get_client():
    global _client_cache
    if _client_cache is None:
        config = load_config()
        db_dir = resolve_path(config["db_dir"])
        _client_cache = chromadb.PersistentClient(path=str(db_dir))
    return _client_cache


def available_collections() -> list[str]:
    return [friendly_name(c.name) for c in get_client().list_collections()]


def retrieve(collections: list[str], question: str, top_k: int | None = None):
    """Devuelve lista de (fuente, texto_chunk) más relevantes para la pregunta."""
    config = load_config()
    client = get_client()
    top_k = top_k or config["top_k"]

    q_emb = ollama.embeddings(model=config["embedding_model"], prompt=question)["embedding"]

    all_chunks = []
    for name in collections:
        try:
            collection = client.get_collection(name=chroma_name(name))
        except Exception:
            print(f"[WARN] la colección '{name}' no existe. Corré sync_docs.py + index.py.",
                  file=sys.stderr)
            continue
        result = collection.query(query_embeddings=[q_emb], n_results=top_k)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        for doc, meta in zip(docs, metas):
            all_chunks.append((f"{name}/{meta.get('source_file', '?')}", doc))

    return all_chunks


def format_context(chunks: list[tuple[str, str]]) -> str:
    return "\n\n---\n\n".join(f"[Fuente: {src}]\n{doc}" for src, doc in chunks)


def ask(collections: list[str], question: str, top_k: int | None = None, stream: bool = False):
    """Retrieval + generación. Si stream=True devuelve un generador de tokens,
    si no, devuelve el string completo de la respuesta y las fuentes usadas."""
    config = load_config()
    chunks = retrieve(collections, question, top_k)

    if not chunks:
        result = "No se encontró contexto relevante en las colecciones indicadas."
        return (iter([result]) if stream else (result, []))

    context_text = format_context(chunks)
    sources = [src for src, _ in chunks]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"CONTEXTO:\n{context_text}\n\nPREGUNTA:\n{question}"},
    ]

    if stream:
        def gen():
            for part in ollama.chat(model=config["chat_model"], messages=messages, stream=True):
                yield part["message"]["content"]
        return gen()

    response = ollama.chat(model=config["chat_model"], messages=messages, stream=False)
    return response["message"]["content"], sources


def generate_scaffold(template_code: str, spec: str) -> str:
    """Genera código repetitivo nuevo clonando el estilo de `template_code` (un archivo
    real del proyecto) y adaptándolo a lo que pide `spec`. Pensado para boilerplate
    (CRUD, DTOs, mappers), no para lógica de negocio no trivial."""
    config = load_config()
    messages = [
        {"role": "system", "content": SCAFFOLD_SYSTEM_PROMPT},
        {"role": "user", "content": f"ARCHIVO MOLDE:\n{template_code}\n\nPEDIDO:\n{spec}"},
    ]
    response = ollama.chat(model=config["chat_model"], messages=messages, stream=False)
    return response["message"]["content"]
