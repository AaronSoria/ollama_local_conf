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

## Integración con VS Code

Hay dos formas de usar esto desde el editor. Ambas asumen que te conectás al
servidor por **VS Code Remote-SSH** (así el editor corre "en" el servidor y
no hay que exponer nada a internet).

### Opción A: Continue.dev (más simple, chat con contexto manual)

Instalá la extensión **Continue** en VS Code. Levantá el servidor HTTP en el
servidor (dejalo corriendo con `tmux` o como servicio, ver más abajo):

```bash
pip install fastapi uvicorn
uvicorn scripts.api_server:app --host 127.0.0.1 --port 8008 --app-dir scripts
```

En `~/.continue/config.json` (se edita desde la propia extensión, "Open
config.json"):

```jsonc
{
  "models": [
    {
      "title": "Qwen Coder (local)",
      "provider": "ollama",
      "model": "qwen2.5-coder",
      "apiBase": "http://localhost:11434"
    }
  ],
  "contextProviders": [
    {
      "name": "http",
      "params": {
        "url": "http://localhost:8008/retrieve",
        "title": "docs",
        "description": "Documentación oficial indexada (C#, Go, Vue, Angular, Python, Flutter, patrones)",
        "displayTitle": "Docs locales"
      }
    }
  ]
}
```

Como VS Code se conecta por Remote-SSH, `localhost:8008` ya es el servidor
(no hace falta port-forwarding manual). En el chat de Continue escribís
`@docs como implemento un composable en vue` y te inyecta el contexto
recuperado antes de preguntarle al modelo.

### Opción B: Cline + MCP (agente que decide solo cuándo consultar la doc)

Esta es la que se parece a Claude Code: un agente que puede editar archivos,
correr comandos, y **decidir por su cuenta** cuándo llamar a una herramienta
— en este caso, tu buscador de documentación.

> **Guía completa y verificada:** ver [`CLINE_SETUP.md`](./CLINE_SETUP.md),
> con la configuración exacta que terminó funcionando (Cline corriendo
> local, no por Remote-SSH, conectado al servidor por Ollama + SSH stdio
> para el MCP) y una tabla de troubleshooting de los problemas reales que
> fuimos encontrando (timeouts, modelo equivocado, hostname sin resolver).

```bash
pip install fastmcp
```

Instalá la extensión **Cline** en VS Code y configurala para usar tu Ollama
(Settings de Cline → API Provider → Ollama → Base URL `http://localhost:11434`
→ modelo `qwen2.5-coder` o el que uses para código).

Después, en la config de MCP servers de Cline (`cline_mcp_settings.json`,
accesible desde el ícono de MCP en la barra lateral de Cline):

```json
{
  "mcpServers": {
    "docs-rag": {
      "command": "/home/allens28/ollama-docs-rag/.venv/bin/python3",
      "args": ["/home/allens28/ollama-docs-rag/scripts/mcp_server.py"]
    }
  }
}
```

(ajustá la ruta del venv y del repo a las tuyas). Cline va a listar dos
herramientas nuevas: `list_doc_collections` y `search_docs`. Cuando le pidas
algo como "escribime un servicio en Angular que consuma esta API", el agente
va a decidir solo si conviene llamar a `search_docs` antes de escribir código,
sin que se lo tengas que pedir explícitamente con `@`.

### Opción C: Claude Code (MCP nativo, a nivel usuario)

Claude Code puede usar este mismo `mcp_server.py` como herramienta nativa,
sin pasar por Bash/SSH manual cada vez. Se registra una sola vez, a nivel
usuario (`--scope user`), y queda disponible automáticamente en **cualquier**
proyecto que abras después — no hay que repetir la configuración por repo:

```bash
claude mcp add docs-rag --scope user -- ssh allens28@192.168.100.37 /home/allens28/ollama_local_conf/.venv/bin/python3 /home/allens28/ollama_local_conf/scripts/mcp_server.py
```

(ajustá usuario/IP/rutas a las tuyas). Verificar con `claude mcp list` que
quedó `✔ Connected`. Vas a tener tres tools disponibles:

- `list_doc_collections` / `search_docs`: iguales a los de Cline.
- `generate_scaffold(template_code, spec)`: delega código repetitivo
  (CRUD, DTOs, mappers) a `chat_model` (local), clonando el estilo de un
  archivo molde real del proyecto en vez de generar desde cero. Pensado
  para que Claude Code se quede con arquitectura y lógica de negocio, y
  derive el boilerplate mecánico al modelo local — gratis en tokens, la
  GPU está ociosa igual.

La decisión de cuándo llamar cada tool la toma el agente solo (igual que en
Cline), guiado por la descripción de cada tool: `generate_scaffold` solo
tiene sentido si ya existe un archivo molde real para copiar el estilo, no
para diseño nuevo.

### Dejar los servidores corriendo de forma estable

El servidor HTTP (Continue) conviene dejarlo como servicio, no en una
terminal suelta:

```ini
# /etc/systemd/system/docs-rag-api.service
[Unit]
Description=ollama-docs-rag API
After=network.target

[Service]
User=allens28
WorkingDirectory=/home/allens28/ollama-docs-rag
ExecStart=/home/allens28/ollama-docs-rag/.venv/bin/uvicorn scripts.api_server:app --host 127.0.0.1 --port 8008 --app-dir scripts
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now docs-rag-api
```

El servidor MCP (Cline) **no** necesita esto — Cline lo lanza y lo mata solo
cada vez que lo necesita, como subproceso.

## Nota de hardware: power limit de la GPU

Si tu GPU tuvo cortes tipo "GPU has fallen off the bus" (Xid 79) bajo la
carga sostenida de inferencia (a diferencia de cargas CUDA en ráfagas
cortas, como cifrado post-cuántico u otros benchmarks breves), puede ser
un tema de picos transitorios de consumo no cubiertos por la fuente/cableado.
`deploy/nvidia-powerlimit.service` cappea el power limit de forma persistente
entre reboots. Instalación:

```bash
sudo systemctl enable --now nvidia-persistenced   # requerido para que el cap no se resetee
sudo cp deploy/nvidia-powerlimit.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nvidia-powerlimit
```

Verificar que quedó aplicado:

```bash
nvidia-smi --query-gpu=power.limit --format=csv
```

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
