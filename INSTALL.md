# Installation Guide

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher (required for the dashboard only)
- pip

Check your versions:
```bash
python --version
node --version
```

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/brendanlucas01/Agent-Mind-Bridge.git
cd Agent-Mind-Bridge
```

---

## Step 2 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `mcp[cli]` — FastMCP framework
- `pydantic` — input validation
- `fastapi` — REST API for the dashboard
- `uvicorn` — ASGI server
- `python-dotenv` — `.env` file support

---

## Step 3 — Configure (Optional)

Copy the example config:
```bash
cp .env.example .env
```

The defaults work out of the box. Edit `.env` only if you need to change ports or the database path.

---

## Step 4 — Start the Server

### Option A — Full stack (MCP + REST API + Dashboard)

```bash
./start.sh
```

`start.sh` will automatically run `npm install` in the `dashboard/` folder on first launch if `node_modules` is missing.

Three services will start:
- **MCP Server** — `http://127.0.0.1:3333/mcp`
- **REST API** — `http://127.0.0.1:8000`
- **Dashboard** — `http://localhost:3000`

Press `Ctrl+C` to stop all three cleanly.

### Option B — MCP server only

```bash
python server.py
```

You should see:
```
INFO:     Started server process
INFO:     Uvicorn running on http://127.0.0.1:3333
```

The MCP endpoint is at: `http://127.0.0.1:3333/mcp`

The database file (`shared_context.db`) is created automatically on first run.

---

## Step 5 — Connect Your IDE

### Claude Code

Run in your terminal:
```bash
claude mcp add --transport http shared-context http://127.0.0.1:3333/mcp
```

Restart Claude Code. Run `/mcp` to verify the server appears with 59 tools.

---

### Cursor

**Config file location:** `~/.cursor/mcp.json`

Create the file if it doesn't exist, then add:
```json
{
  "mcpServers": {
    "shared-context": {
      "url": "http://127.0.0.1:3333/mcp"
    }
  }
}
```

Restart Cursor. The tools will appear automatically in any new conversation.

---

### Windsurf / Antigravity

**Config file location:** `~/.codeium/windsurf/mcp_config.json`

> Windsurf and Antigravity share the same MCP config format. `serverUrl` is the correct key — do not use `url` or `type`, they will be silently ignored.

```json
{
  "mcpServers": {
    "shared-context": {
      "serverUrl": "http://127.0.0.1:3333/mcp"
    }
  }
}
```

Reload the MCP configuration from the Windsurf/Antigravity settings panel, or restart the IDE.

---

### Cline / ROO / Kilo Code

**Config file location:** Open the extension in VS Code → click the MCP servers icon → "Edit MCP Settings". This opens `cline_mcp_settings.json` (or equivalent for ROO/Kilo).

```json
{
  "mcpServers": {
    "shared-context": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:3333/mcp",
      "disabled": false,
      "timeout": 60
    }
  }
}
```

Save the file. The extension will connect automatically — no restart required.

---

## Step 6 — Open the Dashboard (Optional)

If you started with `./start.sh`, the dashboard is already running at `http://localhost:3000`.

If you want to start the dashboard separately:

```bash
# Terminal 1 — MCP server
python server.py

# Terminal 2 — REST API
uvicorn api:app --host 127.0.0.1 --port 8000 --reload

# Terminal 3 — Dashboard
cd dashboard
npm install   # first time only
npm run dev
```

Then open `http://localhost:3000` in your browser.

---

## Verifying the Installation

### MCP Inspector
1. Install: `npx @modelcontextprotocol/inspector`
2. Open the inspector in your browser
3. Set transport to **Streamable HTTP**
4. URL: `http://127.0.0.1:3333/mcp`
5. Click Connect — you should see 59 tools listed

### Quick Smoke Test (Claude Code)
After connecting, ask Claude:
```
Call context_help to show all available tools
```
You should get a structured index of all 59 tools organized by pillar.

### REST API Health Check
```bash
curl http://127.0.0.1:8000/api/health
```
Expected response: `{"status":"ok","db":"connected","timestamp":"..."}`

---

## Keeping the Server Running

For persistent use, run the server as a background process.

**Windows (PowerShell):**
```powershell
Start-Process python -ArgumentList "server.py" -WindowStyle Hidden
```

**macOS/Linux:**
```bash
nohup python server.py > server.log 2>&1 &
```

Or use a process manager like `pm2` or `supervisor` for production use.

---

## Troubleshooting

**`Session not found` error**
The server was restarted but your IDE still holds an old session ID. Restart your IDE/Claude session.

**`tools: []` in MCP Inspector**
Import order issue — make sure you're running `python server.py`, not importing the module directly.

**Port already in use**
Change `PORT` in `.env` to another value (e.g. `3334`) and update your IDE config accordingly.

**Dashboard shows blank / API errors**
Ensure the REST API is running (`uvicorn api:app --port 8000`) before opening the dashboard. Check that `NEXT_PUBLIC_API_URL` in `.env` matches the API port.

**Windsurf/Antigravity not picking up tools**
Confirm you are using `serverUrl` (not `url`). The two keys are not interchangeable in Windsurf's MCP implementation.
