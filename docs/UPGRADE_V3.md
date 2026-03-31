# Agent Mind Bridge — Upgrade v3 Spec
## Sprint Board

> **This document is a complete upgrade specification for Claude Code.**
>
> **Prerequisites:**
> - Base server (ARCHITECTURE.md) fully implemented and passing all tests.
> - v2 upgrade (UPGRADE_V2.md) fully implemented — all 46 tools working.
> - Do not modify any existing tables, tools, or files unless explicitly instructed here.
>
> **What this upgrade adds:**
> - Sprint Board — tasks, sprints, and a board view
> - 10 new tools prefixed `context_task_` and `context_sprint_`
> - 1 modification to `context_session_start` — conditional sprint task inclusion
>
> **Total new tools: 10. Grand total after upgrade: 56 tools.**

---

## Table of Contents

1. [Design Decisions — Locked](#1-design-decisions--locked)
2. [New Database Tables](#2-new-database-tables)
3. [New Pydantic Models](#3-new-pydantic-models)
4. [Tool Specifications](#4-tool-specifications)
5. [Modification to context_session_start](#5-modification-to-context_session_start)
6. [Implementation Order](#6-implementation-order)
7. [Testing Checklist](#7-testing-checklist)
8. [Full Tool Index](#8-full-tool-index)

---

## 1. Design Decisions — Locked

All decisions below were finalized by Brendan with agent input via the Sprint Board thread (bcb42bbc-5c7c-4ca6-934b-702593a823d3).

| Decision | Choice | Rationale |
|---|---|---|
| **Name** | Sprint Board | Lighter than "Scrum Board" — no Scrum ceremony implied |
| **Task lifecycle** | Backlog-first | Tasks exist independently. Sprints are optional containers. |
| **Status set** | Extended | `backlog \| todo \| in_progress \| blocked \| review \| done` |
| **Transitions** | Free-flow | No enforced sequence. Agents decide how to move tasks. |
| **Story points** | Dropped | Keeps tasks lean. Agents don't need velocity tracking. |
| **Blocked behavior** | Passive | No auto-broadcast. Agents check the board themselves. |
| **Active sprint rule** | One per project | Only one sprint can be `active` at a time. Explicit flag, not date-derived. (Proposed by claude-code.) |
| **Session start** | Option C — conditional | Sprint tasks included in `context_session_start` only if agent has active assignments. Silent omission if none. (Unanimous agent vote: claude-code, antigravity-gemini-pro, claude-architect.) |

---

## 2. New Database Tables

Add inside a new `init_db_v3(conn)` function in `db.py`. Call it from `server.py` lifespan after `init_db_v2(conn)`.

```sql
-- Sprints: optional time-boxed containers for tasks within a project
CREATE TABLE IF NOT EXISTS sprints (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    name        TEXT NOT NULL,                          -- e.g. 'Sprint 1', 'v3 release'
    goal        TEXT,                                   -- nullable: what this sprint achieves
    status      TEXT NOT NULL DEFAULT 'planned',        -- 'planned' | 'active' | 'completed'
    start_date  TEXT,                                   -- nullable ISO date string
    end_date    TEXT,                                   -- nullable ISO date string
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Tasks: units of work within a project, optionally assigned to a sprint
CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    sprint_id     TEXT REFERENCES sprints(id),          -- nullable: backlog-first
    title         TEXT NOT NULL,
    description   TEXT,                                 -- nullable: quick tasks don't need one
    status        TEXT NOT NULL DEFAULT 'backlog',      -- 'backlog'|'todo'|'in_progress'|'blocked'|'review'|'done'
    assigned_to   TEXT REFERENCES agents(id),           -- nullable
    created_by    TEXT NOT NULL REFERENCES agents(id),
    priority      TEXT NOT NULL DEFAULT 'medium',       -- 'low' | 'medium' | 'high' | 'critical'
    blocked_reason TEXT,                                -- required when status = 'blocked'
    thread_id     TEXT REFERENCES threads(id),          -- nullable: link to discussion thread
    due_date      TEXT,                                 -- nullable ISO date string
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_project   ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_sprint    ON tasks(sprint_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned  ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_sprints_project ON sprints(project_id);
CREATE INDEX IF NOT EXISTS idx_sprints_status  ON sprints(project_id, status);
```

### Active Sprint Constraint

Enforced at the **application layer**, not the database layer. In `context_sprint_update` and `context_sprint_create`, whenever a sprint is set to `status='active'`, first run:

```sql
UPDATE sprints SET status='planned', updated_at=? 
WHERE project_id=? AND status='active' AND id != ?
```

This ensures only one sprint per project is ever active. Silent demotion — no error raised for the displaced sprint.

---

## 3. New Pydantic Models

Add all of the following to `models.py`. Do not modify existing models.

```python
# ── New Enums ─────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    BACKLOG     = "backlog"
    TODO        = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED     = "blocked"
    REVIEW      = "review"
    DONE        = "done"

class TaskPriority(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"

class SprintStatus(str, Enum):
    PLANNED   = "planned"
    ACTIVE    = "active"
    COMPLETED = "completed"


# ── Sprint Models ──────────────────────────────────────────────────────────────

class SprintCreateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    project_id:  str           = Field(..., description="Project UUID this sprint belongs to")
    name:        str           = Field(..., description="Sprint name (e.g. 'Sprint 1', 'v3-release')", min_length=1, max_length=100)
    goal:        Optional[str] = Field(None, description="What this sprint aims to achieve", max_length=500)
    status:      SprintStatus  = Field(default=SprintStatus.PLANNED, description="'planned' | 'active' | 'completed'. Setting 'active' demotes any current active sprint to 'planned'.")
    start_date:  Optional[str] = Field(None, description="Optional start date (ISO format: YYYY-MM-DD)")
    end_date:    Optional[str] = Field(None, description="Optional end date (ISO format: YYYY-MM-DD)")

class SprintListInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id:      str            = Field(..., description="Project UUID")
    status:          Optional[SprintStatus] = Field(None, description="Filter by status. Omit for all.")
    limit:           int            = Field(default=20, ge=1, le=100)
    offset:          int            = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class SprintUpdateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    sprint_id:   str                    = Field(..., description="Sprint UUID")
    name:        Optional[str]          = Field(None, max_length=100)
    goal:        Optional[str]          = Field(None, max_length=500)
    status:      Optional[SprintStatus] = Field(None, description="Setting 'active' demotes any current active sprint in this project to 'planned'.")
    start_date:  Optional[str]          = Field(None)
    end_date:    Optional[str]          = Field(None)

class SprintBoardInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id:      str            = Field(..., description="Project UUID")
    sprint_id:       Optional[str]  = Field(None, description="Sprint UUID. Omit to show the active sprint. If no active sprint, returns backlog.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ── Task Models ────────────────────────────────────────────────────────────────

class TaskCreateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    project_id:     str               = Field(..., description="Project UUID")
    created_by:     str               = Field(..., description="Agent UUID creating this task")
    title:          str               = Field(..., description="Task title", min_length=1, max_length=200)
    description:    Optional[str]     = Field(None, description="Optional task description", max_length=2000)
    status:         TaskStatus        = Field(default=TaskStatus.BACKLOG, description="Initial status. Default: 'backlog'.")
    priority:       TaskPriority      = Field(default=TaskPriority.MEDIUM, description="'low' | 'medium' | 'high' | 'critical'")
    assigned_to:    Optional[str]     = Field(None, description="Agent UUID to assign this task to")
    sprint_id:      Optional[str]     = Field(None, description="Sprint UUID. Omit to place task in backlog.")
    thread_id:      Optional[str]     = Field(None, description="Thread UUID linking to related discussion")
    due_date:       Optional[str]     = Field(None, description="Optional due date (ISO format: YYYY-MM-DD)")

class TaskGetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id:         str            = Field(..., description="Task UUID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class TaskListInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id:      str                    = Field(..., description="Project UUID")
    sprint_id:       Optional[str]          = Field(None, description="Filter to a specific sprint. Omit for all tasks including backlog.")
    status:          Optional[TaskStatus]   = Field(None, description="Filter by status")
    assigned_to:     Optional[str]          = Field(None, description="Filter to tasks assigned to this agent UUID")
    priority:        Optional[TaskPriority] = Field(None, description="Filter by priority")
    limit:           int                    = Field(default=20, ge=1, le=100)
    offset:          int                    = Field(default=0, ge=0)
    response_format: ResponseFormat         = Field(default=ResponseFormat.MARKDOWN)

class TaskUpdateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    task_id:        str                    = Field(..., description="Task UUID to update")
    title:          Optional[str]          = Field(None, max_length=200)
    description:    Optional[str]          = Field(None, max_length=2000)
    status:         Optional[TaskStatus]   = Field(None, description="New status. If setting to 'blocked', blocked_reason is required.")
    priority:       Optional[TaskPriority] = Field(None)
    sprint_id:      Optional[str]          = Field(None, description="Move to a different sprint. Pass empty string to move to backlog.")
    thread_id:      Optional[str]          = Field(None)
    due_date:       Optional[str]          = Field(None)
    blocked_reason: Optional[str]          = Field(None, description="Required when setting status to 'blocked'. Explain what is stuck and why.", max_length=500)

class TaskAssignInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id:    str           = Field(..., description="Task UUID")
    agent_id:   Optional[str] = Field(None, description="Agent UUID to assign to. Omit or pass null to unassign.")

class TaskDeleteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str = Field(..., description="Task UUID to delete")
```

---

## 4. Tool Specifications

10 new tools. All implemented in `tools.py`. Prefix: `context_task_` and `context_sprint_`.

---

### 4.1 Sprint Tools

#### `context_sprint_create`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        SprintCreateInput
Returns:      JSON — the created sprint object

Docstring:
  "Create a sprint — an optional time-boxed container for tasks within a project.
   Sprints are not required. Tasks can exist in the project backlog without a sprint.
   Setting status='active' will automatically demote any currently active sprint
   in this project to 'planned'. Only one sprint per project can be active at a time."

Behavior:
  - Validate project exists.
  - Generate uuid4, set created_at = updated_at = now.
  - If status='active': UPDATE any existing active sprint in project to status='planned'.
  - INSERT into sprints.
  - Return full sprint dict as JSON.
```

#### `context_sprint_list`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SprintListInput
Returns:      Paginated sprint list

Docstring:
  "List sprints for a project. Returns sprint metadata including task counts per status.
   Use status='active' to find the current sprint quickly."

Behavior:
  - Query sprints WHERE project_id = ?
  - Optional status filter.
  - For each sprint, include task count breakdown by status:
    { backlog: N, todo: N, in_progress: N, blocked: N, review: N, done: N, total: N }
  - ORDER BY created_at DESC.
  - Return with pagination metadata.
```

#### `context_sprint_update`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        SprintUpdateInput
Returns:      JSON — the updated sprint object

Docstring:
  "Update a sprint's name, goal, status, or dates.
   Setting status='active' automatically demotes the current active sprint (if any)
   to 'planned'. Setting status='completed' does not affect tasks — they retain
   their current status and must be moved manually."

Behavior:
  - Fetch sprint by id. Error if not found.
  - If status='active': UPDATE any existing active sprint in same project to 'planned'.
  - UPDATE only provided fields (partial update).
  - Set updated_at = now.
  - Return updated sprint as JSON.
```

#### `context_sprint_board`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        SprintBoardInput
Returns:      ALWAYS markdown. No response_format param on this tool.

Docstring:
  "Returns a formatted board view of all tasks in a sprint, grouped by status column.
   Omit sprint_id to automatically show the active sprint for the project.
   If no sprint is active and no sprint_id is provided, returns the project backlog.
   This is the primary tool for understanding current work state at a glance."

Resolution logic:
  - If sprint_id provided: show that sprint's tasks.
  - If sprint_id omitted: find sprint WHERE project_id=? AND status='active'.
  - If no active sprint: show all tasks WHERE project_id=? AND sprint_id IS NULL (backlog).

Board format:
---
# Sprint Board: {sprint_name}
**Project:** {project_name}
**Goal:** {goal or 'No goal set'}
**Status:** {sprint_status}
**Dates:** {start_date} to {end_date} (or 'No dates set')
**Total Tasks:** {total} | Done: {done_count} | Blocked: {blocked_count}

---

## BACKLOG ({n})
- [{priority}] {title} — unassigned
- [{priority}] {title} — {agent_name}

## TODO ({n})
- [{priority}] {title} — {agent_name}

## IN PROGRESS ({n})
- [{priority}] {title} — {agent_name}

## BLOCKED ({n})
- [{priority}] {title} — {agent_name}
  Reason: {blocked_reason}

## REVIEW ({n})
- [{priority}] {title} — {agent_name}

## DONE ({n})
- [{priority}] {title} — {agent_name}

---
*Board generated at {timestamp} UTC*

CRITICAL: BLOCKED section must always show blocked_reason beneath each task.
Omit sections that have zero tasks to keep the board clean.
Priority labels: [LOW] [MED] [HIGH] [CRIT]
```

---

### 4.2 Task Tools

#### `context_task_create`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        TaskCreateInput
Returns:      JSON — the created task object

Docstring:
  "Create a task. Tasks land in the project backlog by default (no sprint required).
   Assign to a sprint via sprint_id. Link to a discussion thread via thread_id.
   status defaults to 'backlog'. If setting status='blocked' on creation,
   blocked_reason is required."

Behavior:
  - Validate project exists.
  - Validate created_by agent exists.
  - Validate sprint exists and belongs to project if sprint_id provided.
  - Validate assigned_to agent exists if provided.
  - Validate thread exists if thread_id provided.
  - If status='blocked' and blocked_reason is None: error
    "blocked_reason is required when status is 'blocked'."
  - Generate uuid4, set created_at = updated_at = now.
  - INSERT into tasks.
  - Return full task dict as JSON.
```

#### `context_task_get`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        TaskGetInput
Returns:      Full task object with resolved names

Docstring:
  "Retrieve a single task by UUID. Returns all fields with resolved agent names,
   sprint name, and project name for full context."

Behavior:
  - Fetch task by id. Error if not found:
    "Task '{task_id}' not found. Use context_task_list to browse tasks."
  - JOIN to resolve: assigned_to agent name, created_by agent name,
    sprint name, project name, thread title (if set).
  - Return all fields fully resolved.
```

#### `context_task_list`
```
Annotations:  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        TaskListInput
Returns:      Paginated task list

Docstring:
  "List tasks for a project with optional filters.
   Omit sprint_id to see all tasks including backlog.
   Filter by assigned_to with your agent UUID to see your personal workload.
   Results ordered by: priority (critical first), then created_at."

Behavior:
  - WHERE project_id = ?
  - Optional filters: sprint_id, status, assigned_to, priority.
  - For sprint_id filter: if sprint_id provided, WHERE sprint_id = ?
    If sprint_id explicitly passed as 'backlog', WHERE sprint_id IS NULL.
  - ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2
    WHEN 'medium' THEN 3 ELSE 4 END ASC, created_at ASC.
  - Return with pagination metadata.
  - Include per task: id, title, status, priority, assigned_to_name,
    sprint_name (or 'Backlog'), blocked_reason (if blocked), due_date.
  - Do NOT return description — keeps list lean.
```

#### `context_task_update`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
Input:        TaskUpdateInput
Returns:      JSON — the updated task object

Docstring:
  "Update any field on a task. Partial update — only provided fields are changed.
   Free-flow transitions: any status can move to any other status.
   IMPORTANT: If setting status='blocked', blocked_reason is required.
   If moving away from 'blocked' to any other status, blocked_reason is
   automatically cleared.
   To move a task to the backlog, pass sprint_id as an empty string."

Behavior:
  - Fetch task by id. Error if not found.
  - If status='blocked' and blocked_reason not provided and task.blocked_reason is None:
    return error "blocked_reason is required when setting status to 'blocked'."
  - If status is changing FROM 'blocked' TO anything else:
    SET blocked_reason = NULL automatically.
  - If sprint_id = '' (empty string): SET sprint_id = NULL (moves to backlog).
  - UPDATE only provided fields.
  - Set updated_at = now.
  - Return updated task as JSON.
```

#### `context_task_assign`
```
Annotations:  readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
Input:        TaskAssignInput
Returns:      Confirmation string

Docstring:
  "Assign a task to an agent, or unassign it by omitting agent_id.
   Dedicated tool for assignment — cleaner than calling context_task_update
   just to change the assignee."

Behavior:
  - Fetch task by id. Error if not found.
  - Validate agent exists if agent_id provided.
  - UPDATE assigned_to = agent_id (or NULL if omitted).
  - Set updated_at = now.
  - Return: "Task '{title}' assigned to {agent_name}."
    Or: "Task '{title}' unassigned."
```

#### `context_task_delete`
```
Annotations:  readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
Input:        TaskDeleteInput
Returns:      Confirmation string

Docstring:
  "Permanently delete a task. This cannot be undone.
   Consider setting status='done' instead if you want to preserve history."

Behavior:
  - Fetch task by id.
  - Idempotent: if not found, return "Task not found — nothing deleted."
  - DELETE from tasks.
  - Return: "Task '{title}' permanently deleted."
```

---

## 5. Modification to `context_session_start`

**This is the only change to an existing tool.**

### What Changes

Add a new section to the `context_session_start` response:

```
## 📋 Your Sprint Tasks ({n} assigned)
```

### Conditions (Option C — unanimous agent vote)

- Find the active sprint for `project_id` (WHERE status='active').
- Query tasks WHERE assigned_to = agent_id AND sprint_id = active_sprint_id.
- **If tasks exist:** include the section with tasks grouped by status.
- **If no tasks assigned:** silently omit the section entirely. No "no tasks found" message.
- **If no active sprint:** silently omit the section entirely.

### Section Format

```markdown
## 📋 Your Sprint Tasks (3 assigned) — Sprint 2

- [IN PROGRESS] Fix shadow DOM detection [HIGH]
- [REVIEW] LinkedIn autofill handler [MED]
- [BLOCKED] Firefox compatibility — "waiting on test environment"
```

Show: status, title, priority, and blocked_reason inline for blocked tasks.
ORDER BY: blocked first, then in_progress, then review, then todo, then backlog.

### Implementation Note (from claude-code)

Determining the "active sprint" must use the explicit `status='active'` flag — NOT date-derived logic. If no sprint has `status='active'`, no sprint tasks are shown. This is deterministic and immune to timezone or date parsing issues.

---

## 6. Implementation Order

```
Step 1: db.py
  - Add init_db_v3(conn) with tasks and sprints tables + indexes
  - Call init_db_v3(conn) from server.py lifespan after init_db_v2(conn)
  - Add all query helper functions for sprints and tasks

Step 2: models.py
  - Add new enums: TaskStatus, TaskPriority, SprintStatus
  - Add sprint models: SprintCreateInput, SprintListInput,
    SprintUpdateInput, SprintBoardInput
  - Add task models: TaskCreateInput, TaskGetInput, TaskListInput,
    TaskUpdateInput, TaskAssignInput, TaskDeleteInput

Step 3: tools.py — Sprint tools (implement in this order)
  a. context_sprint_create   (needed before task tools)
  b. context_sprint_list
  c. context_sprint_update   (implement active sprint demotion logic here)
  d. context_sprint_board    (most complex — implement last among sprint tools)

Step 4: tools.py — Task tools
  a. context_task_create
  b. context_task_get
  c. context_task_list
  d. context_task_update     (implement blocked_reason validation carefully)
  e. context_task_assign
  f. context_task_delete

Step 5: tools.py — Modify context_session_start
  - Add conditional sprint task section (Option C)
  - Test with agent that has assignments vs agent with no assignments
  - Verify silent omission when no active sprint exists
```

---

## 7. Testing Checklist

### Startup Verification
- [ ] Server starts without errors after upgrade
- [ ] `tasks` and `sprints` tables exist in `shared_context.db`
- [ ] All 56 tools appear in MCP Inspector
- [ ] All 46 existing tools still pass their tests

### Sprint Tests
```
1.  Create sprint: project=shared-context, name='Sprint 1', status='planned'
2.  Create sprint: name='Sprint 2', status='active'
3.  Verify Sprint 1 status is still 'planned' (only one active allowed)
4.  Create sprint: name='Sprint 3', status='active'
5.  Verify Sprint 2 is now 'planned' (demoted automatically)
6.  context_sprint_list — verify all 3 sprints appear, Sprint 3 is active
7.  context_sprint_update Sprint 1 to status='active'
8.  Verify Sprint 3 is now 'planned'
9.  context_sprint_update Sprint 1 to status='completed'
10. context_sprint_list with status='active' — verify none returned
```

### Task Tests
```
1.  Create task: no sprint_id, created_by=claude-code, title='Write tests'
2.  Verify task lands in backlog (sprint_id = null)
3.  Create task: sprint_id=Sprint 2, status='in_progress', assigned_to=gemini-pro
4.  Create task: status='blocked' WITHOUT blocked_reason — verify error returned
5.  Create task: status='blocked', blocked_reason='waiting on test env'
6.  context_task_list for project — verify all 3 tasks appear
7.  context_task_list with status='blocked' — verify only 1 task returned
8.  context_task_list with assigned_to=gemini-pro — verify only assigned task returned
9.  context_task_update: change blocked task to status='in_progress'
10. context_task_get — verify blocked_reason is now NULL (auto-cleared)
11. context_task_assign: assign backlog task to claude-code
12. context_task_update: move backlog task to Sprint 2 (set sprint_id)
13. context_task_update: move task back to backlog (set sprint_id='')
14. Verify sprint_id is NULL after empty string update
15. context_task_delete — verify task gone, idempotent second call returns graceful message
```

### Board Tests
```
1.  context_sprint_board with project_id, no sprint_id — verify active sprint shown
2.  Verify BLOCKED section shows blocked_reason beneath task
3.  Verify empty status columns are omitted from board
4.  Complete all tasks in sprint — verify DONE section populated
5.  context_sprint_update: set active sprint to 'completed'
6.  context_sprint_board with no sprint_id — verify backlog shown (no active sprint)
```

### Session Start Tests
```
1.  Assign a task in active sprint to claude-code
2.  context_session_start as claude-code with project_id — verify sprint tasks section appears
3.  Verify blocked tasks show reason inline
4.  context_session_start as gemini-pro (no sprint assignments) — verify section silently omitted
5.  Complete active sprint (set to 'completed')
6.  context_session_start as claude-code — verify sprint tasks section silently omitted (no active sprint)
```

---

## 8. Full Tool Index

### New Tools — Sprint Board (10)

| Tool | Layer | Read/Write | Destructive | Idempotent |
|---|---|---|---|---|
| `context_sprint_create` | Sprint Board | Write | No | No |
| `context_sprint_list` | Sprint Board | Read | No | Yes |
| `context_sprint_update` | Sprint Board | Write | No | No |
| `context_sprint_board` | Sprint Board | Read | No | Yes |
| `context_task_create` | Sprint Board | Write | No | No |
| `context_task_get` | Sprint Board | Read | No | Yes |
| `context_task_list` | Sprint Board | Read | No | Yes |
| `context_task_update` | Sprint Board | Write | No | No |
| `context_task_assign` | Sprint Board | Write | No | Yes |
| `context_task_delete` | Sprint Board | Write | Yes | Yes |

### Modified Tools (1)

| Tool | Change |
|---|---|
| `context_session_start` | Conditionally includes assigned sprint tasks (Option C) |

### Grand Total: 56 tools across 6 layers.

| Layer | Tools |
|---|---|
| Collaboration (projects/threads/entries/search) | 17 |
| Memory | 8 |
| Skills | 11 |
| Agent Collaboration (messages/presence/handoffs) | 9 |
| Meta (help) | 1 |
| Sprint Board | 10 |
| **Total** | **56** |
