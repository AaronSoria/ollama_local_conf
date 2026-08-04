# Setup del cliente: VS Code + Cline

Esta guía documenta la configuración real que terminó funcionando para usar
Cline (VS Code, corriendo en tu máquina LOCAL, no por Remote-SSH) contra el
Ollama + pipeline RAG que vive en el servidor (`atlasmk2` / `192.168.100.33`).

El código de tus proyectos se queda en tu máquina local. Solo dos cosas
viajan al servidor: la generación del modelo de chat (Ollama) y las
consultas a la documentación indexada (MCP).

## 1. Prerrequisitos en el servidor

- Ollama corriendo y escuchando en la red (no solo `127.0.0.1`), si vas a
  conectarte por IP directa en vez de túnel SSH. Confirmalo con:
  ```bash
  curl http://192.168.100.33:11434/api/tags
  ```
  desde tu máquina local. Si falla, revisá `sudo ufw status` (el puerto 11434
  tiene que estar permitido desde tu IP/red) y que Ollama esté bindeado a
  `0.0.0.0` y no solo `localhost` (`OLLAMA_HOST=0.0.0.0` en el override de
  systemd si hiciera falta).
- SSH con **login por clave, sin contraseña**, desde tu máquina local al
  servidor (lo usa el MCP server, que se lanza de forma no interactiva):
  ```bash
  ssh-copy-id allens28@192.168.100.33
  ssh allens28@192.168.100.33 echo ok   # no debe pedir nada
  ```

## 2. Configuración de Ollama en el servidor (systemd override)

```bash
sudo systemctl edit ollama
```

```ini
[Service]
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
```

- `OLLAMA_KEEP_ALIVE=30m`: mantiene el modelo cargado en VRAM 30 minutos de
  inactividad en vez de los 5 por default. Sin esto, cada mensaje nuevo en
  una sesión de Cline puede pagar el costo de recargar 19GB del modelo a
  GPU antes de generar el primer token.
- `OLLAMA_CONTEXT_LENGTH`: ajustá según cuánta VRAM libre tengas junto con
  el modelo cargado (ver nota de hardware más abajo).

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

## 3. Extensión Cline en VS Code (local, no Remote-SSH)

Instalá **Cline** en tu VS Code normal, abriendo tu proyecto local como
siempre (no conectado por Remote-SSH — Cline corre en tu máquina).

### API Configuration (⚙️ Settings → API Configuration)

| Campo | Valor |
|---|---|
| API Provider | `Ollama` |
| Use custom base URL | ✅ activado |
| Base URL | `http://192.168.100.33:11434` |
| Model | `qwen2.5-coder:32b` (elegilo del dropdown, no lo tipees a mano) |
| Model Context Window | `32768` (o el valor que hayas puesto en `OLLAMA_CONTEXT_LENGTH`) |
| **Request Timeout (ms)** | **`180000`** (180s) — el default de 30s es insuficiente para un modelo de 32B |

**Nota:** después de guardar, cerrá y reabrí el panel de Settings una vez
para confirmar que el modelo quedó fijado — cambiar de provider a veces
resetea el campo de modelo a un default propio de Cline (ej. terminamos
viendo que había quedado en `cline:glm-5.2 (free)` sin querer).

## 4. MCP server (`docs-rag`) vía SSH stdio

Panel de MCP Servers de Cline → **Configure MCP Servers**
(`cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "docs-rag": {
      "disabled": false,
      "timeout": 60,
      "type": "stdio",
      "command": "ssh",
      "args": [
        "allens28@192.168.100.33",
        "/home/allens28/ollama_local_conf/.venv/bin/python3",
        "/home/allens28/ollama_local_conf/scripts/mcp_server.py"
      ]
    }
  }
}
```

SSH reenvía stdin/stdout automáticamente, así que para Cline el proceso
remoto es indistinguible de uno local. No hace falta abrir puertos nuevos
ni tocar `mcp_server.py`.

Cline debería listar dos tools: `list_doc_collections` y `search_docs`.

## 5. Verificar que todo esté conectado

En el servidor, en paralelo mientras usás Cline:

```bash
# ¿Cline está usando de verdad la herramienta de docs?
tail -f ~/ollama_local_conf/mcp_server.log

# ¿las llamadas llegan a Ollama?
sudo journalctl -u ollama -f

# ¿cuántos procesos mcp_server quedaron vivos? (limpiar los viejos si se acumulan)
ps aux | grep mcp_server.py
```

Si `mcp_server.log` **no** muestra ninguna línea de `search_docs` durante un
fallo, el problema no es de docs-rag/MCP — es del modelo de chat o de la
conexión a Ollama en sí (ver troubleshooting abajo).

## Troubleshooting: problemas ya vistos y su causa real

| Síntoma | Causa real | Fix |
|---|---|---|
| `ssh: Could not resolve hostname atlasmk2` | El hostname interno del server no resuelve por DNS desde tu máquina | Usar la IP directa, o agregar un alias en `~/.ssh/config` local |
| El modelo escribe `<tool_call>...</tool_call>` como texto plano en vez de llamar una tool real | Cline había quedado usando su proveedor gratuito propio (`cline:glm-5.2`), no tu Ollama | Confirmar API Provider = Ollama y el modelo correcto en el dropdown |
| `Ollama request timed out after 30 seconds` con `modelId: llama3.2:3b` | Cline quedó con un modelo que no tenés instalado; Ollama intenta bajarlo y no llega en 30s | Seleccionar `qwen2.5-coder:32b` del dropdown (no escribirlo a mano) |
| Mismo timeout pero con `modelId: qwen2.5-coder:32b` y la GPU sí trabajando | El modelo de 32B tarda más de 30s en generar/cargar, y el timeout default de Cline es 30000ms | Subir `Request Timeout (ms)` a `180000`+, y setear `OLLAMA_KEEP_ALIVE` en el servidor |
| `mcp_server.log` vacío durante un fallo de Cline | El fallo no es del MCP server, es de otra tool (Cline nativo) o del modelo | Revisar el panel de Cline para ver qué tool específica falló |

## Nota de hardware (GPU compartida con otras cargas)

Si en algún momento la GPU se usa también para otra cosa (en nuestro caso,
pruebas de cifrado post-cuántico) y da un crash tipo `Xid 79 / GPU has
fallen off the bus` bajo la carga sostenida de inferencia LLM (a diferencia
de cargas CUDA en ráfagas cortas), revisar `deploy/nvidia-powerlimit.service`
en este mismo repo — cappear el power limit resolvió el problema en nuestro
caso.
