# Agent Mind Bridge — Upgrade v4 Spec
## Task Dependencies + Sprint Retrospective + Web Dashboard

> **This document is a complete upgrade specification for Claude Code.**
>
> **Prerequisites:**
> - Base server (ARCHITECTURE.md) fully implemented and passing all tests.
> - v2 upgrade (UPGRADE_V2.md) fully implemented — 46 tools working.
> - v3 upgrade (UPGRADE_V3.md) fully implemented — 56 tools working, sprint board live.
> - Do not modify any existing tables, tools, or files unless explicitly instructed here.
>
> **What this upgrade adds:**
> - Task Dependencies — junction table, 2 new tools, sprint board updated
> - Sprint Retrospective — `context_sprint_close` tool
> - Web Dashboard — FastAPI REST layer (port 8000) + Next.js UI
> - `start.sh` — single command to launch everything
>
> **Design decisions source:** All decisions in this document were finalized by Brendan
> with unanimous agent input via thread `cd1e4ae7-76fa-4a7b-be3d-e2e7c61cc02c`
> (v4 Dashboard — Features & REST API Brainstorm).

---

## Table of Contents

1. [v4 Overview](#1-v4-overview)
2. [Part A — Task Dependencies](#2-part-a--task-dependencies)
3. [Part B — Sprint Retrospective](#3-part-b--sprint-retrospective)
4. [Part C — Web Dashboard](#4-part-c--web-dashboard)
5. [Part D — Startup Script](#5-part-d--startup-script)
6. [Implementation Order](#6-implementation-order)
7. [Testing Checklist](#7-testing-checklist)
8. [Full Tool Index](#8-full-tool-index)

---

## 1. v4 Overview

### What's Being Built

Three independent features that compose into one coherent release:

```
Feature A: Task Dependencies
  → tasks can block each other
  → sprint board shows dependency chains
  → 2 new tools: context_task_add_dependency, context_task_remove_dependency
  → 1 modified tool: context_sprint_board (shows chains)

Feature B: Sprint Retrospective
  → 1 new tool: context_sprint_close
  → generates structured summary, marks sprint completed, posts handoff

Feature C: Web Dashboard
  → FastAPI REST server (port 8000) — 12 read-only endpoints
  → Next.js UI — 5 panels, polling every 30 seconds
  → start.sh — single command launches MCP server + REST API
```

### What's NOT in v4

- No write operations from the dashboard (v5)
- No auth (v5)
- No WebSocket real-time (v5)
- No mobile optimisation (v5)
- No orchestrator / push system (research track — separate thread)

### Design Brief — "Windows 7"

Brendan's exact brief: **"Not Windows 95, not Windows Vista — Windows 7."**

Translate this as:
- Clean, functional, purposeful polish
- Good typography, consistent spacing, clear visual hierarchy
- Subtle color coding (green / grey / red for agent status)
- One or two tasteful accents (soft card shadow, clean sidebar border)
- NO glassmorphism, parallax, or heavy animations
- NO pure utility grey with zero personality
- Fast to load, fast to scan, immediately readable

---

## 2. Part A — Task Dependencies

### 2.1 New Database Table

Add inside a new `init_db_v4(conn)` function in `db.py`:

```sql
-- Task dependencies: directed graph of blocking relationships
-- task_id CANNOT move to 'in_progress' while depends_on task is not 'done'
CREATE TABLE IF NOT EXISTS task_dependencies (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on  TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    created_by  TEXT NOT NULL REFERENCES agents(id),
    created_at  TEXT NOT NULL,
    UNIQUE(task_id, depends_on)     -- no duplicate dependency pairs
);

CREATE INDEX IF NOT EXISTS idx_deps_task    ON task_dependencies(task_id);
CREATE INDEX IF NOT EXISTS idx_deps_on      ON task_dependencies(depends_on);
```

### 2.2 Circular Dependency Prevention

Before inserting any dependency, check for cycles in application code:

```python
def would_create_cycle(conn, task_id: str, depends_on: str) -> bool:
    """
    Walk the dependency graph upward from depends_on.
    If task_id is reachable, inserting this dependency would create a cycle.
    Uses iterative BFS — never recurse in SQLite callbacks.
    """
    visited = set()
    queue = [depends_on]
    while queue:
        current = queue.pop(0)
        if current == task_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        rows = conn.execute(
            "SELECT depends_on FROM task_dependencies WHERE task_id = ?",
            (current,)
        ).fetchall()
        queue.extend(r[0] for r in rows)
    return False
```

### 2.3 New Pydantic Models

Add to `models.py`:

```python
class TaskAddDependencyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id:    str = Field(..., description="Task UUID that will be blocked")
    depends_on: str = Field(..., description="Task UUID that must be done first")
    created_by: str = Field(..., description="Agent UUID adding this dependency")

class TaskRemoveDependencyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id:    str = Field(..., description="Task UUID")
    depends_on: str = Field(..., description="Task UUID to remove as dependency")
```

### 2.4 Tool Specifications

#### `context_task_add_dependency`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        TaskAddDependencyInput
Returns:      Confirmation string

Docstring:
  "Add a dependency between two tasks. task_id will be blocked by depends_on —
   meaning task_id cannot move to 'in_progress' while depends_on is not 'done'.
   Circular dependencies are rejected automatically.
   Idempotent: adding an existing dependency returns success silently."

Behavior:
  - Validate both tasks exist and belong to the same project.
    Error: "Both tasks must belong to the same project."
  - Check for cycles via would_create_cycle(). 
    Error: "Cannot add dependency: would create a circular dependency chain."
  - UNIQUE constraint handles idempotency — catch IntegrityError, return success.
  - INSERT into task_dependencies.
  - Return: "Task '{task_title}' now depends on '{depends_on_title}'."
```

#### `context_task_remove_dependency`
```
Annotations:  readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
Input:        TaskRemoveDependencyInput
Returns:      Confirmation string

Behavior:
  - DELETE WHERE task_id = ? AND depends_on = ?
  - Idempotent: if not found, return "Dependency not found — nothing removed."
  - Return: "Dependency removed. Task '{task_title}' no longer depends on '{depends_on_title}'."
```

### 2.5 Modification to `context_task_update`

When an agent tries to move a task to `in_progress`, validate dependencies:

```python
if new_status == 'in_progress':
    blocking = conn.execute("""
        SELECT t.id, t.title, t.status
        FROM task_dependencies td
        JOIN tasks t ON td.depends_on = t.id
        WHERE td.task_id = ? AND t.status != 'done'
    """, (task_id,)).fetchall()
    
    if blocking:
        titles = ', '.join(f"'{r['title']}' ({r['status']})" for r in blocking)
        return error(
            f"Cannot move to in_progress: blocked by {len(blocking)} unfinished "
            f"task(s): {titles}. Complete those first or remove the dependencies."
        )
```

### 2.6 Modification to `context_sprint_board`

Add a dependency chain indicator to task cards in the board output:

```markdown
## IN PROGRESS (1)
- [HIGH] Fix shadow DOM detection — claude-code
  Blocks: "Test LinkedIn autofill" [BLOCKED]

## BLOCKED (1)
- [HIGH] Test LinkedIn autofill — gemini-pro
  Waiting on: "Fix shadow DOM detection" [IN PROGRESS]
```

For each task:
- If it has unfinished dependencies: show `Waiting on: "{title}" [{status}]`
- If other tasks depend on it: show `Blocks: "{title}" [{status}]`

---

## 3. Part B — Sprint Retrospective

### 3.1 New Pydantic Model

Add to `models.py`:

```python
class SprintCloseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sprint_id:  str = Field(..., description="Sprint UUID to close")
    closed_by:  str = Field(..., description="Agent UUID closing the sprint")
    notes:      Optional[str] = Field(
        None,
        description="Optional human or agent notes to include in the retrospective",
        max_length=2000
    )
```

### 3.2 Tool Specification

#### `context_sprint_close`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SprintCloseInput
Returns:      Markdown retrospective document

Docstring:
  "Close a sprint and automatically generate a structured retrospective.
   Computes what shipped, what carried over, what got blocked and why,
   which agents participated, and how long the sprint ran.
   Posts the retrospective as a pinned 'decision' entry in a new dedicated thread.
   Sets sprint status to 'completed'.
   Also posts a handoff note so the next session picks up with full context.
   Idempotent: if sprint is already completed, returns the existing retrospective."

Behavior:
  1. Fetch sprint. Error if not found.
  2. If already completed: return "Sprint already closed." with existing retro link.
  3. Gather data:
     - All tasks in sprint, grouped by final status
     - Carried-over tasks: status != 'done'
     - Blocked tasks: status = 'blocked' with blocked_reason
     - Participating agents: distinct agent_ids from task assignments + entries
     - Duration: start_date to today (or created_at to today if no start_date)
     - Linked threads: all thread_ids referenced by tasks in the sprint
  4. Generate retrospective markdown (see format below).
  5. Create new thread: "{sprint_name} — Retrospective"
  6. Post retrospective as 'decision' entry, pinned.
  7. UPDATE sprint status = 'completed', updated_at = now.
  8. Call handoff logic: post handoff with summary = first 500 chars of retro,
     next_steps = carried-over task titles, thread_refs = [retro thread id].
  9. Return full retrospective markdown.

Retrospective format:
---
# Sprint Retrospective: {sprint_name}

**Project:** {project_name}
**Closed by:** {agent_name}
**Duration:** {start_date} to {close_date} ({n} days)
**Goal:** {goal or 'No goal set'}

---

## What Shipped ({done_count} tasks)
- {task_title} — {assigned_agent}
- ...

## Carried Over ({carried_count} tasks)
- {task_title} [{status}] — {assigned_agent or 'unassigned'}
- ...

## Blocked at Close ({blocked_count} tasks)
- {task_title} — {assigned_agent}
  Reason: {blocked_reason}
- ...

## Participants
{comma-separated agent names who contributed}

## Notes
{notes if provided, else 'No additional notes.'}

---
*Retrospective generated {timestamp} UTC by {closed_by_agent_name}*
```

---

## 4. Part C — Web Dashboard

The dashboard is two separate components:
1. **FastAPI REST server** — Python, reads SQLite, runs on port 8000
2. **Next.js UI** — TypeScript, reads from REST API, runs on port 3000

### 4.1 Project Structure

```
agent-mind-bridge/
├── server.py          (existing MCP server — untouched)
├── app.py             (existing FastMCP app — untouched)
├── db.py              (existing — add init_db_v4)
├── tools.py           (existing — add new tools)
├── models.py          (existing — add new models)
├── api.py             (NEW — FastAPI REST server)
├── start.sh           (NEW — single startup script)
├── dashboard/         (NEW — Next.js app)
│   ├── package.json
│   ├── postcss.config.mjs
│   ├── next.config.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx        (main dashboard)
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── AgentPresenceBar.tsx
│   │   │   ├── SprintBoard.tsx
│   │   │   ├── TaskCard.tsx
│   │   │   ├── HandoffPanel.tsx
│   │   │   ├── ActivityStream.tsx
│   │   │   ├── SkillsPanel.tsx
│   │   │   ├── ProjectSwitcher.tsx
│   │   │   └── ThreadDrawer.tsx
│   │   ├── hooks/
│   │   │   └── useProject.ts
│   │   └── lib/
│   │       └── api.ts          (typed API client)
│   └── ...
└── requirements.txt   (add: fastapi, uvicorn)
```

---

### 4.2 FastAPI REST Server (`api.py`)

#### Setup

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "shared_context.db")

app = FastAPI(title="Agent Mind Bridge Dashboard API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```

#### The 12 Endpoints

All endpoints are GET, read-only, return JSON. No authentication in v4.

---

**`GET /api/health`**
```python
Returns: { "status": "ok", "db": "connected", "timestamp": "..." }
Purpose: Dashboard uses this to show connection status indicator.
```

---

**`GET /api/projects`**
```python
Returns: [
  {
    "id": "...",
    "name": "shared-context",
    "description": "...",
    "status": "active",
    "thread_count": 8,
    "agent_count": 4,
    "active_sprint": { "id": "...", "name": "Sprint 1" } | null,
    "created_at": "..."
  }
]
Purpose: Project Switcher dropdown.
```

---

**`GET /api/projects/{project_id}`**
```python
Returns: Single project with full stats:
  open_thread_count, resolved_thread_count,
  active_sprint (name, task counts by status),
  agent_count, created_at
Purpose: Project header stats.
```

---

**`GET /api/agents`**
```python
Returns: [
  {
    "id": "...",
    "name": "claude-code",
    "type": "claude",
    "status": "working",                 -- from agent_presence
    "current_task": "Fixing autofill",
    "project_name": "shared-context",
    "last_seen": "2026-03-29T07:00:00Z",
    "last_seen_human": "5 mins ago"
  }
]
Purpose: Agent Presence Bar — always visible at top.
Color mapping: working=green, idle=grey, blocked=red, reviewing=amber.
```

---

**`GET /api/projects/{project_id}/sprint`**
```python
Returns: Active sprint with board data pre-grouped by status column:
{
  "sprint": { "id", "name", "goal", "status", "start_date", "end_date" },
  "board": {
    "backlog":     [ task, ... ],
    "todo":        [ task, ... ],
    "in_progress": [ task, ... ],
    "blocked":     [ task, ... ],
    "review":      [ task, ... ],
    "done":        [ task, ... ]
  },
  "summary": { "total": 12, "done": 4, "blocked": 2, "in_progress": 3 }
}

Each task object:
{
  "id", "title", "status", "priority",
  "assigned_to_name", "blocked_reason",
  "depends_on": [ { "id", "title", "status" } ],
  "blocks":     [ { "id", "title", "status" } ]
}

Purpose: Sprint Board main panel. Data arrives pre-grouped — frontend just renders.
If no active sprint: returns { "sprint": null, "board": null }
```

---

**`GET /api/projects/{project_id}/sprints`**
```python
Returns: All sprints for the project, ordered newest first.
  { "id", "name", "status", "goal", "start_date", "end_date",
    "task_count", "done_count", "created_at" }
Purpose: Sprint history view (future use, available from v4).
```

---

**`GET /api/projects/{project_id}/threads`**
```python
Query params: limit (default 20), offset (default 0)
Returns: Recent threads with entry counts:
  { "id", "title", "status", "entry_count", "created_at",
    "last_entry_at", "last_entry_agent" }
Purpose: Thread list for Activity Stream context.
```

---

**`GET /api/threads/{thread_id}/entries`**
```python
Query params: limit (default 50), offset (default 0)
Returns: Thread metadata + paginated entries:
  {
    "thread": { "id", "title", "status", "project_name" },
    "entries": [
      { "id", "type", "content", "agent_name", "agent_type",
        "pinned", "reply_to", "created_at" }
    ],
    "total": 12, "has_more": false
  }
Purpose: Thread Drawer — loads when user clicks a thread in the Activity Stream.
```

---

**`GET /api/projects/{project_id}/activity`**
```python
Query params: limit (default 30)
Returns: Unified chronological feed of recent entries + messages:
[
  {
    "type": "entry",
    "agent_name": "claude-code",
    "agent_type": "claude",
    "action": "posted a decision",
    "thread_id": "...",
    "thread_title": "Fix LinkedIn autofill",
    "entry_id": "...",
    "content_preview": "First 80 chars of content...",
    "timestamp": "...",
    "timestamp_human": "5 mins ago"
  },
  {
    "type": "message",
    "from_agent": "gemini-pro",
    "to_agent": "claude-code | broadcast",
    "subject": "Heads up on shadow DOM",
    "priority": "high",
    "is_read": false,
    "timestamp": "...",
    "timestamp_human": "12 mins ago"
  }
]
Purpose: Activity Stream right sidebar.
High-priority unread messages: include "priority_flag": true for red dot treatment.
```

---

**`GET /api/projects/{project_id}/tasks`**
```python
Query params: status (optional filter), limit (default 20)
Returns: Filtered task list.
  Most useful as: GET /api/projects/{id}/tasks?status=blocked
  Returns blocked tasks with blocked_reason — fast-path for "what's stuck" view.
Purpose: Blocked tasks fast-path — loaded on every dashboard open.
```

---

**`GET /api/projects/{project_id}/handoffs`**
```python
Query params: limit (default 1)
Returns: Most recent handoff(s):
  { "id", "from_agent_name", "summary", "in_progress",
    "blockers", "next_steps", "thread_refs", "acknowledged_by_name",
    "created_at", "created_at_human" }
Purpose: Latest Handoff panel — top of right sidebar.
```

---

**`GET /api/projects/{project_id}/skills`**
```python
Returns: Global skills for this project (project-scoped + global):
  { "id", "name", "skill_type", "description", "version", "scope", "updated_at" }
  Description only — not full content. Keeps response lean.
Purpose: Global Skills panel — collapsed by default, shows active conventions.
```

---

### 4.3 Next.js Dashboard

#### Installation

```bash
cd dashboard
npm install
npm run dev    # port 3000
```

#### `package.json` dependencies

```json
{
  "dependencies": {
    "next": "15.x",
    "react": "19.x",
    "react-dom": "19.x",
    "swr": "^2.x"
  },
  "devDependencies": {
    "typescript": "^5.x",
    "@types/react": "^19.x",
    "tailwindcss": "latest",
    "@tailwindcss/postcss": "latest"
  }
}
```

#### `postcss.config.mjs`

```js
export default {
  plugins: ["@tailwindcss/postcss"]
};
```

#### `src/app/globals.css`

```css
@import "tailwindcss";

/* Custom CSS for premium touches — "Windows 7" aesthetic */
:root {
  --color-working: #22c55e;   /* green-500 */
  --color-idle: #6b7280;      /* gray-500 */
  --color-blocked: #ef4444;   /* red-500 */
  --color-reviewing: #f59e0b; /* amber-500 */
  --color-critical: #dc2626;  /* red-600 */
  --color-high: #f97316;      /* orange-500 */
  --color-medium: #3b82f6;    /* blue-500 */
  --color-low: #9ca3af;       /* gray-400 */
  --shadow-card: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08);
  --shadow-drawer: -4px 0 24px rgba(0,0,0,0.15);
}

/* Smooth status dot pulse for WORKING agents */
@keyframes pulse-working {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.status-working { animation: pulse-working 2s ease-in-out infinite; }
```

---

#### Dashboard Layout (`src/app/page.tsx`)

```
┌─────────────────────────────────────────────────────────────────────┐
│  TOPNAV: [Project Switcher ▾]    Agent Presence Bar                 │
│          shared-context   claude-code ● gemini-pro ○ architect ○    │
├─────────────────────────────────────────────────┬───────────────────┤
│                                                 │  Latest Handoff   │
│              SPRINT BOARD                       │  ─────────────    │
│                                                 │  Activity Stream  │
│  BACKLOG  TODO  IN PROGRESS  BLOCKED  REVIEW  DONE│                 │
│  ──────   ────  ───────────  ───────  ──────  ──── │  [entry]       │
│  [card]  [card]   [card]     [card]   [card] [card] │  [message 🔴] │
│  [card]           [card]     [card]          [card] │  [entry]       │
│                              reason                 │  ...           │
│                                                 │  ─────────────    │
│                                                 │  Global Skills    │
│                                                 │  (collapsed ▾)    │
└─────────────────────────────────────────────────┴───────────────────┘
```

---

#### Component Specifications

**`AgentPresenceBar`**
- Horizontal list of all agents
- Each agent: colored dot (status color) + name + current_task on hover tooltip
- WORKING dot pulses with CSS animation
- BLOCKED dot is red, no animation — should stand out
- Auto-refreshes via SWR every 30 seconds

**`ProjectSwitcher`**
- Dropdown in top-left
- Shows all active projects with active sprint name
- Selecting a project re-fetches all panels
- Persists selection in localStorage

**`SprintBoard`**
- Six columns: backlog / todo / in_progress / blocked / review / done
- Columns with zero tasks are HIDDEN (not shown as empty columns)
- BLOCKED column: red left-border, always rendered when it has tasks
- Each `TaskCard` shows: title, priority badge, assignee initial avatar, blocked_reason if blocked
- Dependency indicators: small chain icon on tasks with deps, tooltip shows chain
- No drag-and-drop in v4 — read only

**`TaskCard`**
```
┌─────────────────────────────┐
│ [CRIT] Fix shadow DOM       │
│ ⛓ Blocks: Test autofill    │
│ ● claude-code               │
└─────────────────────────────┘

┌─────────────────────────────┐
│ [HIGH] Test LinkedIn        │
│ ⚠ Waiting on: Fix shadow   │
│ Reason: waiting on fix      │
│ ● gemini-pro                │
└─────────────────────────────┘
```
Priority badges: CRIT=red, HIGH=orange, MED=blue, LOW=grey.

**`HandoffPanel`**
- Shows the most recent handoff
- Title: from_agent + time ago
- Summary text (truncated to 150 chars, expand on click)
- In Progress, Blockers, Next Steps as collapsible sections
- Unacknowledged handoffs have a yellow left border

**`ActivityStream`**
- Unified feed: entries + messages, newest first
- Entry items: agent avatar + name + action + thread title + time ago
- Message items: from → to + subject + priority icon + time ago
- High-priority unread messages: red dot indicator on left
- Thread items are clickable — opens `ThreadDrawer`
- Auto-refreshes every 30 seconds

**`ThreadDrawer`**
- Slides in from the right (CSS transform, not a new page)
- Shows thread title, status, entry count
- Full entry list in chronological order
- Entry types color-coded: proposal=blue, feedback=amber, decision=green, note=grey
- Pinned entries marked with ⭐
- Close button or click-outside dismisses

**`SkillsPanel`**
- Collapsed by default (shows count badge)
- Expand shows global skills: name, type badge, version
- One-line description only — no full content
- Sorted: project-scoped first, then global

---

#### `src/lib/api.ts` — Typed API Client

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchProjects() {
  const res = await fetch(`${API_BASE}/api/projects`);
  if (!res.ok) throw new Error('Failed to fetch projects');
  return res.json();
}

export async function fetchAgents() {
  const res = await fetch(`${API_BASE}/api/agents`);
  if (!res.ok) throw new Error('Failed to fetch agents');
  return res.json();
}

export async function fetchSprint(projectId: string) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/sprint`);
  if (!res.ok) throw new Error('Failed to fetch sprint');
  return res.json();
}

export async function fetchActivity(projectId: string) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/activity`);
  if (!res.ok) throw new Error('Failed to fetch activity');
  return res.json();
}

export async function fetchHandoff(projectId: string) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/handoffs?limit=1`);
  if (!res.ok) throw new Error('Failed to fetch handoff');
  return res.json();
}

export async function fetchThreadEntries(threadId: string) {
  const res = await fetch(`${API_BASE}/api/threads/${threadId}/entries`);
  if (!res.ok) throw new Error('Failed to fetch thread');
  return res.json();
}

export async function fetchSkills(projectId: string) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/skills`);
  if (!res.ok) throw new Error('Failed to fetch skills');
  return res.json();
}
```

---

#### SWR Polling Setup

```typescript
// In each component, use SWR with 30-second refresh:
import useSWR from 'swr';

const { data: agents } = useSWR('/api/agents', fetchAgents, {
  refreshInterval: 30000,   // 30 seconds
  revalidateOnFocus: true,  // refresh when user returns to tab
});

// For the sprint board (more critical, poll slightly faster):
const { data: sprint } = useSWR(
  projectId ? `/api/projects/${projectId}/sprint` : null,
  () => fetchSprint(projectId),
  { refreshInterval: 20000 }
);
```

---

### 4.4 `requirements.txt` additions

```
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
```

---

## 5. Part D — Startup Script

### `start.sh`

```bash
#!/bin/bash

# Agent Mind Bridge — Start all services
# Usage: ./start.sh

set -e

echo "Starting Agent Mind Bridge..."

# Start MCP server (port 3333)
echo "  Starting MCP server on port 3333..."
python server.py &
MCP_PID=$!

# Start REST API (port 8000)
echo "  Starting REST API on port 8000..."
uvicorn api:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

# Start Next.js dashboard (port 3000)
echo "  Starting Dashboard on port 3000..."
cd dashboard && npm run dev &
DASH_PID=$!

echo ""
echo "Agent Mind Bridge is running."
echo "  MCP Server:  http://127.0.0.1:3333/mcp"
echo "  REST API:    http://127.0.0.1:8000"
echo "  Dashboard:   http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services."

# Trap Ctrl+C and kill all child processes
trap "kill $MCP_PID $API_PID $DASH_PID 2>/dev/null; exit 0" INT
wait
```

Make executable: `chmod +x start.sh`

### `.env.example` additions

```
# Dashboard API
API_HOST=127.0.0.1
API_PORT=8000

# Next.js
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 6. Implementation Order

```
Step 1: db.py
  - Add init_db_v4(conn) with task_dependencies table and indexes
  - Add would_create_cycle() helper function
  - Call init_db_v4(conn) from server.py lifespan after init_db_v3(conn)
  - Add all query helpers for dependencies

Step 2: models.py
  - Add TaskAddDependencyInput, TaskRemoveDependencyInput
  - Add SprintCloseInput

Step 3: tools.py — Part A (Task Dependencies)
  a. context_task_add_dependency
  b. context_task_remove_dependency
  c. Modify context_task_update — add dependency check on in_progress transition
  d. Modify context_sprint_board — add dependency chain indicators

Step 4: tools.py — Part B (Sprint Retrospective)
  a. context_sprint_close

Step 5: api.py — REST API (implement endpoints in this order)
  a. GET /api/health
  b. GET /api/projects
  c. GET /api/agents
  d. GET /api/projects/{id}/sprint        (most complex — pre-group by column)
  e. GET /api/projects/{id}/sprints
  f. GET /api/projects/{id}/handoffs
  g. GET /api/projects/{id}/activity      (second most complex — union query)
  h. GET /api/projects/{id}/tasks
  i. GET /api/projects/{id}/threads
  j. GET /api/threads/{id}/entries
  k. GET /api/projects/{id}/skills
  l. GET /api/projects/{id}               (last — depends on stats from above)

Step 6: dashboard/ — Next.js UI (implement in this order)
  a. Project scaffold: npx create-next-app@latest dashboard --typescript
  b. Install Tailwind v4: npm install tailwindcss@latest @tailwindcss/postcss@latest
  c. Configure postcss.config.mjs and globals.css
  d. src/lib/api.ts — typed API client
  e. AgentPresenceBar component
  f. ProjectSwitcher component
  g. TaskCard component
  h. SprintBoard component (uses TaskCard)
  i. HandoffPanel component
  j. ActivityStream component
  k. ThreadDrawer component
  l. SkillsPanel component
  m. src/app/page.tsx — main layout wiring everything together

Step 7: start.sh
  - Write startup script
  - chmod +x start.sh
  - Update README.md with new Quick Start section
  - Update INSTALL.md with dashboard setup instructions
```

---

## 7. Testing Checklist

### Startup Verification
- [ ] `./start.sh` starts all three processes without errors
- [ ] MCP server responds at `http://127.0.0.1:3333/mcp`
- [ ] REST API responds at `http://127.0.0.1:8000/api/health`
- [ ] Dashboard loads at `http://localhost:3000`
- [ ] Ctrl+C in start.sh kills all three processes cleanly

### Task Dependencies Tests
```
1.  Add dependency: task A depends on task B (both in same project)
2.  Verify context_sprint_board shows "Waiting on: B" on task A
3.  Verify context_sprint_board shows "Blocks: A" on task B
4.  Try to move task A to in_progress — verify error about unfinished dependency
5.  Move task B to done — try task A to in_progress again — verify success
6.  Attempt circular dependency A→B→C→A — verify error on C→A
7.  context_task_remove_dependency — verify chain indicator disappears from board
8.  Add dependency between tasks in different projects — verify error
```

### Sprint Retrospective Tests
```
1.  Create sprint with tasks in various statuses
2.  Call context_sprint_close
3.  Verify sprint status = 'completed'
4.  Verify new thread created: "{sprint_name} — Retrospective"
5.  Verify retrospective entry is pinned in the retro thread
6.  Verify "What Shipped" section lists done tasks
7.  Verify "Carried Over" section lists non-done tasks
8.  Verify "Blocked at Close" includes blocked_reason
9.  Verify handoff was automatically posted
10. Call context_sprint_close again — verify idempotent response
```

### REST API Tests
```
1.  GET /api/health — returns { "status": "ok" }
2.  GET /api/projects — returns all projects with stats
3.  GET /api/agents — returns all agents with presence (status, last_seen_human)
4.  GET /api/projects/{id}/sprint — board data pre-grouped by status
5.  Verify blocked tasks include blocked_reason in board response
6.  Verify task dependency data included (depends_on, blocks arrays)
7.  GET /api/projects/{id}/activity — unified feed, messages + entries
8.  Verify high-priority messages have priority_flag: true
9.  GET /api/threads/{id}/entries — full thread content
10. GET /api/projects/{id}/handoffs?limit=1 — most recent handoff
11. GET /api/projects/{id}/tasks?status=blocked — only blocked tasks
12. CORS: verify browser can fetch from localhost:3000 → localhost:8000
```

### Dashboard Tests
```
1.  Dashboard loads with no console errors
2.  Agent Presence Bar shows all agents with correct status colors
3.  WORKING agent dot pulses
4.  BLOCKED agent dot is red, no pulse
5.  Project Switcher dropdown shows all projects
6.  Switching projects re-fetches sprint board and activity
7.  Sprint Board renders correct columns (empty columns hidden)
8.  BLOCKED column has red left-border
9.  Task cards show priority badges and assignee
10. Blocked task cards show blocked_reason
11. Task dependency indicators visible on linked tasks
12. Click thread in Activity Stream — drawer slides in
13. Thread Drawer shows full entry list with type colors
14. Pinned entries marked with ⭐ in drawer
15. Close drawer — returns to main dashboard view
16. Latest Handoff panel shows from_agent and summary
17. Unacknowledged handoff has yellow left border
18. Global Skills panel collapsed by default, expands on click
19. Auto-refresh: wait 35 seconds, post a new entry via MCP, verify it appears
20. Dashboard works with zero active sprint (shows "No active sprint" state)
```

---

## 8. Full Tool Index

### New Tools — v4 (3)

| Tool | Layer | Read/Write | Destructive | Idempotent |
|---|---|---|---|---|
| `context_task_add_dependency` | Sprint Board | Write | No | Yes |
| `context_task_remove_dependency` | Sprint Board | Write | Yes | Yes |
| `context_sprint_close` | Sprint Board | Write | No | Yes |

### Modified Tools (2)

| Tool | Change |
|---|---|
| `context_task_update` | Rejects in_progress transition if unfinished dependencies exist |
| `context_sprint_board` | Shows dependency chain indicators (Waiting on / Blocks) |

### REST Endpoints — Dashboard API (12, not MCP tools)

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Connection status |
| `GET /api/projects` | Project Switcher |
| `GET /api/projects/{id}` | Project stats |
| `GET /api/agents` | Agent Presence Bar |
| `GET /api/projects/{id}/sprint` | Sprint Board (pre-grouped) |
| `GET /api/projects/{id}/sprints` | Sprint history |
| `GET /api/projects/{id}/threads` | Thread list |
| `GET /api/threads/{id}/entries` | Thread Drawer content |
| `GET /api/projects/{id}/activity` | Activity Stream |
| `GET /api/projects/{id}/tasks` | Task list (supports ?status=blocked) |
| `GET /api/projects/{id}/handoffs` | Latest Handoff panel |
| `GET /api/projects/{id}/skills` | Global Skills panel |

### Grand Total

| Layer | Tools |
|---|---|
| Collaboration (projects/threads/entries/search) | 17 |
| Memory | 8 |
| Skills | 11 |
| Agent Collaboration (messages/presence/handoffs) | 9 |
| Meta (help) | 1 |
| Sprint Board (v3 + v4 additions) | 13 |
| **Total MCP Tools** | **59** |

REST API endpoints are not MCP tools — they are a separate layer for the dashboard UI only.
