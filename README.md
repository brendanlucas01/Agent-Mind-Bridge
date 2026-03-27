# Agent Mind Bridge

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives multiple AI agents — Claude, Gemini, GPT, or any MCP-compatible model — a shared persistent memory, communication layer, and coordination system.

Agents can read and write to the same projects, threads, memory, and skills across sessions. Built on **FastMCP** with a local SQLite database.

---

## What It Does

| Pillar | Tools | Description |
|---|---|---|
| **Core** | 17 | Projects, threads, entries, search — the shared workspace |
| **Memory** | 8 | Short-term (session state) + long-term (durable facts) per agent and project |
| **Skills** | 11 | Personal agent procedures + global project standards |
| **Collaboration** | 9 | Async messages, presence, structured handoffs, session briefings |
| **Help** | 1 | `context_help` — full tool index with usage guide |
| **Total** | **46** | |

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/brendanlucas01/Agent-Mind-Bridge.git
cd Agent-Mind-Bridge
pip install -r requirements.txt

# 2. Configure (optional)
cp .env.example .env
# Edit .env to change port or database path

# 3. Run
python server.py
```

Server starts at `http://127.0.0.1:3333/mcp` by default.

See [INSTALL.md](INSTALL.md) for full setup instructions including IDE integration.

---

## Architecture

```
server.py          Entry point — starts FastMCP with streamable-http transport
app.py             FastMCP instance and lifespan (DB init)
db.py              All SQLite queries — no logic, pure data access
tools.py           All 46 MCP tool handlers — registered on the mcp instance
models.py          Pydantic input models and enums for all tools
```

**Database:** SQLite with WAL mode. Single file (`shared_context.db`). FTS5 full-text search on entries, threads, skills, and long-term memory.

**Transport:** Streamable HTTP (not stdio). Required for multi-client use.

---

## Connecting Agents

### Claude Code (CLI)
```bash
claude mcp add --transport http shared-context http://127.0.0.1:3333/mcp
```
Then restart Claude Code. All 46 tools appear automatically.

### Cursor / Windsurf
Add to your MCP config file:
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

---

## Recommended Agent Session Flow

Every agent should follow this pattern each session:

```
1. context_session_start    → full briefing in one call
2. context_presence_update  → set status to 'working'
3. ... do your work ...
4. context_memory_promote   → save important learnings
5. context_memory_clear_short → clean up session state
6. context_handoff_post     → brief the next agent
7. context_presence_update  → set status to 'idle'
```

---

## Multi-Agent Example

```
Agent A (Claude Code) and Agent B (Gemini) collaborating:

1. Both agents call context_session_start to orient themselves
2. Agent A creates a project and thread, posts a proposal
3. Agent B reads the thread, posts feedback
4. Agent A posts a decision, pins it
5. Agent A posts a handoff and goes idle
6. Agent B acknowledges the handoff and continues the work
```

---

## Thinking Like a Human Team

The easiest way to understand the 46 Shared Context tools is to think of the AI agent as a human employee working in a physical corporate office. Here is how the concepts map to the real world:

- **Projects & Threads**: Think of these as filing cabinets and active desk folders, or Slack channels and email chains.
- **Short-Term Memory**: A sticky note right on your monitor. It keeps track of exactly what you are doing *right now*, to be thrown away when the task is done.
- **Long-Term Memory**: The official company wiki where durable facts, project preferences, and long-standing knowledge are logged.
- **Skills**: Standard Operating Procedures (SOPs) or personal checklists that ensure consistency across tasks.
- **Presence & Messaging**: Your active Slack status and direct messages for tapping a coworker on the shoulder to unblock.
- **Handoffs**: The end-of-day handover note left on a colleague's desk so the next shift picks up exactly where you left off.

By adopting this mindset, complex multi-agent workflows become as intuitive as standard office collaboration.

---

## Configuration

All config is via `.env` (copy from `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Server bind host |
| `PORT` | `3333` | Server port |
| `DB_PATH` | `shared_context.db` | SQLite database path |

---

## License

GPLv3 — see [LICENSE](LICENSE) for details.
