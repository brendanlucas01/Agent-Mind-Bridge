# Shared Context MCP Server — Architecture & Implementation Spec

> **This document is a complete implementation specification for Claude Code.**
> Read it fully before writing any code. Every design decision has been made.
> Your job is to implement exactly what is described here, verify it runs, and test it with MCP Inspector.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Database Schema](#4-database-schema)
5. [FTS5 Setup & Triggers](#5-fts5-setup--triggers)
6. [Data Models (Pydantic)](#6-data-models-pydantic)
7. [Tool Specifications](#7-tool-specifications)
8. [Response Format Design](#8-response-format-design)
9. [Server Initialization & Lifespan](#9-server-initialization--lifespan)
10. [Error Handling Strategy](#10-error-handling-strategy)
11. [Implementation Order](#11-implementation-order)
12. [Testing Checklist](#12-testing-checklist)
13. [Configuration](#13-configuration)

---

## 1. Project Overview

A **shared MCP server** that gives multiple AI agents (Claude Code, Gemini via Antigravity, or any MCP-compatible client) a **common persistent blackboard** to collaborate on software projects.

### Core Concept

Two or more AI agents connect to this server simultaneously. They read each other's proposals, post feedback, make decisions, and build shared context — all without bloating their individual context windows with `.md` files.

### Hierarchy

```
Project
 └── Thread (a topic or task within the project)
      └── Entry (a proposal, feedback, decision, or note)

Agent (any AI or human participant, registered once, used across all projects)
```

### Key Design Decisions (Do Not Change)

- **Tool-only** — No MCP Resources. All data access is via Tools for maximum client compatibility.
- **Streamable HTTP transport** — Required for multiple simultaneous clients. Not stdio.
- **SQLite with FTS5** — Single file DB, no external infrastructure needed.
- **FastMCP** — Use the `@mcp.tool` decorator pattern throughout.
- **All tools prefixed `context_`** — Prevents naming conflicts when used alongside other MCP servers.
- **Dual response format** — All read tools support `response_format: 'markdown' | 'json'`.
- **Pagination on all list tools** — `limit` + `offset` + `has_more` on every list/search tool.

---

## 2. Tech Stack

```
Python          3.10+
mcp[cli]        latest    — FastMCP framework
pydantic        v2        — Input validation
uvicorn         latest    — ASGI server (used by FastMCP's HTTP transport)
better-sqlite3  —         — DO NOT USE. Use Python stdlib sqlite3 instead.
```

### `requirements.txt`

```
mcp[cli]>=1.0.0
pydantic>=2.0.0
uvicorn>=0.30.0
```

### Installation

```bash
pip install -r requirements.txt
```

### Running the server

```bash
python server.py
# Server starts on http://127.0.0.1:3333/mcp
```

---

## 3. Project Structure

```
shared-mcp/
├── server.py        # FastMCP init, lifespan, transport config. No business logic.
├── db.py            # All SQLite operations. Schema init, all query functions.
├── tools.py         # All 17 tool handler functions. Imports from db.py.
├── models.py        # All Pydantic input models and enums.
├── requirements.txt
└── ARCHITECTURE.md  # This file.
```

**Strict separation rules:**
- `server.py` only imports from `tools.py` and `db.py`
- `tools.py` only imports from `db.py` and `models.py`
- `db.py` has zero imports from other local files
- `models.py` has zero imports from other local files

---

## 4. Database Schema

Create all tables in `db.py` inside an `init_db(conn)` function called during lifespan startup.

```sql
-- Projects: top-level containers for work
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'archived'
    created_at  TEXT NOT NULL,
    archived_at TEXT
);

-- Agents: registered AI or human participants
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    type        TEXT NOT NULL,   -- 'claude' | 'gemini' | 'openai' | 'human' | 'other'
    description TEXT,
    created_at  TEXT NOT NULL
);

-- Threads: topics or tasks within a project
CREATE TABLE IF NOT EXISTS threads (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',    -- 'open' | 'resolved'
    created_at  TEXT NOT NULL,
    resolved_at TEXT
);

-- Entries: individual contributions within a thread
CREATE TABLE IF NOT EXISTS entries (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES threads(id),
    agent_id    TEXT NOT NULL REFERENCES agents(id),
    type        TEXT NOT NULL,   -- 'proposal' | 'feedback' | 'decision' | 'note'
    content     TEXT NOT NULL,
    reply_to    TEXT REFERENCES entries(id),  -- nullable, for threaded replies
    pinned      INTEGER NOT NULL DEFAULT 0,   -- 0 | 1
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_threads_project ON threads(project_id);
CREATE INDEX IF NOT EXISTS idx_entries_thread ON entries(thread_id);
CREATE INDEX IF NOT EXISTS idx_entries_agent ON entries(agent_id);
CREATE INDEX IF NOT EXISTS idx_entries_pinned ON entries(thread_id, pinned);
```

### ID Generation

Use `uuid.uuid4()` for all IDs. Store as TEXT strings.

### Timestamps

Store all timestamps as ISO 8601 UTC strings: `datetime.utcnow().isoformat() + 'Z'`

---

## 5. FTS5 Setup & Triggers

Create FTS5 virtual tables and their sync triggers in `init_db()` immediately after the main tables.

```sql
-- FTS5 virtual tables
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    content,
    content='entries',
    content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS threads_fts USING fts5(
    title,
    content='threads',
    content_rowid='rowid'
);

-- Entry FTS triggers
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO entries_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;

-- Thread FTS triggers
CREATE TRIGGER IF NOT EXISTS threads_ai AFTER INSERT ON threads BEGIN
    INSERT INTO threads_fts(rowid, title) VALUES (new.rowid, new.title);
END;

CREATE TRIGGER IF NOT EXISTS threads_au AFTER UPDATE ON threads BEGIN
    INSERT INTO threads_fts(threads_fts, rowid, title) VALUES ('delete', old.rowid, old.title);
    INSERT INTO threads_fts(rowid, title) VALUES (new.rowid, new.title);
END;

CREATE TRIGGER IF NOT EXISTS threads_ad AFTER DELETE ON threads BEGIN
    INSERT INTO threads_fts(threads_fts, rowid, title) VALUES ('delete', old.rowid, old.title);
END;
```

### FTS5 Search Query Pattern

Always wrap FTS5 queries in try/except. If the query string is malformed, fall back to a LIKE search:

```python
def search_entries_fts(conn, query: str, project_id: str | None, thread_id: str | None, limit: int, offset: int) -> list[dict]:
    try:
        sql = """
            SELECT e.id, e.thread_id, e.agent_id, e.type, e.pinned, e.created_at,
                   t.title as thread_title, t.project_id,
                   a.name as agent_name,
                   snippet(entries_fts, 0, '**', '**', '...', 20) as snippet,
                   entries_fts.rank
            FROM entries_fts
            JOIN entries e ON entries_fts.rowid = e.rowid
            JOIN threads t ON e.thread_id = t.id
            JOIN agents a ON e.agent_id = a.id
            WHERE entries_fts MATCH ?
        """
        params = [query]
        if thread_id:
            sql += " AND e.thread_id = ?"
            params.append(thread_id)
        if project_id:
            sql += " AND t.project_id = ?"
            params.append(project_id)
        sql += " ORDER BY entries_fts.rank LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except Exception:
        # Fallback: plain LIKE search
        like = f"%{query}%"
        sql = """
            SELECT e.id, e.thread_id, e.agent_id, e.type, e.pinned, e.created_at,
                   t.title as thread_title, t.project_id,
                   a.name as agent_name,
                   e.content as snippet,
                   0 as rank
            FROM entries e
            JOIN threads t ON e.thread_id = t.id
            JOIN agents a ON e.agent_id = a.id
            WHERE e.content LIKE ?
        """
        params = [like]
        if thread_id:
            sql += " AND e.thread_id = ?"
            params.append(thread_id)
        if project_id:
            sql += " AND t.project_id = ?"
            params.append(project_id)
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
```

**Note on FTS5 rank:** The rank value is negative — closer to 0 means MORE relevant. When returning rank in responses, label it clearly or normalize it.

---

## 6. Data Models (Pydantic)

All models go in `models.py`. Use Pydantic v2 throughout.

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from enum import Enum


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class AgentType(str, Enum):
    CLAUDE = "claude"
    GEMINI = "gemini"
    OPENAI = "openai"
    HUMAN = "human"
    OTHER = "other"


class EntryType(str, Enum):
    PROPOSAL = "proposal"
    FEEDBACK = "feedback"
    DECISION = "decision"
    NOTE = "note"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ThreadStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class SearchIn(str, Enum):
    ENTRIES = "entries"
    THREADS = "threads"
    BOTH = "both"


# --- Project Models ---

class CreateProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(..., description="Unique project name (e.g. 'browser-extension', 'job-board')", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Optional project description", max_length=500)


class ListProjectsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Optional[ProjectStatus] = Field(None, description="Filter by status: 'active' or 'archived'. Omit for all.")
    limit: int = Field(default=20, ge=1, le=100, description="Max results to return")
    offset: int = Field(default=0, ge=0, description="Number of results to skip")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' for readable output, 'json' for structured data")


class GetProjectInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str = Field(..., description="Project UUID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ArchiveProjectInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str = Field(..., description="Project UUID to archive")


# --- Agent Models ---

class RegisterAgentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(..., description="Unique agent name (e.g. 'claude-code', 'gemini-antigravity')", min_length=1, max_length=100)
    type: AgentType = Field(..., description="Agent type: 'claude' | 'gemini' | 'openai' | 'human' | 'other'")
    description: Optional[str] = Field(None, description="Optional description of this agent's role", max_length=300)


class ListAgentsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetAgentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id: str = Field(..., description="Agent UUID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Thread Models ---

class CreateThreadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    project_id: str = Field(..., description="Project UUID this thread belongs to")
    title: str = Field(..., description="Thread title describing the topic or task", min_length=1, max_length=200)


class ListThreadsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: Optional[str] = Field(None, description="Filter by project UUID. Omit for all projects.")
    status: Optional[ThreadStatus] = Field(None, description="Filter by 'open' or 'resolved'. Omit for all.")
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetThreadInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    thread_id: str = Field(..., description="Thread UUID")
    limit: int = Field(default=20, ge=1, le=100, description="Max entries to return")
    offset: int = Field(default=0, ge=0, description="Entries to skip (for pagination)")
    agent_id: Optional[str] = Field(None, description="Filter entries to this agent only")
    entry_type: Optional[EntryType] = Field(None, description="Filter by entry type: proposal | feedback | decision | note")
    pinned_only: bool = Field(default=False, description="If true, return only pinned/starred entries")
    order: str = Field(default="asc", pattern="^(asc|desc)$", description="'asc' for chronological, 'desc' for newest first")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ResolveThreadInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    thread_id: str = Field(..., description="Thread UUID to mark as resolved")


class ExportThreadInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    thread_id: str = Field(..., description="Thread UUID to export as a markdown document")


# --- Entry Models ---

class PostEntryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    thread_id: str = Field(..., description="Thread UUID to post into")
    agent_id: str = Field(..., description="Agent UUID of the author")
    type: EntryType = Field(..., description="Entry type: 'proposal' | 'feedback' | 'decision' | 'note'")
    content: str = Field(..., description="The entry content (markdown supported)", min_length=1, max_length=50000)
    reply_to: Optional[str] = Field(None, description="Optional entry UUID this is a reply to")


class UpdateEntryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    entry_id: str = Field(..., description="Entry UUID to update")
    content: str = Field(..., description="New content to replace the existing content", min_length=1, max_length=50000)


class PinEntryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    entry_id: str = Field(..., description="Entry UUID to pin or unpin")
    pinned: bool = Field(..., description="True to pin/star, False to unpin")


class GetEntryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    entry_id: str = Field(..., description="Entry UUID to retrieve")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Search Models ---

class SearchContextInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    query: str = Field(..., description="Search query. Supports FTS5 syntax: phrases in quotes, prefix with *, AND/OR/NOT operators.", min_length=1, max_length=500)
    project_id: Optional[str] = Field(None, description="Scope search to a specific project UUID")
    thread_id: Optional[str] = Field(None, description="Scope search to a specific thread UUID")
    search_in: SearchIn = Field(default=SearchIn.BOTH, description="'entries' | 'threads' | 'both'")
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)
```

---

## 7. Tool Specifications

All 17 tools. Implement each in `tools.py` as an async function registered via `@mcp.tool`. Import the `mcp` instance from `server.py` or pass it in — use whichever pattern FastMCP recommends for multi-file setups.

---

### 7.1 Project Tools

#### `context_create_project`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        CreateProjectInput
Returns:      JSON always — the created project object
Behavior:
  - Generate uuid4 for id
  - Set created_at to UTC now
  - Set status = 'active'
  - INSERT into projects
  - Return full project dict as JSON
Error cases:
  - If name already exists: return clear error "A project named '{name}' already exists. Use context_list_projects to see existing projects."
```

#### `context_list_projects`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        ListProjectsInput
Returns:      Paginated list of projects
Behavior:
  - Query projects with optional status filter
  - Apply limit/offset
  - Return with pagination metadata (total, count, offset, has_more, next_offset)
```

#### `context_get_project`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        GetProjectInput
Returns:      Single project with thread summary
Behavior:
  - Fetch project by id
  - Include: total thread count, open thread count, resolved thread count
  - Error if not found: "Project '{project_id}' not found. Use context_list_projects to find valid IDs."
```

#### `context_archive_project`
```
Annotations:  readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
Input:        ArchiveProjectInput
Returns:      Confirmation message
Behavior:
  - Set status='archived', archived_at=now
  - Idempotent: if already archived, return success with note "Project was already archived."
  - Does NOT delete any data
```

---

### 7.2 Agent Tools

#### `context_register_agent`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        RegisterAgentInput
Returns:      JSON — the created agent object
Behavior:
  - Generate uuid4 for id
  - Set created_at to UTC now
  - INSERT into agents
  - Error if name already exists: "An agent named '{name}' already exists. Use context_list_agents to find its ID."
```

#### `context_list_agents`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        ListAgentsInput
Returns:      All registered agents
Behavior:
  - No pagination needed (agent count stays small)
  - Include for each agent: id, name, type, description, created_at
```

#### `context_get_agent`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        GetAgentInput
Returns:      Single agent with activity summary
Behavior:
  - Fetch agent by id
  - Include: total entries posted, entries by type breakdown, projects participated in
  - Error if not found: "Agent '{agent_id}' not found. Use context_list_agents to find valid IDs."
```

---

### 7.3 Thread Tools

#### `context_create_thread`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        CreateThreadInput
Returns:      JSON — the created thread object
Behavior:
  - Validate project exists first. Error: "Project '{project_id}' not found."
  - Generate uuid4 for id
  - Set created_at to UTC now, status='open'
  - INSERT into threads
  - Return full thread dict as JSON
```

#### `context_list_threads`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        ListThreadsInput
Returns:      Paginated thread list
Behavior:
  - Optional filters: project_id, status
  - Include for each thread: id, title, project_id, project_name, status, created_at, entry_count
  - Apply limit/offset, return pagination metadata
```

#### `context_get_thread`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        GetThreadInput
Returns:      Thread metadata + filtered/paginated entries

CRITICAL — This is the primary reading tool. Design its response carefully:

Thread metadata block (always returned, never filtered):
  - id, title, status, project_id, project_name, created_at, resolved_at
  - total_entries (count of ALL entries, ignoring current filters)
  - pinned_count (total pinned entries in this thread)

Entries block (filtered + paginated):
  - Apply agent_id, entry_type, pinned_only filters
  - Apply order (asc/desc by created_at)
  - Apply limit/offset
  - For each entry: id, agent_id, agent_name, type, content, reply_to, pinned, created_at, updated_at
  - Include pagination: returned_count, offset, has_more, next_offset

Docstring must include this warning:
  "Use this tool to read thread contents during active collaboration.
   For archiving a completed thread as a standalone document, use context_export_thread instead.
   Use pinned_only=true to quickly surface key decisions without reading the full thread."
```

#### `context_resolve_thread`
```
Annotations:  readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
Input:        ResolveThreadInput
Returns:      Confirmation with thread summary
Behavior:
  - Set status='resolved', resolved_at=now
  - Idempotent: if already resolved, return success with note
  - Include in response: thread title, entry count, resolved_at timestamp
```

#### `context_export_thread`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        ExportThreadInput
Returns:      ALWAYS markdown. No response_format param on this tool.

CRITICAL — This is archival export only. Always returns complete thread, no filters, no pagination.

Docstring must include:
  "Generates a complete markdown document of an entire thread for archiving, sharing with humans,
   or saving outside the server. Always returns ALL entries. Do NOT use this to read context
   during active collaboration — use context_get_thread instead, which supports filtering
   and pagination to keep your context window lean."

Markdown format:
---
# {thread_title}

**Project:** {project_name}
**Status:** {status}
**Created:** {created_at}
**Resolved:** {resolved_at or 'Open'}
**Participants:** {comma-separated agent names}
**Total Entries:** {count}

---

## [{entry_type}] {agent_name} — {created_at}
{⭐ *pinned* if pinned}
{↩ *reply to {reply_to_id}* if reply_to is set}

{content}

---
(repeat for each entry in chronological order)
```

---

### 7.4 Entry Tools

#### `context_post_entry`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        PostEntryInput
Returns:      JSON — the created entry object
Behavior:
  - Validate thread exists. Error: "Thread '{thread_id}' not found."
  - Validate agent exists. Error: "Agent '{agent_id}' not found. Register with context_register_agent first."
  - Validate thread is open. Error: "Thread '{thread_id}' is resolved and no longer accepting entries."
  - If reply_to set, validate that entry exists in same thread.
  - Generate uuid4, set created_at = updated_at = now
  - INSERT into entries
  - Return full entry dict as JSON
```

#### `context_update_entry`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        UpdateEntryInput
Returns:      JSON — the updated entry object
Behavior:
  - Fetch entry by id. Error if not found.
  - Update content, set updated_at = now
  - FTS5 triggers handle index update automatically
  - Return full updated entry dict
```

#### `context_pin_entry`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        PinEntryInput
Returns:      Confirmation message
Behavior:
  - Fetch entry by id. Error if not found.
  - Set pinned = 1 if pinned=True, 0 if pinned=False
  - Idempotent: pinning already-pinned entry is fine
  - Return: "Entry {entry_id} has been {'pinned ⭐' if pinned else 'unpinned'}."
```

#### `context_get_entry`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        GetEntryInput
Returns:      Full entry object — all fields

Docstring must include:
  "Retrieve a single entry by its UUID. Use this to read the full content of a specific
   entry after identifying its ID from context_search results, or to resolve the parent
   entry in a reply_to chain without loading the entire thread.
   For browsing entries in a thread, use context_get_thread instead."

Behavior:
  - Fetch entry by id. Error if not found:
    "Entry '{entry_id}' not found. Use context_search to find valid entry IDs,
     or context_get_thread to browse entries within a thread."
  - JOIN to resolve agent_name and thread_title and project_id for full context
  - Return all fields:
      id, thread_id, thread_title, project_id, agent_id, agent_name,
      type, content, reply_to, pinned, created_at, updated_at
  - If reply_to is set, also include reply_to_snippet:
      the first 100 chars of the parent entry's content, so the AI has
      immediate context without a second round trip
```

---

### 7.5 Search Tool

#### `context_search`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SearchContextInput
Returns:      Lean result list — snippets only, no full content

CRITICAL — Returns snippets, not full entry content.
The AI should follow up with context_get_thread to read full content after identifying the thread.

Docstring must include:
  "Searches across entry content and/or thread titles using full-text search.
   Returns lightweight results with snippets only — no full content.
   After a search: use context_get_entry to read the full content of a specific entry,
   or use context_get_thread to browse all entries in a thread.
   Supports FTS5 query syntax: phrase search with quotes, prefix with *, AND/OR/NOT operators.
   Falls back to LIKE search automatically if query syntax is invalid."

Result format per item:
  type:          'entry' | 'thread'
  id:            entry or thread UUID
  thread_id:     UUID (always present)
  thread_title:  string
  project_id:    UUID
  project_name:  string
  agent_name:    string (for entries) | null (for threads)
  entry_type:    string (for entries) | null (for threads)
  snippet:       matched excerpt with **bold** highlights
  relevance:     normalized string 'high' | 'medium' | 'low' (derived from FTS5 rank)

Pagination metadata: total_results, returned, offset, has_more, next_offset

Note on relevance normalization:
  FTS5 rank is negative (closer to 0 = more relevant).
  Normalize: rank > -0.5 = 'high', > -1.5 = 'medium', else 'low'
```

---

## 8. Response Format Design

### Markdown Format — Rules

- Use `##` for entity titles
- Use `**label:**` for metadata fields
- Format timestamps as `YYYY-MM-DD HH:MM UTC`
- Show IDs in parentheses after names: `claude-code (abc-123-...)`
- Use `⭐` for pinned entries
- Use `↩` for reply indicators
- Include pagination footer: `*Showing {offset+1}–{offset+count} of {total}*`

### JSON Format — Rules

- Return raw dict/list, serialized with `json.dumps(result, indent=2)`
- Include all fields including IDs and timestamps
- Always include pagination metadata at top level

### Pagination Metadata (both formats)

Every list/search response must include:
```json
{
  "total": 47,
  "returned": 20,
  "offset": 0,
  "has_more": true,
  "next_offset": 20
}
```

---

## 9. Server Initialization & Lifespan

In `server.py`:

```python
import sqlite3
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from db import init_db

DB_PATH = "shared_context.db"

@asynccontextmanager
async def lifespan(server):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Better concurrent read performance
    conn.execute("PRAGMA foreign_keys=ON")     # Enforce FK constraints
    init_db(conn)
    yield {"db": conn}
    conn.close()

mcp = FastMCP("context_mcp", lifespan=lifespan)

# Import tools to register them (side-effect import)
import tools  # noqa: F401, E402

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=3333)
```

### Accessing DB in Tools

```python
# In tools.py
from mcp.server.fastmcp import FastMCP, Context
from server import mcp

@mcp.tool(name="context_create_project", annotations={...})
async def context_create_project(params: CreateProjectInput, ctx: Context) -> str:
    conn = ctx.request_context.lifespan_state["db"]
    # use conn for all queries
```

### WAL Mode

`PRAGMA journal_mode=WAL` is critical. It allows multiple readers + one writer simultaneously, which is exactly our use case (Claude Code and Gemini reading while one posts).

---

## 10. Error Handling Strategy

### Rule 1: Never raise exceptions to the client

Catch all exceptions in each tool and return a string error message. Never let an unhandled exception propagate.

### Rule 2: Error messages must be actionable

Every error must tell the AI what to do next:

```python
# Bad
return "Error: not found"

# Good
return f"Error: Thread '{thread_id}' not found. Use context_list_threads to find valid thread IDs."
```

### Rule 3: Validation order

Always validate in this order inside each tool:
1. Existence checks (does the referenced entity exist?)
2. State checks (is the thread open? is the project active?)
3. Business logic

### Rule 4: FTS5 fallback

Always wrap FTS5 queries in try/except with LIKE fallback. Never surface FTS5 parse errors to the client.

### Standard error format

```python
def error(message: str) -> str:
    return f"Error: {message}"
```

---

## 11. Implementation Order

Follow this order to avoid circular dependency issues and enable incremental testing:

```
1. models.py          — All Pydantic models and enums. No dependencies.
2. db.py              — Schema init, all query functions. No local dependencies.
3. server.py          — FastMCP init, lifespan, transport. Imports db.py.
4. tools.py           — All tool handlers. Imports server.py, db.py, models.py.

Within tools.py, implement in this order:
  a. context_register_agent      (needed by all entry tools)
  b. context_list_agents
  c. context_get_agent
  d. context_create_project      (needed by thread tools)
  e. context_list_projects
  f. context_get_project
  g. context_archive_project
  h. context_create_thread       (needed by entry tools)
  i. context_list_threads
  j. context_get_thread          (most complex read tool)
  k. context_resolve_thread
  l. context_post_entry          (core write tool)
  m. context_update_entry
  n. context_pin_entry
  o. context_get_entry           (reads single entry + resolves reply_to snippet)
  p. context_export_thread       (reads everything)
  q. context_search              (FTS5 — most complex)
```

---

## 12. Testing Checklist

After implementation, verify all of the following before marking complete:

### Startup

- [ ] `python server.py` starts without errors
- [ ] `shared_context.db` is created automatically
- [ ] Server listens on `http://127.0.0.1:3333/mcp`

### MCP Inspector

Run: `npx @modelcontextprotocol/inspector http://127.0.0.1:3333/mcp`

- [ ] All 17 tools appear in the inspector
- [ ] Each tool shows correct input schema
- [ ] Each tool shows correct annotations

### Functional Tests (run in MCP Inspector)

```
1. Register two agents: 'claude-code' (type=claude) and 'gemini' (type=gemini)
2. Create a project: 'browser-extension'
3. Create a thread in the project: 'Autofill logic for LinkedIn'
4. Post a proposal from claude-code
5. Post feedback from gemini (reply_to the proposal entry)
6. Pin the proposal entry
7. Call context_get_thread — verify metadata shows total_entries=2, pinned_count=1
8. Call context_get_thread with pinned_only=True — verify only 1 entry returned
9. Call context_get_thread with agent_id=gemini — verify only gemini's entry returned
10. Call context_search with query="autofill" — verify snippet returned, no full content
11. Call context_get_entry with the entry_id from search result — verify full content returned
12. Post a reply entry (reply_to set) — call context_get_entry and verify reply_to_snippet present
13. Call context_export_thread — verify complete markdown document returned
14. Call context_resolve_thread — verify status changes to 'resolved'
15. Attempt context_post_entry on resolved thread — verify error message returned
16. Call context_archive_project — verify status changes to 'archived'
17. Create second project, second thread — verify context_search scopes correctly with project_id
```

### Concurrency Test

Open two terminal tabs. Run simultaneous reads (context_get_thread) and a write (context_post_entry) and verify no locking errors. WAL mode should handle this cleanly.

---

## 13. Configuration

All configuration via constants at the top of `server.py`:

```python
DB_PATH    = "shared_context.db"   # SQLite file path
HOST       = "127.0.0.1"           # Bind address — do not change to 0.0.0.0 for local use
PORT       = 3333                   # HTTP port
```

### MCP Client Configuration

**Claude Code** (`.claude/mcp.json` or via `claude mcp add`):
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

**Antigravity / Gemini:**
Point to the same URL: `http://127.0.0.1:3333/mcp`

Both clients connect simultaneously. The server handles concurrent access via SQLite WAL mode.

---

## Appendix: Tool Summary Table

| Tool | Read/Write | Destructive | Idempotent | Paginated |
|---|---|---|---|---|
| `context_create_project` | Write | No | No | — |
| `context_list_projects` | Read | No | Yes | Yes |
| `context_get_project` | Read | No | Yes | — |
| `context_archive_project` | Write | Yes | Yes | — |
| `context_register_agent` | Write | No | No | — |
| `context_list_agents` | Read | No | Yes | — |
| `context_get_agent` | Read | No | Yes | — |
| `context_create_thread` | Write | No | No | — |
| `context_list_threads` | Read | No | Yes | Yes |
| `context_get_thread` | Read | No | Yes | Yes |
| `context_resolve_thread` | Write | Yes | Yes | — |
| `context_export_thread` | Read | No | Yes | — |
| `context_post_entry` | Write | No | No | — |
| `context_update_entry` | Write | No | No | — |
| `context_pin_entry` | Write | No | Yes | — |
| `context_get_entry` | Read | No | Yes | — |
| `context_search` | Read | No | Yes | Yes |

**Total: 17 tools**
