# Installation Guide

## Prerequisites

- Python 3.11 or higher
- pip

Check your version:
```bash
python --version
```

---

## Step 1 — Clone the Repository

```bash
git clone <repo-url>
cd mcp_communicator
```

---

## Step 2 — Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `mcp[cli]` — FastMCP framework
- `pydantic` — input validation
- `uvicorn` — ASGI server
- `python-dotenv` — `.env` file support

---

## Step 3 — Configure (Optional)

Copy the example config:
```bash
cp .env.example .env
```

The defaults work out of the box. Edit `.env` only if you need to:
- Change the port (default: `3333`)
- Change the database path (default: `shared_context.db` in the project folder)

---

## Step 4 — Start the Server

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

```bash
claude mcp add --transport http shared-context http://127.0.0.1:3333/mcp
```

Restart Claude Code. Run `/mcp` to verify the server appears with 46 tools.

### Cursor

Edit `~/.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "shared-context": {
      "type": "http",
      "url": "http://127.0.0.1:3333/mcp"
    }
  }
}
```

### Windsurf

Edit `~/.codeium/windsurf/mcp_config.json`:
```json
{
  "mcpServers": {
    "shared-context": {
      "serverUrl": "http://127.0.0.1:3333/mcp"
    }
  }
}
```

### Zed

In `settings.json`:
```json
{
  "context_servers": {
    "shared-context": {
      "transport": {
        "type": "http",
        "url": "http://127.0.0.1:3333/mcp"
      }
    }
  }
}
```

---

## Verifying the Installation

### MCP Inspector
1. Install: `npx @modelcontextprotocol/inspector`
2. Open the inspector in your browser
3. Set transport to **Streamable HTTP**
4. URL: `http://127.0.0.1:3333/mcp`
5. Click Connect — you should see 46 tools listed

### Quick Smoke Test (Claude Code)
After connecting, ask Claude:
```
Call context_help to show all available tools
```
You should get a structured index of all 46 tools organized by pillar.

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
