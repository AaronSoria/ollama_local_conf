#!/usr/bin/env python3
"""
Expone el pipeline RAG como API HTTP, pensado para integrarse con Continue.dev
(context provider tipo "http") u otras herramientas que puedan pegarle a un
endpoint REST.

Correr:
    uvicorn api_server:app --host 0.0.0.0 --port 8008

Endpoints:
    POST /retrieve  {"collections": ["go","python"], "question": "...", "top_k": 5}
        -> {"chunks": [{"source": "...", "text": "..."}]}

    POST /ask       {"collections": ["go"], "question": "..."}
        -> {"answer": "...", "sources": ["go/doc/faq.html", ...]}

    GET  /collections
        -> {"collections": ["csharp","go","vue",...]}
"""
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

import rag_core as rag

app = FastAPI(title="ollama-docs-rag API")


class RetrieveRequest(BaseModel):
    collections: List[str]
    question: str
    top_k: Optional[int] = None


class AskRequest(BaseModel):
    collections: List[str]
    question: str
    top_k: Optional[int] = None


@app.get("/collections")
def list_collections():
    return {"collections": rag.available_collections()}


@app.post("/retrieve")
def retrieve(req: RetrieveRequest):
    chunks = rag.retrieve(req.collections, req.question, req.top_k)
    return {"chunks": [{"source": src, "text": text} for src, text in chunks]}


@app.post("/ask")
def ask(req: AskRequest):
    answer, sources = rag.ask(req.collections, req.question, req.top_k, stream=False)
    return {"answer": answer, "sources": sources}


@app.get("/health")
def health():
    return {"status": "ok"}
