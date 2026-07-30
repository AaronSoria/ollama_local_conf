# ollama-docs-rag

Pipeline RAG (Retrieval-Augmented Generation) 100% local y por CLI, para que un
modelo de Ollama genere código y responda consultas basándose en documentación
oficial actualizada (C#, Go, Vue.js, Angular, Python y patrones de diseño), en
vez de alucinar.

No requiere interfaz gráfica: pensado para correr por SSH en un servidor Ubuntu
donde ya tenés Ollama corriendo.

## Cómo funciona

```
config.yaml          → define qué repos de docs traer y cómo
scripts/sync_docs.py  → git clone / git pull de cada fuente (sparse-checkout)
scripts/index.py      → chunking + embeddings (Ollama) + guardado en ChromaDB
scripts/query.py      → recupera contexto relevante y se lo pasa al modelo de chat
scripts/run_update.sh → wrapper para cron (sync + index en un solo paso)
```

Cada fuente de `config.yaml` es una colección independiente en ChromaDB. El
indexado es **incremental**: guarda un hash por archivo y solo re-embebe lo
que cambió desde la última corrida (`docs-sources/.manifest_<nombre>.json`).

## Requisitos previos

- Ollama corriendo en el servidor (`ollama serve`, normalmente ya activo como
  servicio).
- Modelos descargados:
  ```bash
  ollama pull nomic-embed-text      # embeddings
  ollama pull qwen2.5-coder         # modelo de chat/código (o el que prefieras)
  ```
- Python 3.10+ y git.

## Instalación

```bash
git clone <tu-repo> ollama-docs-rag
cd ollama-docs-rag

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Revisá `config.yaml` y ajustá `chat_model` / `embedding_model` si usás otros
nombres de modelo, y `ollama_host` si Ollama corre en otra máquina/puerto.

## Primer uso

```bash
# 1. Descargar toda la documentación (puede tardar unos minutos, sobre todo cpython/go)
python3 scripts/sync_docs.py

# 2. Generar embeddings e indexar en ChromaDB
python3 scripts/index.py
```

## Consultar

```bash
python3 scripts/query.py --collection csharp "como implemento IEnumerable en una clase propia"

python3 scripts/query.py --collection go "diferencia entre channel buffered y unbuffered"

# Combinar varias colecciones en una sola consulta
python3 scripts/query.py --collection python,patterns "como aplico el patron strategy en python"

# Ver qué chunks de documentación se usaron como contexto (útil para debug/confianza)
python3 scripts/query.py --collection vue --show-context "como defino un composable"
```

Colecciones disponibles por defecto: `csharp`, `go`, `vue`, `angular`,
`python`, `flutter`, `patterns`.

## Mantener todo actualizado

Sincronizar solo algunas fuentes:

```bash
python3 scripts/sync_docs.py --only go,vue
python3 scripts/index.py --only go,vue
```

Forzar reindexado completo de una fuente (por ejemplo si cambiaste
`chunk_size` en `config.yaml`):

```bash
python3 scripts/index.py --rebuild go
```

Automatizar con cron (ver `crontab.example`):

```bash
crontab -e
# pegar la línea de crontab.example, ajustando la ruta absoluta
```

## Nota sobre Refactoring Guru

Refactoring Guru no tiene un repositorio oficial abierto — es contenido con
copyright (freemium/de pago). El `config.yaml` viene con una alternativa open
source de patrones de diseño (`design-patterns-for-humans`). Si compraste el
contenido de Refactoring Guru, podés exportarlo/guardarlo manualmente como
`.md` dentro de `docs-sources/patterns/` y `index.py` lo va a tomar igual en
la próxima corrida (no hace falta que venga de un `git clone`).

## Notas de diseño

- El chunking es simple (por párrafos, con solapamiento) para minimizar
  dependencias. Si necesitás algo más sofisticado (chunking consciente de
  estructura Markdown/headers), se puede reemplazar `chunk_text()` en
  `index.py` sin tocar el resto del pipeline.
- `query.py` fuerza al modelo a citar los archivos fuente usados y a admitir
  cuando el contexto no alcanza, en vez de inventar — eso es lo que reduce
  las alucinaciones, más que el modelo en sí.
- Repos grandes (go, angular, cpython) se traen con `sparse-checkout` para no
  descargar código fuente que no necesitás, solo la carpeta de docs.
