# Shared Context MCP Server — Upgrade v2 Spec
## Memory + Skills + Agent Collaboration

> **This document is a complete upgrade specification for Claude Code.**
>
> **Prerequisites:**
> - The base server from `ARCHITECTURE.md` must already be implemented and working.
> - All 17 base tools must be passing the testing checklist in `ARCHITECTURE.md` section 12.
> - Do not modify any existing tables, tools, or files unless explicitly instructed here.
>
> **What this upgrade adds:**
> - Pillar 2: Memory (short-term + long-term) — 8 tools
> - Pillar 3: Skills (personal + global) — 11 tools
> - Pillar 4: Agent Collaboration (messages + presence + handoffs) — 9 tools
> - `context_help` index tool — 1 tool
>
> **Total new tools: 29. Grand total after upgrade: 46 tools.**

---

## Table of Contents

1. [Upgrade Strategy](#1-upgrade-strategy)
2. [New Database Tables](#2-new-database-tables)
3. [New FTS5 Tables & Triggers](#3-new-fts5-tables--triggers)
4. [New Pydantic Models](#4-new-pydantic-models)
5. [Pillar 2 — Memory Tools](#5-pillar-2--memory-tools)
6. [Pillar 3 — Skills Tools](#6-pillar-3--skills-tools)
7. [Pillar 4 — Collaboration Tools](#7-pillar-4--collaboration-tools)
8. [The Help Tool](#8-the-help-tool)
9. [Implementation Order](#9-implementation-order)
10. [Testing Checklist](#10-testing-checklist)
11. [Full Tool Index](#11-full-tool-index)

---

## 1. Upgrade Strategy

### File Changes

| File | Action |
|---|---|
| `db.py` | ADD new tables and FTS5 setup. Do not touch existing functions. |
| `models.py` | ADD new Pydantic models and enums. Do not touch existing models. |
| `tools.py` | ADD new tool functions. Do not touch existing tools. |
| `server.py` | No changes needed. |
| `requirements.txt` | No changes needed. |

### Upgrade Approach

All new tables use `CREATE TABLE IF NOT EXISTS` — running the upgraded `init_db()` on an existing database is safe and non-destructive. The existing 17 tools continue working without any modification.

Add a single `init_db_v2(conn)` function in `db.py` and call it from the lifespan in `server.py` immediately after `init_db(conn)`:

```python
# In server.py lifespan, after init_db(conn):
from db import init_db, init_db_v2
init_db(conn)
init_db_v2(conn)
```

All new query functions go into `db.py`. All new tool handlers go into `tools.py`. Keep the same strict separation rules from `ARCHITECTURE.md` section 3.

---

## 2. New Database Tables

Add all of the following inside `init_db_v2(conn)` in `db.py`.

---

### 2.1 Memory Tables

```sql
-- Short-term memory: working state for current task/session
-- Scoped to one agent within one project (or globally if project_id is null)
CREATE TABLE IF NOT EXISTS short_term_memory (
    id          TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL REFERENCES agents(id),
    project_id  TEXT REFERENCES projects(id),    -- nullable = cross-project
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    expires_at  TEXT,                             -- nullable = no expiry
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(agent_id, project_id, key)             -- one value per key per agent per project
);

-- Long-term memory: durable facts that survive across sessions
-- Scoped flexibly: agent+project, project-only, or global (both nullable)
CREATE TABLE IF NOT EXISTS long_term_memory (
    id               TEXT PRIMARY KEY,
    agent_id         TEXT REFERENCES agents(id),     -- nullable = not agent-specific
    project_id       TEXT REFERENCES projects(id),   -- nullable = cross-project
    key              TEXT NOT NULL,
    value            TEXT NOT NULL,
    tags             TEXT,                           -- comma-separated tags
    confidence       TEXT NOT NULL DEFAULT 'medium', -- 'low' | 'medium' | 'high'
    source_thread_id TEXT REFERENCES threads(id),    -- nullable = where this was learned
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stm_agent_project ON short_term_memory(agent_id, project_id);
CREATE INDEX IF NOT EXISTS idx_ltm_agent_project ON long_term_memory(agent_id, project_id);
CREATE INDEX IF NOT EXISTS idx_ltm_project ON long_term_memory(project_id);
```

---

### 2.2 Skills Tables

```sql
-- Personal skills: agent-specific behaviors, preferences, procedures
-- Only the owning agent can access these
CREATE TABLE IF NOT EXISTS personal_skills (
    id           TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL REFERENCES agents(id),
    name         TEXT NOT NULL,
    skill_type   TEXT NOT NULL,   -- 'instruction' | 'procedure' | 'template' | 'pattern'
    description  TEXT NOT NULL,   -- one-line summary for discovery
    content      TEXT NOT NULL,   -- the full skill content
    tags         TEXT,            -- comma-separated
    usage_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(agent_id, name)        -- name unique per agent
);

-- Global skills: project-wide or cross-project standards all agents must follow
-- Nullable project_id = truly global (applies to all projects)
CREATE TABLE IF NOT EXISTS global_skills (
    id           TEXT PRIMARY KEY,
    project_id   TEXT REFERENCES projects(id),   -- nullable = cross-project standard
    name         TEXT NOT NULL,
    skill_type   TEXT NOT NULL,   -- 'instruction' | 'procedure' | 'template' | 'pattern'
    description  TEXT NOT NULL,
    content      TEXT NOT NULL,
    tags         TEXT,
    created_by   TEXT NOT NULL REFERENCES agents(id),
    version      INTEGER NOT NULL DEFAULT 1,      -- increments on every update
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(project_id, name)      -- name unique per project (nulls not enforced — handle in app)
);

CREATE INDEX IF NOT EXISTS idx_personal_skills_agent ON personal_skills(agent_id);
CREATE INDEX IF NOT EXISTS idx_global_skills_project ON global_skills(project_id);
```

---

### 2.3 Collaboration Tables

```sql
-- Agent messages: async direct messages between agents
-- to_agent_id nullable = broadcast to all agents in the project
CREATE TABLE IF NOT EXISTS agent_messages (
    id           TEXT PRIMARY KEY,
    from_agent_id TEXT NOT NULL REFERENCES agents(id),
    to_agent_id   TEXT REFERENCES agents(id),     -- nullable = broadcast
    project_id    TEXT REFERENCES projects(id),   -- nullable = not project-specific
    subject       TEXT NOT NULL,
    content       TEXT NOT NULL,
    priority      TEXT NOT NULL DEFAULT 'normal', -- 'low' | 'normal' | 'high'
    thread_ref    TEXT REFERENCES threads(id),    -- nullable = link to related thread
    is_read       INTEGER NOT NULL DEFAULT 0,     -- 0 | 1
    created_at    TEXT NOT NULL
);

-- Agent presence: current status and working state
-- One row per agent per project, upserted on update
CREATE TABLE IF NOT EXISTS agent_presence (
    id           TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL REFERENCES agents(id),
    project_id   TEXT REFERENCES projects(id),   -- nullable = general presence
    status       TEXT NOT NULL DEFAULT 'idle',   -- 'idle' | 'working' | 'blocked' | 'reviewing'
    current_task TEXT,                           -- free text: what the agent is doing right now
    updated_at   TEXT NOT NULL,
    UNIQUE(agent_id, project_id)
);

-- Handoff notes: structured end-of-session summaries
-- Left by one agent for whoever picks up next
CREATE TABLE IF NOT EXISTS handoffs (
    id              TEXT PRIMARY KEY,
    from_agent_id   TEXT NOT NULL REFERENCES agents(id),
    project_id      TEXT NOT NULL REFERENCES projects(id),
    summary         TEXT NOT NULL,   -- what was accomplished this session
    in_progress     TEXT,            -- what's half-done
    blockers        TEXT,            -- what's stuck and why
    next_steps      TEXT,            -- suggested actions for the next agent
    thread_refs     TEXT,            -- comma-separated thread UUIDs
    acknowledged_by TEXT REFERENCES agents(id),   -- nullable until read
    acknowledged_at TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_to_agent ON agent_messages(to_agent_id, is_read);
CREATE INDEX IF NOT EXISTS idx_messages_from_agent ON agent_messages(from_agent_id);
CREATE INDEX IF NOT EXISTS idx_messages_project ON agent_messages(project_id);
CREATE INDEX IF NOT EXISTS idx_presence_agent ON agent_presence(agent_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_project ON handoffs(project_id, created_at);
```

---

## 3. New FTS5 Tables & Triggers

Add inside `init_db_v2(conn)` after the main tables.

```sql
-- FTS5 for long-term memory values
CREATE VIRTUAL TABLE IF NOT EXISTS ltm_fts USING fts5(
    value,
    content='long_term_memory',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS ltm_ai AFTER INSERT ON long_term_memory BEGIN
    INSERT INTO ltm_fts(rowid, value) VALUES (new.rowid, new.value);
END;
CREATE TRIGGER IF NOT EXISTS ltm_au AFTER UPDATE ON long_term_memory BEGIN
    INSERT INTO ltm_fts(ltm_fts, rowid, value) VALUES ('delete', old.rowid, old.value);
    INSERT INTO ltm_fts(rowid, value) VALUES (new.rowid, new.value);
END;
CREATE TRIGGER IF NOT EXISTS ltm_ad AFTER DELETE ON long_term_memory BEGIN
    INSERT INTO ltm_fts(ltm_fts, rowid, value) VALUES ('delete', old.rowid, old.value);
END;

-- FTS5 for personal skill content
CREATE VIRTUAL TABLE IF NOT EXISTS personal_skills_fts USING fts5(
    description, content,
    content='personal_skills',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS ps_ai AFTER INSERT ON personal_skills BEGIN
    INSERT INTO personal_skills_fts(rowid, description, content) VALUES (new.rowid, new.description, new.content);
END;
CREATE TRIGGER IF NOT EXISTS ps_au AFTER UPDATE ON personal_skills BEGIN
    INSERT INTO personal_skills_fts(personal_skills_fts, rowid, description, content) VALUES ('delete', old.rowid, old.description, old.content);
    INSERT INTO personal_skills_fts(rowid, description, content) VALUES (new.rowid, new.description, new.content);
END;
CREATE TRIGGER IF NOT EXISTS ps_ad AFTER DELETE ON personal_skills BEGIN
    INSERT INTO personal_skills_fts(personal_skills_fts, rowid, description, content) VALUES ('delete', old.rowid, old.description, old.content);
END;

-- FTS5 for global skill content
CREATE VIRTUAL TABLE IF NOT EXISTS global_skills_fts USING fts5(
    description, content,
    content='global_skills',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS gs_ai AFTER INSERT ON global_skills BEGIN
    INSERT INTO global_skills_fts(rowid, description, content) VALUES (new.rowid, new.description, new.content);
END;
CREATE TRIGGER IF NOT EXISTS gs_au AFTER UPDATE ON global_skills BEGIN
    INSERT INTO global_skills_fts(global_skills_fts, rowid, description, content) VALUES ('delete', old.rowid, old.description, old.content);
    INSERT INTO global_skills_fts(rowid, description, content) VALUES (new.rowid, new.description, new.content);
END;
CREATE TRIGGER IF NOT EXISTS gs_ad AFTER DELETE ON global_skills BEGIN
    INSERT INTO global_skills_fts(global_skills_fts, rowid, description, content) VALUES ('delete', old.rowid, old.description, old.content);
END;
```

---

## 4. New Pydantic Models

Add all of the following to `models.py`. Do not modify existing models.

```python
# ── New Enums ─────────────────────────────────────────────────────────────────

class MemoryScope(str, Enum):
    AGENT_PROJECT = "agent_project"   # scoped to this agent + this project
    PROJECT       = "project"         # shared across all agents in project
    GLOBAL        = "global"          # shared across all agents and all projects

class Confidence(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"

class SkillType(str, Enum):
    INSTRUCTION = "instruction"   # a rule or constraint to follow
    PROCEDURE   = "procedure"     # a step-by-step process
    TEMPLATE    = "template"      # a reusable code or text scaffold
    PATTERN     = "pattern"       # an architectural or design pattern

class AgentStatus(str, Enum):
    IDLE      = "idle"
    WORKING   = "working"
    BLOCKED   = "blocked"
    REVIEWING = "reviewing"

class MessagePriority(str, Enum):
    LOW    = "low"
    NORMAL = "normal"
    HIGH   = "high"


# ── Short-Term Memory Models ───────────────────────────────────────────────────

class MemorySetShortInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:   str           = Field(..., description="Agent UUID")
    project_id: Optional[str] = Field(None, description="Project UUID. Omit for cross-project memory.")
    key:        str           = Field(..., description="Memory key (e.g. 'current_file', 'current_task')", min_length=1, max_length=200)
    value:      str           = Field(..., description="Memory value to store", min_length=1, max_length=10000)
    expires_at: Optional[str] = Field(None, description="Optional ISO 8601 UTC expiry timestamp. Omit for no expiry.")

class MemoryGetShortInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id:   str           = Field(..., description="Agent UUID")
    project_id: Optional[str] = Field(None, description="Project UUID. Omit for cross-project memory.")
    key:        Optional[str] = Field(None, description="Specific key to retrieve. Omit to get all keys for this agent+project.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class MemoryClearShortInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id:   str           = Field(..., description="Agent UUID")
    project_id: Optional[str] = Field(None, description="Project UUID. Omit to clear all cross-project memory for this agent.")


# ── Long-Term Memory Models ────────────────────────────────────────────────────

class MemorySetLongInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:         Optional[str]  = Field(None, description="Agent UUID. Omit for project-wide or global memory.")
    project_id:       Optional[str]  = Field(None, description="Project UUID. Omit for global memory.")
    key:              str            = Field(..., description="Memory key", min_length=1, max_length=200)
    value:            str            = Field(..., description="Memory value", min_length=1, max_length=50000)
    tags:             Optional[str]  = Field(None, description="Comma-separated tags (e.g. 'api,rate-limit,adzuna')")
    confidence:       Confidence     = Field(default=Confidence.MEDIUM, description="'low' | 'medium' | 'high'")
    source_thread_id: Optional[str]  = Field(None, description="Thread UUID where this was learned. Optional.")

class MemoryGetLongInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id:   Optional[str] = Field(None, description="Agent UUID to scope results. Omit for project-wide or global.")
    project_id: Optional[str] = Field(None, description="Project UUID to scope results. Omit for global.")
    key:        Optional[str] = Field(None, description="Specific key. Omit to list all in scope.")
    tags:       Optional[str] = Field(None, description="Filter by tag (single tag)")
    limit:      int           = Field(default=20, ge=1, le=100)
    offset:     int           = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class MemoryDeleteLongInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    memory_id: str = Field(..., description="Long-term memory UUID to delete")

class MemoryPromoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:         str           = Field(..., description="Agent UUID (owner of the short-term memory)")
    project_id:       Optional[str] = Field(None, description="Project UUID of the short-term memory")
    key:              str           = Field(..., description="Short-term memory key to promote")
    target_scope:     MemoryScope   = Field(..., description="'agent_project' | 'project' | 'global'")
    override_value:   Optional[str] = Field(None, description="Optionally rewrite the value when promoting. Omit to use current value as-is.")
    tags:             Optional[str] = Field(None, description="Tags to attach to the long-term memory")
    confidence:       Confidence    = Field(default=Confidence.MEDIUM)
    source_thread_id: Optional[str] = Field(None, description="Thread UUID where this was learned")
    clear_after:      bool          = Field(default=True, description="If true, delete the short-term entry after promoting. Default: true.")


# ── Personal Skill Models ──────────────────────────────────────────────────────

class SkillCreatePersonalInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:    str           = Field(..., description="Agent UUID — owner of this skill")
    name:        str           = Field(..., description="Unique skill name for this agent (e.g. 'debug-content-script')", min_length=1, max_length=100)
    skill_type:  SkillType     = Field(..., description="'instruction' | 'procedure' | 'template' | 'pattern'")
    description: str           = Field(..., description="One-line summary used for discovery and search", min_length=1, max_length=300)
    content:     str           = Field(..., description="Full skill content", min_length=1, max_length=50000)
    tags:        Optional[str] = Field(None, description="Comma-separated tags")

class SkillGetPersonalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id:        str            = Field(..., description="Agent UUID")
    name:            Optional[str]  = Field(None, description="Skill name. Omit to list all personal skills for this agent.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class SkillListPersonalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id:        str            = Field(..., description="Agent UUID")
    skill_type:      Optional[SkillType] = Field(None, description="Filter by type")
    tags:            Optional[str]  = Field(None, description="Filter by tag (single tag)")
    limit:           int            = Field(default=20, ge=1, le=100)
    offset:          int            = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class SkillUpdatePersonalInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    skill_id:    str           = Field(..., description="Personal skill UUID")
    description: Optional[str] = Field(None, description="Updated one-line description", max_length=300)
    content:     Optional[str] = Field(None, description="Updated skill content", max_length=50000)
    tags:        Optional[str] = Field(None, description="Updated comma-separated tags")

class SkillDeletePersonalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    skill_id: str = Field(..., description="Personal skill UUID to delete")


# ── Global Skill Models ────────────────────────────────────────────────────────

class SkillCreateGlobalInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    project_id:  Optional[str] = Field(None, description="Project UUID. Omit to create a truly global skill (applies to all projects).")
    name:        str           = Field(..., description="Unique skill name within this project (e.g. 'api-response-format')", min_length=1, max_length=100)
    skill_type:  SkillType     = Field(..., description="'instruction' | 'procedure' | 'template' | 'pattern'")
    description: str           = Field(..., description="One-line summary", min_length=1, max_length=300)
    content:     str           = Field(..., description="Full skill content — all agents will follow this", min_length=1, max_length=50000)
    tags:        Optional[str] = Field(None, description="Comma-separated tags")
    created_by:  str           = Field(..., description="Agent UUID creating this skill")

class SkillGetGlobalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name:            str            = Field(..., description="Skill name to retrieve")
    project_id:      Optional[str]  = Field(None, description="Project UUID. Resolution order: project-scoped first, then global fallback.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class SkillListGlobalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id:      Optional[str]       = Field(None, description="Project UUID. Returns project-scoped AND truly global skills. Omit for global-only.")
    skill_type:      Optional[SkillType] = Field(None, description="Filter by type")
    tags:            Optional[str]       = Field(None, description="Filter by tag")
    limit:           int                 = Field(default=20, ge=1, le=100)
    offset:          int                 = Field(default=0, ge=0)
    response_format: ResponseFormat      = Field(default=ResponseFormat.MARKDOWN)

class SkillUpdateGlobalInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    skill_id:    str           = Field(..., description="Global skill UUID")
    description: Optional[str] = Field(None, max_length=300)
    content:     Optional[str] = Field(None, max_length=50000)
    tags:        Optional[str] = Field(None)
    # version increments automatically on every update — do not accept from client

class SkillDeleteGlobalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    skill_id: str = Field(..., description="Global skill UUID to delete")

class SkillSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    query:           str            = Field(..., description="FTS5 search query across skill descriptions and content", min_length=1, max_length=300)
    agent_id:        Optional[str]  = Field(None, description="Agent UUID — includes personal skills for this agent in results")
    project_id:      Optional[str]  = Field(None, description="Project UUID — includes project-scoped global skills in results")
    limit:           int            = Field(default=10, ge=1, le=50)
    offset:          int            = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ── Collaboration Models ───────────────────────────────────────────────────────

class MessageSendInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    from_agent_id: str                = Field(..., description="Sending agent UUID")
    to_agent_id:   Optional[str]      = Field(None, description="Receiving agent UUID. Omit to broadcast to all agents in the project.")
    project_id:    Optional[str]      = Field(None, description="Project context UUID")
    subject:       str                = Field(..., description="Message subject line", min_length=1, max_length=200)
    content:       str                = Field(..., description="Message body", min_length=1, max_length=10000)
    priority:      MessagePriority    = Field(default=MessagePriority.NORMAL, description="'low' | 'normal' | 'high'")
    thread_ref:    Optional[str]      = Field(None, description="Optional thread UUID this message relates to")

class MessageInboxInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id:        str            = Field(..., description="Agent UUID — retrieve messages addressed to this agent or broadcast")
    project_id:      Optional[str]  = Field(None, description="Filter to a specific project. Omit for all.")
    unread_only:     bool           = Field(default=True, description="If true, return only unread messages. Default: true.")
    limit:           int            = Field(default=20, ge=1, le=100)
    offset:          int            = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class MessageMarkReadInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: str = Field(..., description="Message UUID to mark as read")

class PresenceUpdateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:     str                = Field(..., description="Agent UUID")
    project_id:   Optional[str]      = Field(None, description="Project UUID context")
    status:       AgentStatus        = Field(..., description="'idle' | 'working' | 'blocked' | 'reviewing'")
    current_task: Optional[str]      = Field(None, description="What the agent is doing right now", max_length=300)

class PresenceGetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id:      Optional[str]  = Field(None, description="Filter presence to a specific project. Omit for all.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class HandoffPostInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    from_agent_id: str           = Field(..., description="Agent UUID leaving the handoff note")
    project_id:    str           = Field(..., description="Project UUID this handoff is for")
    summary:       str           = Field(..., description="What was accomplished this session", min_length=1, max_length=5000)
    in_progress:   Optional[str] = Field(None, description="What is partially done and needs continuation", max_length=2000)
    blockers:      Optional[str] = Field(None, description="What is stuck and why", max_length=2000)
    next_steps:    Optional[str] = Field(None, description="Suggested actions for whoever picks up next", max_length=2000)
    thread_refs:   Optional[str] = Field(None, description="Comma-separated thread UUIDs relevant to this handoff")

class HandoffGetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id:      str            = Field(..., description="Project UUID")
    limit:           int            = Field(default=5, ge=1, le=20, description="How many recent handoffs to return. Default: 5.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class HandoffAcknowledgeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    handoff_id: str = Field(..., description="Handoff UUID to acknowledge")
    agent_id:   str = Field(..., description="Agent UUID acknowledging the handoff")
```

---

## 5. Pillar 2 — Memory Tools

8 tools total. All prefixed `context_memory_`.

---

### 5.1 `context_memory_set_short`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        MemorySetShortInput
Returns:      Confirmation string

Docstring:
  "Write or overwrite a short-term memory key for an agent.
   Short-term memory is working state for the current task or session.
   Use this to track what you're currently doing, which files you've modified,
   your current approach, or any state that needs to survive across a few tool calls.
   At end of session, call context_memory_clear_short to clean up,
   or context_memory_promote to elevate important learnings to long-term memory."

Behavior:
  - UPSERT on (agent_id, project_id, key) — update if exists, insert if not
  - Set updated_at = now on every call
  - Validate agent exists. Error: "Agent '{agent_id}' not found."
  - Validate project exists if project_id provided.
  - Return: "Short-term memory key '{key}' set for agent {agent_name}."

Expiry handling:
  - Store expires_at as-is if provided
  - On read (context_memory_get_short), check expires_at — if past, treat as not found
  - Lazy expiry: no background job needed, just check on read
```

---

### 5.2 `context_memory_get_short`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        MemoryGetShortInput
Returns:      Single value or all keys for agent+project

Docstring:
  "Retrieve short-term memory for an agent.
   Provide a specific key to get one value, or omit key to get all current
   short-term memory for this agent and project.
   Expired entries are automatically excluded."

Behavior:
  - If key provided: return single value or "Key '{key}' not found in short-term memory."
  - If key omitted: return all non-expired entries for agent+project
  - Filter out entries where expires_at < now
  - Include in response: key, value, expires_at (if set), updated_at
```

---

### 5.3 `context_memory_clear_short`

```
Annotations:  readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
Input:        MemoryClearShortInput
Returns:      Confirmation with count of cleared entries

Docstring:
  "Clear all short-term memory for an agent in a project. Call this at end of session.
   If you want to preserve important learnings before clearing, call
   context_memory_promote first for each key worth keeping."

Behavior:
  - DELETE all short_term_memory rows for agent_id + project_id
  - Return: "Cleared {n} short-term memory entries for agent {agent_name}."
  - Idempotent: if nothing to clear, return "No short-term memory to clear."
```

---

### 5.4 `context_memory_set_long`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        MemorySetLongInput
Returns:      JSON — the created or updated memory object

Docstring:
  "Write a long-term memory — a durable fact that persists across sessions.
   Scope via agent_id and project_id:
     - Both set: private to this agent within this project
     - project_id only: shared across all agents in the project
     - Neither set: global, shared across all agents and all projects
   Use tags and confidence to make memories easier to find and evaluate later.
   Link source_thread_id to preserve where this fact was learned."

Behavior:
  - No UNIQUE constraint on long-term memory — multiple entries per key are allowed
    (different agents, different scopes, or updated over time)
  - Generate uuid4, set created_at = updated_at = now
  - INSERT into long_term_memory
  - FTS5 triggers handle indexing automatically
  - Return full memory dict as JSON
```

---

### 5.5 `context_memory_get_long`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        MemoryGetLongInput
Returns:      Paginated list or single memory entry

Docstring:
  "Retrieve long-term memories. Scope via agent_id and project_id.
   Provide a key to look up a specific fact, or omit to browse all memories in scope.
   Filter by tags to narrow results. Results include the source thread reference
   so you can trace where each fact was learned."

Behavior:
  - If key provided: filter by exact key match within scope
  - Scope resolution: WHERE agent_id = ? AND project_id = ? (use IS NULL for nulls)
  - Apply tag filter: WHERE tags LIKE '%{tag}%' if tag provided
  - Return with pagination metadata
```

---

### 5.6 `context_memory_delete_long`

```
Annotations:  readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
Input:        MemoryDeleteLongInput
Returns:      Confirmation string

Behavior:
  - DELETE from long_term_memory WHERE id = memory_id
  - FTS5 triggers handle index cleanup automatically
  - Idempotent: if not found, return "Memory '{memory_id}' not found — nothing deleted."
  - Return: "Long-term memory '{key}' deleted."
```

---

### 5.7 `context_memory_search`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        MemoryGetLongInput (reuse — query param via key field) 
              — actually create a dedicated MemorySearchInput:

class MemorySearchInput(BaseModel):
    query:      str           = Field(..., min_length=1, max_length=300)
    agent_id:   Optional[str] = Field(None)
    project_id: Optional[str] = Field(None)
    limit:      int           = Field(default=10, ge=1, le=50)
    offset:     int           = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

Docstring:
  "Full-text search across long-term memory values.
   Supports FTS5 query syntax. Falls back to LIKE search on malformed queries.
   Scope via agent_id and project_id. Returns snippets — retrieve full value
   via context_memory_get_long if needed."

Behavior:
  - FTS5 MATCH on ltm_fts with try/except LIKE fallback (same pattern as context_search)
  - Return: id, key, snippet, agent_name (if scoped), project_name (if scoped),
            confidence, tags, source_thread_id, relevance ('high'|'medium'|'low')
```

---

### 5.8 `context_memory_promote`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        MemoryPromoteInput
Returns:      JSON — the created long-term memory object

Docstring:
  "Promote a short-term memory entry to long-term memory.
   Use this at end of session to preserve important learnings before clearing short-term memory.
   You can optionally rewrite the value when promoting to make it more precise or general.
   Set clear_after=true (default) to automatically remove the short-term entry after promotion."

Behavior:
  1. Fetch short-term entry by (agent_id, project_id, key). Error if not found.
  2. Use override_value if provided, else use current short-term value.
  3. Resolve scope from target_scope:
       'agent_project' → agent_id + project_id both set
       'project'       → agent_id = null, project_id set
       'global'        → both null
  4. INSERT into long_term_memory with resolved scope.
  5. If clear_after=True: DELETE the short-term entry.
  6. Return the created long-term memory as JSON.
```

---

## 6. Pillar 3 — Skills Tools

11 tools total. All prefixed `context_skill_`.

---

### 6.1 `context_skill_create_personal`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        SkillCreatePersonalInput
Returns:      JSON — the created skill object

Docstring:
  "Create a personal skill — a reusable behavior, procedure, or pattern
   that only this agent uses. Personal skills capture how you individually
   approach problems. Other agents cannot see or access these.
   skill_type options: 'instruction' (a rule to follow), 'procedure' (step-by-step process),
   'template' (reusable scaffold), 'pattern' (architectural approach)."

Behavior:
  - Validate agent exists.
  - UNIQUE(agent_id, name): error if name already exists for this agent.
    "A personal skill named '{name}' already exists for this agent. Use context_skill_update_personal to modify it."
  - Generate uuid4, set created_at = updated_at = now, usage_count = 0
  - INSERT into personal_skills
  - FTS5 triggers handle indexing automatically
  - Return full skill dict as JSON
```

---

### 6.2 `context_skill_get_personal`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SkillGetPersonalInput
Returns:      Single skill with full content

Docstring:
  "Retrieve a personal skill by name. Also increments the usage_count
   so frequently-used skills can be surfaced in listings."

Behavior:
  - Fetch personal_skills WHERE agent_id = ? AND name = ?
  - On successful retrieval: UPDATE usage_count = usage_count + 1
  - Error if not found: "Personal skill '{name}' not found for this agent.
    Use context_skill_list_personal to browse available skills, or context_skill_search to search."
  - Return full content including usage_count
```

---

### 6.3 `context_skill_list_personal`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SkillListPersonalInput
Returns:      Paginated list — descriptions only, not full content

Docstring:
  "List personal skills for an agent. Returns descriptions and metadata,
   not full content. Use context_skill_get_personal to retrieve a specific skill's content.
   Sort order: most-used first (usage_count DESC), then alphabetical."

Behavior:
  - Filter by skill_type if provided
  - Filter by tag: WHERE tags LIKE '%{tag}%' if provided
  - ORDER BY usage_count DESC, name ASC
  - Return: id, name, skill_type, description, tags, usage_count, updated_at
  - Do NOT return content field in list — keeps response lean
```

---

### 6.4 `context_skill_update_personal`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        SkillUpdatePersonalInput
Returns:      JSON — the updated skill object

Behavior:
  - Fetch skill by id. Error if not found.
  - Update only the fields provided (description, content, tags) — partial update
  - Set updated_at = now
  - FTS5 triggers handle re-indexing automatically
  - Return updated skill dict as JSON
```

---

### 6.5 `context_skill_delete_personal`

```
Annotations:  readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
Input:        SkillDeletePersonalInput
Returns:      Confirmation string

Behavior:
  - DELETE WHERE id = skill_id
  - FTS5 triggers handle cleanup automatically
  - Idempotent: if not found, return "Personal skill not found — nothing deleted."
```

---

### 6.6 `context_skill_create_global`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        SkillCreateGlobalInput
Returns:      JSON — the created global skill object

Docstring:
  "Create a global skill — a standard, convention, or pattern that ALL agents
   in this project must follow consistently. This is how you enforce consistency
   across Claude Code, Gemini, and any other agent regardless of interface.
   Set project_id to scope to one project. Omit project_id for a truly global
   standard that applies across all projects.
   All agents should call context_skill_list_global at session start to load
   current project standards."

Behavior:
  - Validate project exists if project_id provided.
  - Validate created_by agent exists.
  - Name uniqueness: check within project scope (handle null project_id in app code,
    not via DB constraint since NULL != NULL in SQLite).
    Error: "A global skill named '{name}' already exists in this scope."
  - Set version = 1, created_at = updated_at = now
  - Return full skill dict as JSON
```

---

### 6.7 `context_skill_get_global`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SkillGetGlobalInput
Returns:      Single global skill with full content

Docstring:
  "Retrieve a global skill by name. Resolution order:
   1. Look for skill with this name in the specified project (project_id scoped)
   2. If not found, look for a truly global skill (project_id = null) with this name
   3. If not found, return error with suggestion to search.
   The version field tells you if this skill has been updated since you last read it."

Behavior:
  - Resolution order as described in docstring
  - Return: id, project_id, name, skill_type, description, content, tags,
            created_by, version, created_at, updated_at
  - Include in response: "scope": "project" | "global" (which level matched)
```

---

### 6.8 `context_skill_list_global`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SkillListGlobalInput
Returns:      Paginated list — descriptions only, not full content

Docstring:
  "List global skills. If project_id is provided, returns BOTH project-scoped
   skills AND truly global skills (null project_id), sorted by scope then name.
   Call this at the start of each session to load current project standards.
   Use context_skill_get_global to retrieve a specific skill's full content."

Behavior:
  - If project_id provided: WHERE project_id = ? OR project_id IS NULL
  - If no project_id: WHERE project_id IS NULL only
  - Label each result with scope: 'project' or 'global'
  - ORDER BY scope ASC (project first), name ASC
  - Return: id, name, skill_type, description, tags, version, scope, updated_at
  - Do NOT return content — keeps response lean for session-start loading
```

---

### 6.9 `context_skill_update_global`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        SkillUpdateGlobalInput
Returns:      JSON — the updated skill with new version number

Docstring:
  "Update a global skill. Automatically increments the version number.
   Agents that have previously loaded this skill should re-read it when
   they see the version has changed."

Behavior:
  - Fetch skill by id. Error if not found.
  - UPDATE only provided fields (partial update)
  - Increment version = version + 1
  - Set updated_at = now
  - FTS5 triggers handle re-indexing automatically
  - Return updated skill including new version number
```

---

### 6.10 `context_skill_delete_global`

```
Annotations:  readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
Input:        SkillDeleteGlobalInput
Returns:      Confirmation string

Behavior:
  - DELETE WHERE id = skill_id
  - Idempotent: if not found, return "Global skill not found — nothing deleted."
```

---

### 6.11 `context_skill_search`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SkillSearchInput
Returns:      Unified search results across personal + global skills

Docstring:
  "Full-text search across skill descriptions and content.
   If agent_id is provided, includes that agent's personal skills in results.
   If project_id is provided, includes project-scoped and global skills.
   Results are labelled by source: 'personal' or 'global'.
   Returns snippets — use context_skill_get_personal or context_skill_get_global
   to retrieve full content."

Behavior:
  - Run FTS5 MATCH on personal_skills_fts (if agent_id provided) with try/except LIKE fallback
  - Run FTS5 MATCH on global_skills_fts (if project_id provided or neither provided)
  - UNION results, labelled by source
  - Return per result: source ('personal'|'global'), id, name, skill_type, description_snippet,
    content_snippet, tags, version (global only), relevance ('high'|'medium'|'low')
  - ORDER BY relevance DESC
```

---

## 7. Pillar 4 — Collaboration Tools

9 tools total. Prefixed `context_message_`, `context_presence_`, `context_handoff_`.

---

### 7.1 `context_message_send`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        MessageSendInput
Returns:      JSON — the sent message object

Docstring:
  "Send an async message to a specific agent or broadcast to all agents in a project.
   Messages persist until read. Use for: handing off work, flagging blockers,
   asking questions that don't belong in a thread, or notifying an agent of something important.
   Priority 'high' should be reserved for blockers or conflicts that need urgent attention.
   For structured end-of-session handoffs, use context_handoff_post instead."

Behavior:
  - Validate from_agent exists.
  - Validate to_agent exists if provided.
  - Validate project exists if provided.
  - Validate thread_ref exists if provided.
  - Generate uuid4, set created_at = now, is_read = 0
  - Return full message dict as JSON
```

---

### 7.2 `context_message_inbox`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        MessageInboxInput
Returns:      Paginated list of messages

Docstring:
  "Retrieve messages for an agent. Returns messages addressed directly to this agent
   AND broadcast messages (to_agent_id = null) for the specified project.
   Call this at the start of each session to check for pending communications.
   Messages are ordered newest first. Use unread_only=false to see full history."

Behavior:
  - WHERE (to_agent_id = agent_id OR to_agent_id IS NULL)
  - If project_id provided: AND project_id = ?
  - If unread_only=True: AND is_read = 0
  - ORDER BY created_at DESC
  - Return per message: id, from_agent_name, subject, content preview (first 100 chars),
    priority, is_read, thread_ref, created_at
  - Include pagination metadata
```

---

### 7.3 `context_message_read`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        MessageMarkReadInput
Returns:      Full message content + confirmation

Docstring:
  "Retrieve and mark a specific message as read.
   Returns the full message content. Automatically sets is_read = 1."

Behavior:
  - Fetch message by id. Error if not found.
  - UPDATE is_read = 1
  - Return full message: id, from_agent_name, to_agent_name (or 'broadcast'),
    project_name, subject, content, priority, thread_ref, created_at
```

---

### 7.4 `context_presence_update`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        PresenceUpdateInput
Returns:      Confirmation string

Docstring:
  "Update this agent's current status and working task.
   Call this when starting work ('working'), when blocked ('blocked'),
   when reviewing another agent's work ('reviewing'), or at session end ('idle').
   Other agents check this via context_presence_get to avoid duplicate work
   and surface blockers."

Behavior:
  - UPSERT on (agent_id, project_id) — update if row exists, insert if not
  - Set updated_at = now
  - Validate agent and project exist.
  - Return: "Presence updated: {agent_name} is now {status}."
            + " Current task: {current_task}" if current_task provided
```

---

### 7.5 `context_presence_get`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        PresenceGetInput
Returns:      All agent presence records

Docstring:
  "Get the current status of all agents. Call this at session start to understand
   what other agents are currently doing, avoid duplicating in-progress work,
   and identify any agents that are blocked and may need input."

Behavior:
  - If project_id: WHERE project_id = ? OR project_id IS NULL
  - If no project_id: return all presence records
  - Include: agent_name, agent_type, status, current_task, updated_at, project_name
  - ORDER BY updated_at DESC
  - Human-readable staleness indicator: "updated X mins/hours/days ago"
```

---

### 7.6 `context_handoff_post`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        HandoffPostInput
Returns:      JSON — the created handoff object

Docstring:
  "Post a structured end-of-session handoff note for a project.
   Use this when ending a working session so the next agent (or your next session)
   can immediately understand the current state without reading full thread histories.
   Include what you completed, what's in-progress, any blockers, and suggested next steps.
   Reference relevant thread IDs in thread_refs for easy navigation.
   Call context_presence_update with status='idle' after posting a handoff."

Behavior:
  - Validate from_agent and project exist.
  - Validate each thread_id in thread_refs if provided.
  - Generate uuid4, set created_at = now, acknowledged_by/at = null
  - Return full handoff dict as JSON
```

---

### 7.7 `context_handoff_get`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        HandoffGetInput
Returns:      Recent handoffs for a project

Docstring:
  "Retrieve recent handoff notes for a project. Call this at session start
   to understand where the project stands before reading any threads.
   Returns the N most recent handoffs (default 5), newest first.
   Unacknowledged handoffs are marked clearly — acknowledge them with
   context_handoff_acknowledge after reading."

Behavior:
  - WHERE project_id = ?
  - ORDER BY created_at DESC
  - LIMIT as specified
  - Mark unacknowledged handoffs prominently in response
  - Include: from_agent_name, summary, in_progress, blockers, next_steps,
             thread_refs (with thread titles resolved), created_at,
             acknowledged_by_name, acknowledged_at
```

---

### 7.8 `context_handoff_acknowledge`

```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        HandoffAcknowledgeInput
Returns:      Confirmation string

Docstring:
  "Acknowledge a handoff note, confirming you have read it and are taking over.
   This signals to the team that the handoff has been received and acted upon."

Behavior:
  - Fetch handoff by id. Error if not found.
  - If already acknowledged: return "Handoff already acknowledged by {agent_name} at {time}."
  - UPDATE acknowledged_by = agent_id, acknowledged_at = now
  - Return: "Handoff acknowledged. You are now responsible for: {summary_first_100_chars}..."
```

---

### 7.9 `context_session_start`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False

Input:
class SessionStartInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id:   str           = Field(..., description="Your agent UUID")
    project_id: Optional[str] = Field(None, description="Project UUID you're working on")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

Returns:  Consolidated session briefing

Docstring:
  "One-shot session startup briefing. Call this at the very start of every session
   instead of calling inbox, presence, handoff, memory, and skills separately.
   Returns a consolidated view of everything you need to orient yourself:
   unread messages, recent handoffs, other agents' presence, your short-term memory,
   and current global skills for the project.
   This is the recommended first call in every working session."

Behavior — execute all of the following in one response:
  1. Unread messages for this agent (limit 5, newest first)
  2. Most recent unacknowledged handoff for this project (1 only)
  3. All agent presence for this project
  4. Agent's short-term memory (all keys for agent+project)
  5. Global skills for this project (names + descriptions only, not full content)

Format response as clearly sectioned markdown:
  ## 📬 Messages ({n} unread)
  ## 🤝 Latest Handoff
  ## 👥 Team Presence
  ## 🧠 Your Short-Term Memory
  ## 📚 Project Skills ({n} skills)

This single call replaces 5 individual calls and is the recommended session start pattern.
```

---

## 8. The Help Tool

### `context_help`

```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False

Input:
class HelpInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    layer: Optional[str] = Field(None, description="Filter to a specific layer: 'collaboration' | 'memory' | 'skills' | 'agent'. Omit for full index.")

Returns:  Structured tool index grouped by layer

Docstring:
  "Returns a structured index of all available tools, grouped by functional layer.
   Call this when connecting to the server for the first time, or when unsure
   which tool to use for a task. Each entry includes the tool name and a one-line
   description of its purpose."

Behavior:
  - Return static grouped index — no DB query needed
  - Groups: Collaboration (projects/threads/entries), Memory, Skills, Agent Collaboration, Meta
  - Per tool: name, one-line purpose
  - If layer filter provided, return only that group
  - Also include: recommended session start sequence at bottom of response
```

Recommended session start sequence to include in help output:
```
## Recommended Session Start Sequence
1. context_session_start     — get full briefing in one call
2. context_skill_list_global — load project standards (if not using session_start)
3. context_memory_get_short  — check your working state
4. context_list_threads      — see open work items
```

---

## 9. Implementation Order

```
Step 1: db.py
  - Add init_db_v2(conn) function with all new tables and FTS5 triggers
  - Add all new query helper functions for each new table
  - Call init_db_v2(conn) from server.py lifespan after init_db(conn)

Step 2: models.py
  - Add all new enums: MemoryScope, Confidence, SkillType, AgentStatus, MessagePriority
  - Add all new Pydantic input models in order:
    Memory models → Skill models → Collaboration models → Help model

Step 3: tools.py — Memory tools (implement in this order)
  a. context_memory_set_short
  b. context_memory_get_short
  c. context_memory_clear_short
  d. context_memory_set_long
  e. context_memory_get_long
  f. context_memory_delete_long
  g. context_memory_search      (FTS5 — add MemorySearchInput to models.py first)
  h. context_memory_promote

Step 4: tools.py — Skills tools
  a. context_skill_create_personal
  b. context_skill_get_personal
  c. context_skill_list_personal
  d. context_skill_update_personal
  e. context_skill_delete_personal
  f. context_skill_create_global
  g. context_skill_get_global    (implement resolution order carefully)
  h. context_skill_list_global
  i. context_skill_update_global
  j. context_skill_delete_global
  k. context_skill_search        (FTS5 union across two tables)

Step 5: tools.py — Collaboration tools
  a. context_message_send
  b. context_message_inbox
  c. context_message_read
  d. context_presence_update
  e. context_presence_get
  f. context_handoff_post
  g. context_handoff_get
  h. context_handoff_acknowledge
  i. context_session_start       (implement last — depends on all others)

Step 6: tools.py — Meta
  a. context_help                (static, no DB — implement last)
```

---

## 10. Testing Checklist

### Startup Verification
- [ ] Server starts without errors after upgrade
- [ ] All new tables exist in `shared_context.db`
- [ ] All 46 tools appear in MCP Inspector
- [ ] Existing 17 tools still pass original testing checklist

### Memory Tests
```
1. Set short-term memory: agent=claude-code, project=browser-extension, key=current_file, value=autofill.js
2. Get short-term memory: key=current_file — verify correct value returned
3. Get all short-term memory for agent+project — verify current_file present
4. Set long-term memory: project-scoped, key=shadow-dom-approach, value=use MutationObserver, confidence=high
5. Get long-term memory by key — verify returned
6. Promote current_file short-term → long-term with target_scope=agent_project, clear_after=true
7. Get short-term memory — verify current_file is gone
8. Get long-term memory — verify promoted entry exists
9. Search long-term memory for "MutationObserver" — verify result with snippet
10. Clear all short-term memory for agent+project — verify confirmation with count
```

### Skills Tests
```
1. Create personal skill: agent=claude-code, name=debug-content-script, type=procedure
2. Get personal skill by name — verify usage_count increments to 1
3. List personal skills — verify description returned, NOT full content
4. Create global skill: project=browser-extension, name=api-response-format, type=instruction
5. Get global skill by name with project_id — verify returned with scope='project'
6. Create truly global skill: no project_id, name=commit-message-format
7. Get global skill 'commit-message-format' without project_id — verify scope='global'
8. List global skills with project_id — verify BOTH project-scoped AND global skills appear
9. Update global skill — verify version increments from 1 to 2
10. Search skills with agent_id + project_id — verify results from both personal and global
```

### Collaboration Tests
```
1. Update presence: claude-code, project=browser-extension, status=working, task=fixing autofill
2. Get presence — verify claude-code shows as working
3. Send message: from=claude-code, to=gemini, subject=Heads up, priority=high
4. Check gemini inbox — verify unread message appears
5. Read message — verify is_read=1 and full content returned
6. Post handoff: from=claude-code, project=browser-extension, summary=fixed autofill, next_steps=test on Firefox
7. Get handoffs for project — verify unacknowledged handoff appears
8. Acknowledge handoff as gemini — verify acknowledged_by set
9. Get handoffs again — verify acknowledged marker updated
10. Call context_session_start as gemini — verify consolidated briefing with all sections
```

### Help Tool Test
```
1. Call context_help with no filter — verify all 46 tools listed in groups
2. Call context_help with layer='memory' — verify only memory tools listed
```

---

## 11. Full Tool Index

| # | Tool | Layer | Read/Write |
|---|---|---|---|
| 1 | `context_create_project` | Collaboration | Write |
| 2 | `context_list_projects` | Collaboration | Read |
| 3 | `context_get_project` | Collaboration | Read |
| 4 | `context_archive_project` | Collaboration | Write |
| 5 | `context_register_agent` | Collaboration | Write |
| 6 | `context_list_agents` | Collaboration | Read |
| 7 | `context_get_agent` | Collaboration | Read |
| 8 | `context_create_thread` | Collaboration | Write |
| 9 | `context_list_threads` | Collaboration | Read |
| 10 | `context_get_thread` | Collaboration | Read |
| 11 | `context_resolve_thread` | Collaboration | Write |
| 12 | `context_export_thread` | Collaboration | Read |
| 13 | `context_post_entry` | Collaboration | Write |
| 14 | `context_update_entry` | Collaboration | Write |
| 15 | `context_pin_entry` | Collaboration | Write |
| 16 | `context_search` | Collaboration | Read |
| 17 | `context_help` | Meta | Read |
| 18 | `context_memory_set_short` | Memory | Write |
| 19 | `context_memory_get_short` | Memory | Read |
| 20 | `context_memory_clear_short` | Memory | Write |
| 21 | `context_memory_set_long` | Memory | Write |
| 22 | `context_memory_get_long` | Memory | Read |
| 23 | `context_memory_delete_long` | Memory | Write |
| 24 | `context_memory_search` | Memory | Read |
| 25 | `context_memory_promote` | Memory | Write |
| 26 | `context_skill_create_personal` | Skills | Write |
| 27 | `context_skill_get_personal` | Skills | Read |
| 28 | `context_skill_list_personal` | Skills | Read |
| 29 | `context_skill_update_personal` | Skills | Write |
| 30 | `context_skill_delete_personal` | Skills | Write |
| 31 | `context_skill_create_global` | Skills | Write |
| 32 | `context_skill_get_global` | Skills | Read |
| 33 | `context_skill_list_global` | Skills | Read |
| 34 | `context_skill_update_global` | Skills | Write |
| 35 | `context_skill_delete_global` | Skills | Write |
| 36 | `context_skill_search` | Skills | Read |
| 37 | `context_message_send` | Agent Collab | Write |
| 38 | `context_message_inbox` | Agent Collab | Read |
| 39 | `context_message_read` | Agent Collab | Write |
| 40 | `context_presence_update` | Agent Collab | Write |
| 41 | `context_presence_get` | Agent Collab | Read |
| 42 | `context_handoff_post` | Agent Collab | Write |
| 43 | `context_handoff_get` | Agent Collab | Read |
| 44 | `context_handoff_acknowledge` | Agent Collab | Write |
| 45 | `context_session_start` | Agent Collab | Read |
| 46 | `context_help` | Meta | Read |

**Total: 46 tools across 5 layers.**
