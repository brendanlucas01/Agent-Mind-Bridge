"""
MCP tools definition module.

Provides 46 fastMCP tools exposed to the LLM agent.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

from mcp.server.fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations

from app import mcp
import db
from models import (
    RegisterAgentInput, ListAgentsInput, GetAgentInput,
    CreateProjectInput, ListProjectsInput, GetProjectInput, ArchiveProjectInput,
    CreateThreadInput, ListThreadsInput, GetThreadInput, ResolveThreadInput, ExportThreadInput,
    PostEntryInput, UpdateEntryInput, PinEntryInput, GetEntryInput,
    MemorySetShortInput, MemoryGetShortInput, MemoryClearShortInput,
    MemorySetLongInput, MemoryGetLongInput, MemoryDeleteLongInput,
    MemorySearchInput, MemoryPromoteInput, MemoryScope,
    MessageSendInput, MessageInboxInput, MessageReadInput,
    PresenceUpdateInput, PresenceGetInput,
    HandoffPostInput, HandoffGetInput, HandoffAcknowledgeInput,
    SessionStartInput,
    SkillCreatePersonalInput, SkillGetPersonalInput, SkillListPersonalInput,
    SkillUpdatePersonalInput, SkillDeletePersonalInput,
    SkillCreateGlobalInput, SkillGetGlobalInput, SkillListGlobalInput,
    SkillUpdateGlobalInput, SkillDeleteGlobalInput, SkillSearchInput,
    HelpInput, SearchContextInput, ResponseFormat, SearchIn, GLOBAL_SENTINEL,
    # v3 — Sprint Board
    SprintCreateInput, SprintListInput, SprintUpdateInput, SprintBoardInput,
    TaskCreateInput, TaskGetInput, TaskListInput, TaskUpdateInput,
    TaskAssignInput, TaskDeleteInput,
    TaskStatus, TaskPriority, SprintStatus,
    # v4 — Task Dependencies + Sprint Retrospective
    TaskAddDependencyInput, TaskRemoveDependencyInput, SprintCloseInput,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _error(message: str) -> str:
    return f"Error: {message}"


def _fmt_ts(ts: str) -> str:
    """Format ISO timestamp to 'YYYY-MM-DD HH:MM UTC'."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return ts


def _normalize_rank(rank) -> str:
    try:
        r = float(rank)
        if r > -0.5:
            return "high"
        elif r > -1.5:
            return "medium"
        else:
            return "low"
    except Exception:
        return "low"


def _pagination_meta(total: int, returned: int, offset: int, limit: int) -> dict:
    has_more = (offset + returned) < total
    return {
        "total": total,
        "returned": returned,
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + returned if has_more else None,
    }


# =============================================================================
# AGENT TOOLS
# =============================================================================

@mcp.tool(
    name="context_register_agent",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def context_register_agent(params: RegisterAgentInput, ctx: Context) -> str:
    """
    Register a new AI or human agent. Each agent has a unique name and type.

    Args:
        params (RegisterAgentInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        if params.name == GLOBAL_SENTINEL:
            return _error(f"'{GLOBAL_SENTINEL}' is a reserved system name and cannot be used as an agent name.")
        existing = db.db_get_agent_by_name(conn, params.name)
        if existing:
            return _error(f"An agent named '{params.name}' already exists. Use context_list_agents to find its ID.")
        agent = db.db_create_agent(
            conn,
            id=str(uuid.uuid4()),
            name=params.name,
            type_=params.type.value,
            description=params.description,
            created_at=_now(),
        )
        return json.dumps(agent, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_list_agents",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_list_agents(params: ListAgentsInput, ctx: Context) -> str:
    """
    List all registered agents.

    Args:
        params (ListAgentsInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agents = db.db_list_agents(conn)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"agents": agents, "total": len(agents)}, indent=2)
        # Markdown
        if not agents:
            return "No agents registered yet. Use context_register_agent to add one."
        lines = ["## Registered Agents\n"]
        for a in agents:
            lines.append(f"### {a['name']} ({a['id']})")
            lines.append(f"**Type:** {a['type']}")
            if a.get("description"):
                lines.append(f"**Description:** {a['description']}")
            lines.append(f"**Registered:** {_fmt_ts(a['created_at'])}\n")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_get_agent",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_get_agent(params: GetAgentInput, ctx: Context) -> str:
    """
    Get a single agent with activity summary.

    Args:
        params (GetAgentInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found. Use context_list_agents to find valid IDs.")
        activity = db.db_get_agent_activity(conn, params.agent_id)
        result = {**agent, **activity}
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(result, indent=2)
        lines = [
            f"## {agent['name']} ({agent['id']})",
            f"**Type:** {agent['type']}",
        ]
        if agent.get("description"):
            lines.append(f"**Description:** {agent['description']}")
        lines.append(f"**Registered:** {_fmt_ts(agent['created_at'])}")
        lines.append(f"\n### Activity")
        lines.append(f"**Total Entries:** {activity['total_entries']}")
        if activity["by_type"]:
            by_type_str = ", ".join(f"{k}: {v}" for k, v in activity["by_type"].items())
            lines.append(f"**By Type:** {by_type_str}")
        if activity["projects"]:
            proj_str = ", ".join(p["name"] for p in activity["projects"])
            lines.append(f"**Projects:** {proj_str}")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# PROJECT TOOLS
# =============================================================================

@mcp.tool(
    name="context_create_project",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def context_create_project(params: CreateProjectInput, ctx: Context) -> str:
    """
    Create a new project. Projects are top-level containers for threads and entries.

    Args:
        params (CreateProjectInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        if params.name == GLOBAL_SENTINEL:
            return _error(f"'{GLOBAL_SENTINEL}' is a reserved system name and cannot be used as a project name.")
        existing = db.db_get_project_by_name(conn, params.name)
        if existing:
            return _error(f"A project named '{params.name}' already exists. Use context_list_projects to see existing projects.")
        project = db.db_create_project(
            conn,
            id=str(uuid.uuid4()),
            name=params.name,
            description=params.description,
            created_at=_now(),
        )
        return json.dumps(project, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_list_projects",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_list_projects(params: ListProjectsInput, ctx: Context) -> str:
    """
    List all projects with optional status filter and pagination.

    Args:
        params (ListProjectsInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        status_val = params.status.value if params.status else None
        projects, total = db.db_list_projects(conn, status_val, params.limit, params.offset)
        pagination = _pagination_meta(total, len(projects), params.offset, params.limit)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"projects": projects, **pagination}, indent=2)
        if not projects:
            return "No projects found."
        lines = ["## Projects\n"]
        for p in projects:
            lines.append(f"### {p['name']} ({p['id']})")
            lines.append(f"**Status:** {p['status']}")
            if p.get("description"):
                lines.append(f"**Description:** {p['description']}")
            lines.append(f"**Created:** {_fmt_ts(p['created_at'])}")
            if p.get("archived_at"):
                lines.append(f"**Archived:** {_fmt_ts(p['archived_at'])}")
            lines.append("")
        start = params.offset + 1
        end = params.offset + len(projects)
        lines.append(f"*Showing {start}–{end} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_get_project",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_get_project(params: GetProjectInput, ctx: Context) -> str:
    """
    Get a single project with thread summary statistics.

    Args:
        params (GetProjectInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        project = db.db_get_project_by_id(conn, params.project_id)
        if not project:
            return _error(f"Project '{params.project_id}' not found. Use context_list_projects to find valid IDs.")
        counts = db.db_get_project_thread_counts(conn, params.project_id)
        result = {**project, **counts}
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(result, indent=2)
        lines = [
            f"## {project['name']} ({project['id']})",
            f"**Status:** {project['status']}",
        ]
        if project.get("description"):
            lines.append(f"**Description:** {project['description']}")
        lines.append(f"**Created:** {_fmt_ts(project['created_at'])}")
        if project.get("archived_at"):
            lines.append(f"**Archived:** {_fmt_ts(project['archived_at'])}")
        lines.append(f"\n### Thread Summary")
        lines.append(f"**Total:** {counts['total']}  **Open:** {counts['open']}  **Resolved:** {counts['resolved']}")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_archive_project",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_archive_project(params: ArchiveProjectInput, ctx: Context) -> str:
    """
    Archive a project. Does not delete any data.

    Args:
        params (ArchiveProjectInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        project = db.db_get_project_by_id(conn, params.project_id)
        if not project:
            return _error(f"Project '{params.project_id}' not found. Use context_list_projects to find valid IDs.")
        if project["status"] == "archived":
            return f"Project '{project['name']}' ({params.project_id}) has been archived. Project was already archived."
        updated = db.db_archive_project(conn, params.project_id, _now())
        return f"Project '{updated['name']}' ({params.project_id}) has been archived."
    except Exception as e:
        return _error(str(e))


# =============================================================================
# THREAD TOOLS
# =============================================================================

@mcp.tool(
    name="context_create_thread",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def context_create_thread(params: CreateThreadInput, ctx: Context) -> str:
    """
    Create a new thread within a project.

    Args:
        params (CreateThreadInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        project = db.db_get_project_by_id(conn, params.project_id)
        if not project:
            return _error(f"Project '{params.project_id}' not found.")
        thread = db.db_create_thread(
            conn,
            id=str(uuid.uuid4()),
            project_id=params.project_id,
            title=params.title,
            created_at=_now(),
        )
        return json.dumps(thread, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_list_threads",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_list_threads(params: ListThreadsInput, ctx: Context) -> str:
    """
    List threads with optional project/status filters and pagination.

    Args:
        params (ListThreadsInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        status_val = params.status.value if params.status else None
        threads, total = db.db_list_threads(conn, params.project_id, status_val, params.limit, params.offset)
        pagination = _pagination_meta(total, len(threads), params.offset, params.limit)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"threads": threads, **pagination}, indent=2)
        if not threads:
            return "No threads found."
        lines = ["## Threads\n"]
        for t in threads:
            lines.append(f"### {t['title']} ({t['id']})")
            lines.append(f"**Project:** {t.get('project_name', t['project_id'])}")
            lines.append(f"**Status:** {t['status']}  **Entries:** {t.get('entry_count', 0)}")
            lines.append(f"**Created:** {_fmt_ts(t['created_at'])}")
            if t.get("resolved_at"):
                lines.append(f"**Resolved:** {_fmt_ts(t['resolved_at'])}")
            lines.append("")
        start = params.offset + 1
        end = params.offset + len(threads)
        lines.append(f"*Showing {start}–{end} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_get_thread",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_get_thread(params: GetThreadInput, ctx: Context) -> str:
    """
    Use this tool to read thread contents during active collaboration.
    For archiving a completed thread as a standalone document, use context_export_thread instead.
    Use pinned_only=true to quickly surface key decisions without reading the full thread.

    Args:
        params (GetThreadInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        thread = db.db_get_thread_by_id(conn, params.thread_id)
        if not thread:
            return _error(f"Thread '{params.thread_id}' not found. Use context_list_threads to find valid thread IDs.")
        project = db.db_get_project_by_id(conn, thread["project_id"])
        project_name = project["name"] if project else thread["project_id"]
        counts = db.db_get_thread_entry_counts(conn, params.thread_id)
        entry_type_val = params.entry_type.value if params.entry_type else None
        entries, filtered_total = db.db_get_thread_entries(
            conn,
            thread_id=params.thread_id,
            agent_id=params.agent_id,
            entry_type=entry_type_val,
            pinned_only=params.pinned_only,
            order=params.order,
            limit=params.limit,
            offset=params.offset,
        )
        pagination = _pagination_meta(filtered_total, len(entries), params.offset, params.limit)
        if params.response_format == ResponseFormat.JSON:
            result = {
                "thread": {
                    **thread,
                    "project_name": project_name,
                    "total_entries": counts["total_entries"],
                    "pinned_count": counts["pinned_count"],
                },
                "entries": entries,
                **pagination,
            }
            return json.dumps(result, indent=2)
        # Markdown
        lines = [
            f"## {thread['title']} ({thread['id']})",
            f"**Project:** {project_name}",
            f"**Status:** {thread['status']}",
            f"**Created:** {_fmt_ts(thread['created_at'])}",
        ]
        if thread.get("resolved_at"):
            lines.append(f"**Resolved:** {_fmt_ts(thread['resolved_at'])}")
        lines.append(f"**Total Entries:** {counts['total_entries']}  **Pinned:** {counts['pinned_count']}")
        lines.append("\n---\n")
        if not entries:
            lines.append("*No entries match the current filters.*")
        else:
            for e in entries:
                pin_str = " ⭐ *pinned*" if e["pinned"] else ""
                reply_str = f"\n↩ *reply to {e['reply_to']}*" if e.get("reply_to") else ""
                lines.append(f"### [{e['type']}] {e['agent_name']} — {_fmt_ts(e['created_at'])}{pin_str}")
                lines.append(f"**Entry ID:** {e['id']}")
                if reply_str:
                    lines.append(reply_str)
                lines.append(f"\n{e['content']}\n")
                lines.append("---\n")
        start = params.offset + 1
        end = params.offset + len(entries)
        lines.append(f"*Showing {start}–{end} of {filtered_total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_resolve_thread",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_resolve_thread(params: ResolveThreadInput, ctx: Context) -> str:
    """
    Mark a thread as resolved.

    Args:
        params (ResolveThreadInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        thread = db.db_get_thread_by_id(conn, params.thread_id)
        if not thread:
            return _error(f"Thread '{params.thread_id}' not found. Use context_list_threads to find valid thread IDs.")
        note = ""
        if thread["status"] == "resolved":
            note = " (Thread was already resolved.)"
        else:
            db.db_resolve_thread(conn, params.thread_id, _now())
            thread = db.db_get_thread_by_id(conn, params.thread_id)
        counts = db.db_get_thread_entry_counts(conn, params.thread_id)
        return (
            f"Thread '{thread['title']}' ({params.thread_id}) is now resolved.{note}\n"
            f"**Entries:** {counts['total_entries']}  **Resolved at:** {_fmt_ts(thread['resolved_at'])}"
        )
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_export_thread",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_export_thread(params: ExportThreadInput, ctx: Context) -> str:
    """
    Generates a complete markdown document of an entire thread for archiving, sharing with humans,
    or saving outside the server. Always returns ALL entries. Do NOT use this to read context
    during active collaboration — use context_get_thread instead, which supports filtering
    and pagination to keep your context window lean.

    Args:
        params (ExportThreadInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        thread = db.db_get_thread_by_id(conn, params.thread_id)
        if not thread:
            return _error(f"Thread '{params.thread_id}' not found. Use context_list_threads to find valid thread IDs.")
        project = db.db_get_project_by_id(conn, thread["project_id"])
        project_name = project["name"] if project else thread["project_id"]
        entries = db.db_get_thread_all_entries(conn, params.thread_id)
        participants = db.db_get_thread_participants(conn, params.thread_id)
        lines = [
            f"# {thread['title']}",
            "",
            f"**Project:** {project_name}",
            f"**Status:** {thread['status']}",
            f"**Created:** {_fmt_ts(thread['created_at'])}",
            f"**Resolved:** {_fmt_ts(thread['resolved_at']) if thread.get('resolved_at') else 'Open'}",
            f"**Participants:** {', '.join(participants) if participants else 'None'}",
            f"**Total Entries:** {len(entries)}",
            "",
            "---",
            "",
        ]
        for e in entries:
            pin_str = "\n⭐ *pinned*" if e["pinned"] else ""
            reply_str = f"\n↩ *reply to {e['reply_to']}*" if e.get("reply_to") else ""
            lines.append(f"## [{e['type']}] {e['agent_name']} — {_fmt_ts(e['created_at'])}{pin_str}{reply_str}")
            lines.append("")
            lines.append(e["content"])
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# ENTRY TOOLS
# =============================================================================

@mcp.tool(
    name="context_post_entry",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def context_post_entry(params: PostEntryInput, ctx: Context) -> str:
    """
    Post a new entry (proposal, feedback, decision, or note) into a thread.

    Args:
        params (PostEntryInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        thread = db.db_get_thread_by_id(conn, params.thread_id)
        if not thread:
            return _error(f"Thread '{params.thread_id}' not found. Use context_list_threads to find valid thread IDs.")
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found. Register with context_register_agent first.")
        if thread["status"] == "resolved":
            return _error(f"Thread '{params.thread_id}' is resolved and no longer accepting entries.")
        if params.reply_to:
            reply_entry = db.db_get_entry_by_id(conn, params.reply_to)
            if not reply_entry:
                return _error(f"Reply target entry '{params.reply_to}' not found.")
            if reply_entry["thread_id"] != params.thread_id:
                return _error(f"Reply target entry '{params.reply_to}' does not belong to this thread.")
        entry = db.db_create_entry(
            conn,
            id=str(uuid.uuid4()),
            thread_id=params.thread_id,
            agent_id=params.agent_id,
            type_=params.type.value,
            content=params.content,
            reply_to=params.reply_to,
            created_at=_now(),
        )
        return json.dumps(entry, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_update_entry",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def context_update_entry(params: UpdateEntryInput, ctx: Context) -> str:
    """
    Update the content of an existing entry.

    Args:
        params (UpdateEntryInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        entry = db.db_get_entry_by_id(conn, params.entry_id)
        if not entry:
            return _error(f"Entry '{params.entry_id}' not found. Use context_get_thread to find valid entry IDs.")
        updated = db.db_update_entry(conn, params.entry_id, params.content, _now())
        return json.dumps(updated, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_pin_entry",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_pin_entry(params: PinEntryInput, ctx: Context) -> str:
    """
    Pin or unpin an entry to highlight key decisions or proposals.

    Args:
        params (PinEntryInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        entry = db.db_get_entry_by_id(conn, params.entry_id)
        if not entry:
            return _error(f"Entry '{params.entry_id}' not found. Use context_get_thread to find valid entry IDs.")
        db.db_pin_entry(conn, params.entry_id, params.pinned)
        label = "pinned ⭐" if params.pinned else "unpinned"
        return f"Entry {params.entry_id} has been {label}."
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_get_entry",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_get_entry(params: GetEntryInput, ctx: Context) -> str:
    """
    Retrieve a single entry by its UUID. Use this to read the full content of a specific
    entry after identifying its ID from context_search results, or to resolve the parent
    entry in a reply_to chain without loading the entire thread.
    For browsing entries in a thread, use context_get_thread instead.

    Args:
        params (GetEntryInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        entry = db.db_get_entry_with_context(conn, params.entry_id)
        if not entry:
            return _error(
                f"Entry '{params.entry_id}' not found. Use context_search to find valid entry IDs, "
                "or context_get_thread to browse entries within a thread."
            )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(entry, indent=2)
        # Markdown
        pin_str = " ⭐ *pinned*" if entry["pinned"] else ""
        lines = [
            f"## [{entry['type']}] {entry['agent_name']} — {_fmt_ts(entry['created_at'])}{pin_str}",
            f"**Entry ID:** {entry['id']}",
            f"**Thread:** {entry['thread_title']} (`{entry['thread_id']}`)",
            f"**Project ID:** {entry['project_id']}",
            f"**Agent:** {entry['agent_name']} (`{entry['agent_id']}`)",
            f"**Updated:** {_fmt_ts(entry['updated_at'])}",
        ]
        if entry.get("reply_to"):
            lines.append(f"\n↩ *reply to `{entry['reply_to']}`*")
            if entry.get("reply_to_snippet"):
                lines.append(f"> {entry['reply_to_snippet']}")
        lines.append(f"\n{entry['content']}")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# MEMORY TOOLS
# =============================================================================

@mcp.tool(
    name="context_memory_set_short",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_memory_set_short(params: MemorySetShortInput, ctx: Context) -> str:
    """
    Write or overwrite a short-term memory key for an agent.
    Short-term memory is working state for the current task or session.
    Use this to track what you're currently doing, which files you've modified,
    your current approach, or any state that needs to survive across a few tool calls.
    Pass project_id='__global__' for memory not tied to a specific project.
    At end of session, call context_memory_clear_short to clean up,
    or context_memory_promote to elevate important learnings to long-term memory.

    Args:
        params (MemorySetShortInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found. Register with context_register_agent first.")
        if params.project_id != GLOBAL_SENTINEL:
            project = db.db_get_project_by_id(conn, params.project_id)
            if not project:
                return _error(f"Project '{params.project_id}' not found. Use '__global__' for cross-project scope.")
        db.db_stm_set(conn, str(uuid.uuid4()), params.agent_id, params.project_id,
                      params.key, params.value, params.expires_at, _now())
        return f"Short-term memory key '{params.key}' set for agent {agent['name']}."
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_memory_get_short",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_memory_get_short(params: MemoryGetShortInput, ctx: Context) -> str:
    """
    Retrieve short-term memory for an agent.
    Provide a specific key to get one value, or omit key to get all current
    short-term memory for this agent and project scope.
    Scope is strict: '__global__' returns only global entries, a project_id returns only that project's entries.
    Expired entries are automatically excluded.

    Args:
        params (MemoryGetShortInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        now = _now()
        if params.key:
            entry = db.db_stm_get_key(conn, params.agent_id, params.project_id, params.key, now)
            if not entry:
                return _error(f"Key '{params.key}' not found in short-term memory for this scope.")
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(entry, indent=2)
            lines = [f"**{entry['key']}:** {entry['value']}"]
            if entry.get("expires_at"):
                lines.append(f"*Expires: {_fmt_ts(entry['expires_at'])}*")
            lines.append(f"*Updated: {_fmt_ts(entry['updated_at'])}*")
            return "\n".join(lines)
        else:
            entries = db.db_stm_get_all(conn, params.agent_id, params.project_id, now)
            if params.response_format == ResponseFormat.JSON:
                return json.dumps({"entries": entries, "total": len(entries)}, indent=2)
            if not entries:
                return "No short-term memory entries found for this scope."
            lines = [f"## Short-Term Memory — scope: `{params.project_id}`\n"]
            for e in entries:
                exp = f" *(expires {_fmt_ts(e['expires_at'])})*" if e.get("expires_at") else ""
                lines.append(f"**{e['key']}:** {e['value']}{exp}")
            return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_memory_clear_short",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
async def context_memory_clear_short(params: MemoryClearShortInput, ctx: Context) -> str:
    """
    Clear all short-term memory for an agent in a specific scope. Call this at end of session.
    Scope is strict — pass '__global__' to clear global entries, or a project_id to clear that project's entries.
    If you want to preserve important learnings before clearing, call
    context_memory_promote first for each key worth keeping.

    Args:
        params (MemoryClearShortInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found.")
        count = db.db_stm_clear(conn, params.agent_id, params.project_id)
        if count == 0:
            return "No short-term memory to clear."
        return f"Cleared {count} short-term memory {'entry' if count == 1 else 'entries'} for agent {agent['name']} in scope `{params.project_id}`."
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_memory_set_long",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_memory_set_long(params: MemorySetLongInput, ctx: Context) -> str:
    """
    Write a long-term memory — a durable fact that persists across sessions.
    Scope via agent_id and project_id:
      - Both set to real IDs: private to this agent within this project
      - agent_id='__global__', project_id set: shared across all agents in the project
      - Both '__global__': global, shared across all agents and all projects
    Multiple entries per key are allowed — long-term memory is a log of facts, not a key-value store.
    Use tags and confidence to make memories easier to find and evaluate later.

    Args:
        params (MemorySetLongInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        if params.agent_id != GLOBAL_SENTINEL:
            agent = db.db_get_agent_by_id(conn, params.agent_id)
            if not agent:
                return _error(f"Agent '{params.agent_id}' not found.")
        if params.project_id != GLOBAL_SENTINEL:
            project = db.db_get_project_by_id(conn, params.project_id)
            if not project:
                return _error(f"Project '{params.project_id}' not found.")
        if params.source_thread_id:
            thread = db.db_get_thread_by_id(conn, params.source_thread_id)
            if not thread:
                return _error(f"Thread '{params.source_thread_id}' not found.")
        memory = db.db_ltm_set(
            conn,
            id=str(uuid.uuid4()),
            agent_id=params.agent_id,
            project_id=params.project_id,
            key=params.key,
            value=params.value,
            tags=params.tags,
            confidence=params.confidence.value,
            source_thread_id=params.source_thread_id,
            now=_now(),
        )
        return json.dumps(memory, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_memory_get_long",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_memory_get_long(params: MemoryGetLongInput, ctx: Context) -> str:
    """
    Retrieve long-term memories by scope. Scope is strict.
    Provide a key to look up a specific fact, or omit to browse all memories in scope.
    Since long-term memory is a log of facts, multiple entries may exist for the same key.
    Filter by tags to narrow results. Results include source_thread_id so you can
    trace where each fact was learned.

    Args:
        params (MemoryGetLongInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        memories, total = db.db_ltm_get(
            conn, params.agent_id, params.project_id, params.key, params.tags, params.limit, params.offset
        )
        pagination = _pagination_meta(total, len(memories), params.offset, params.limit)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"memories": memories, **pagination}, indent=2)
        if not memories:
            return "No long-term memories found for this scope."
        lines = [f"## Long-Term Memory — scope: agent=`{params.agent_id}` project=`{params.project_id}`\n"]
        for m in memories:
            conf_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(m["confidence"], "⚪")
            lines.append(f"### {m['key']} `{m['id']}`")
            lines.append(f"{conf_icon} **Confidence:** {m['confidence']}  **Created:** {_fmt_ts(m['created_at'])}")
            if m.get("tags"):
                lines.append(f"**Tags:** {m['tags']}")
            if m.get("source_thread_id"):
                lines.append(f"**Source thread:** `{m['source_thread_id']}`")
            lines.append(f"\n{m['value']}\n")
        start = params.offset + 1
        end = params.offset + len(memories)
        lines.append(f"*Showing {start}–{end} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_memory_delete_long",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
async def context_memory_delete_long(params: MemoryDeleteLongInput, ctx: Context) -> str:
    """
    Delete a specific long-term memory entry by its UUID.

    Args:
        params (MemoryDeleteLongInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        memory = db.db_ltm_get_by_id(conn, params.memory_id)
        if not memory:
            return f"Memory '{params.memory_id}' not found — nothing deleted."
        db.db_ltm_delete(conn, params.memory_id)
        return f"Long-term memory '{memory['key']}' ({params.memory_id}) deleted."
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_memory_search",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_memory_search(params: MemorySearchInput, ctx: Context) -> str:
    """
    Full-text search across long-term memory values.
    Supports FTS5 query syntax. Falls back to LIKE search on malformed queries.
    Scope is strict — pass '__global__' for agent_id or project_id to search that scope.
    Returns snippets — retrieve full value via context_memory_get_long if needed.

    Args:
        params (MemorySearchInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        results = db.db_ltm_search_fts(conn, params.query, params.agent_id, params.project_id, params.limit, params.offset)
        for r in results:
            try:
                rank = float(r.get("rank", 0))
                r["relevance"] = "high" if rank > -0.5 else ("medium" if rank > -1.5 else "low")
            except Exception:
                r["relevance"] = "low"
        pagination = _pagination_meta(len(results), len(results), params.offset, params.limit)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"results": results, **pagination}, indent=2)
        if not results:
            return f"No long-term memories found for query: `{params.query}`"
        lines = [f"## Memory Search Results for `{params.query}`\n"]
        for r in results:
            lines.append(f"### {r['key']} `{r['id']}`")
            lines.append(f"**Relevance:** {r['relevance']}  **Confidence:** {r['confidence']}")
            if r.get("tags"):
                lines.append(f"**Tags:** {r['tags']}")
            lines.append(f"\n> {r['snippet']}\n")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_memory_promote",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_memory_promote(params: MemoryPromoteInput, ctx: Context) -> str:
    """
    Promote a short-term memory entry to long-term memory.
    Use this at end of session to preserve important learnings before clearing short-term memory.
    You can optionally rewrite the value when promoting to make it more precise or general.
    Set clear_after=true (default) to automatically remove the short-term entry after promotion.
    target_scope controls the long-term memory scope:
      'agent_project' → private to this agent in the same project
      'project'       → shared across all agents in the project
      'global'        → shared across all agents and all projects

    Args:
        params (MemoryPromoteInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        stm = db.db_stm_get_key(conn, params.agent_id, params.project_id, params.key, _now())
        if not stm:
            return _error(
                f"Short-term memory key '{params.key}' not found for this agent/scope. "
                "It may have expired or already been cleared."
            )
        value = params.override_value if params.override_value is not None else stm["value"]

        # Resolve target scope to agent_id + project_id for LTM
        if params.target_scope == MemoryScope.AGENT_PROJECT:
            ltm_agent_id = params.agent_id
            ltm_project_id = params.project_id
        elif params.target_scope == MemoryScope.PROJECT:
            ltm_agent_id = GLOBAL_SENTINEL
            ltm_project_id = params.project_id
        else:  # GLOBAL
            ltm_agent_id = GLOBAL_SENTINEL
            ltm_project_id = GLOBAL_SENTINEL

        memory = db.db_ltm_set(
            conn,
            id=str(uuid.uuid4()),
            agent_id=ltm_agent_id,
            project_id=ltm_project_id,
            key=params.key,
            value=value,
            tags=params.tags,
            confidence=params.confidence.value,
            source_thread_id=params.source_thread_id,
            now=_now(),
        )
        if params.clear_after:
            db.db_stm_clear(conn, params.agent_id, params.project_id)
        return json.dumps({
            "promoted": memory,
            "short_term_cleared": params.clear_after,
        }, indent=2)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# HELP TOOL
# =============================================================================

_HELP_INDEX = {
    "core": {
        "label": "Pillar 1 — Core (17 tools)",
        "description": "Agents, projects, threads, entries, and search. The foundation everything else is built on.",
        "session_tip": "Start here if you're new. Register your agent, find or create a project, then open threads to collaborate.",
        "groups": {
            "Agents": [
                ("context_register_agent",  "Register a new AI or human agent",                         "name, type"),
                ("context_list_agents",     "List all registered agents",                               "response_format"),
                ("context_get_agent",       "Get one agent with full activity summary",                 "agent_id"),
            ],
            "Projects": [
                ("context_create_project",  "Create a top-level project container",                     "name"),
                ("context_list_projects",   "List projects with optional status filter",                 "status, limit, offset"),
                ("context_get_project",     "Get one project with thread statistics",                    "project_id"),
                ("context_archive_project", "Archive a project (non-destructive)",                      "project_id"),
            ],
            "Threads": [
                ("context_create_thread",   "Create a discussion thread inside a project",              "project_id, title"),
                ("context_list_threads",    "List threads with project/status filters",                  "project_id, status"),
                ("context_get_thread",      "Read thread entries — paginated, filterable. Use during active work.", "thread_id, limit, pinned_only"),
                ("context_resolve_thread",  "Mark a thread as resolved",                                "thread_id"),
                ("context_export_thread",   "Export full thread as a markdown document. Use for archiving.", "thread_id"),
            ],
            "Entries": [
                ("context_post_entry",      "Post a proposal / feedback / decision / note into a thread", "thread_id, agent_id, type, content"),
                ("context_get_entry",       "Get one entry by UUID — useful after search returns an ID", "entry_id"),
                ("context_update_entry",    "Replace an entry's content",                               "entry_id, content"),
                ("context_pin_entry",       "Pin or unpin an entry to highlight key decisions",         "entry_id, pinned"),
            ],
            "Search": [
                ("context_search",          "FTS5 search across entry content and thread titles",        "query, project_id, search_in"),
            ],
        },
    },
    "memory": {
        "label": "Pillar 2 — Memory (8 tools)",
        "description": "Short-term working state + long-term durable facts. Both scoped by agent_id + project_id. Use '__global__' sentinel for cross-agent or cross-project scope.",
        "session_tip": "Call context_memory_get_short at session start to restore working state. Call context_memory_promote + context_memory_clear_short at session end.",
        "groups": {
            "Short-Term Memory": [
                ("context_memory_set_short",   "Write/UPSERT a working memory key (session state)",    "agent_id, project_id, key, value"),
                ("context_memory_get_short",   "Read one key or all keys in scope",                    "agent_id, project_id, key?"),
                ("context_memory_clear_short", "Wipe all STM for agent+scope. Call at session end.",   "agent_id, project_id"),
            ],
            "Long-Term Memory": [
                ("context_memory_set_long",    "Write a durable fact (INSERT always — it's a log)",    "agent_id, project_id, key, value, confidence"),
                ("context_memory_get_long",    "Read LTM entries by scope/key/tag",                    "agent_id, project_id, key?"),
                ("context_memory_delete_long", "Delete a specific LTM entry by UUID",                  "memory_id"),
                ("context_memory_search",      "FTS5 search across LTM values",                        "query, agent_id, project_id"),
                ("context_memory_promote",     "Promote STM → LTM. Optionally rewrite value.",         "agent_id, project_id, key, target_scope"),
            ],
        },
    },
    "skills": {
        "label": "Pillar 3 — Skills (11 tools)",
        "description": "Personal skills (agent-private) + global skills (shared standards). Global skills enforce consistency across all agents on a project.",
        "session_tip": "Call context_skill_list_global at session start to load current project standards. Call context_skill_get_personal to load your own procedures.",
        "groups": {
            "Personal Skills": [
                ("context_skill_create_personal", "Create a personal skill (instruction/procedure/template/pattern)", "agent_id, name, skill_type, description, content"),
                ("context_skill_get_personal",    "Get personal skill by name — increments usage_count",             "agent_id, name"),
                ("context_skill_list_personal",   "List personal skills (descriptions only, not content)",           "agent_id, skill_type?"),
                ("context_skill_update_personal", "Partial update a personal skill",                                  "skill_id, description?, content?, tags?"),
                ("context_skill_delete_personal", "Delete a personal skill permanently",                              "skill_id"),
            ],
            "Global Skills": [
                ("context_skill_create_global",   "Create a project/global standard all agents must follow",         "project_id?, name, skill_type, description, content, created_by"),
                ("context_skill_get_global",      "Get global skill — resolves project→global fallback order",       "name, project_id?"),
                ("context_skill_list_global",     "List global skills. Call at session start.",                      "project_id?"),
                ("context_skill_update_global",   "Update global skill — auto-increments version",                   "skill_id, description?, content?, tags?"),
                ("context_skill_delete_global",   "Delete a global skill permanently",                               "skill_id"),
                ("context_skill_search",          "FTS5 search across personal + global skill content",              "query, agent_id?, project_id?"),
            ],
        },
    },
    "collaboration": {
        "label": "Pillar 4 — Collaboration (9 tools)",
        "description": "Async messages, agent presence, and structured handoffs. Use context_session_start instead of calling these individually at startup.",
        "session_tip": "Always start with context_session_start. It gives you messages, handoffs, presence, STM, and skills in one call.",
        "groups": {
            "Messages": [
                ("context_message_send",        "Send a direct or broadcast message. Broadcasts auto-expire 48h.", "from_agent_id, to_agent_id?, subject, content, priority"),
                ("context_message_inbox",       "Paginated inbox — newest first. Includes broadcasts.",           "agent_id, project_id?, unread_only"),
                ("context_message_read",        "Read full message content + mark as read",                       "message_id"),
            ],
            "Presence": [
                ("context_presence_update",     "Set your status: idle / working / blocked / reviewing",          "agent_id, project_id, status, current_task?"),
                ("context_presence_get",        "See all agents' current status and tasks",                       "project_id?"),
            ],
            "Handoffs": [
                ("context_handoff_post",        "Post a structured end-of-session handoff note",                  "from_agent_id, project_id, summary, in_progress?, blockers?, next_steps?, thread_refs?"),
                ("context_handoff_get",         "Get recent handoffs for a project — read before starting work",  "project_id, limit"),
                ("context_handoff_acknowledge", "Acknowledge a handoff — signals you've taken over",              "handoff_id, agent_id"),
                ("context_session_start",       "⭐ ONE-SHOT session briefing (messages, presence, skills, sprint tasks). Call first.",   "agent_id, project_id?"),
            ],
        },
    },
    "sprints": {
        "label": "Pillar 5 — Sprint Board (13 tools)",
        "description": "Agile task tracking, sprints, and Kanban board visualization. Tasks can exist in the backlog or be assigned to a sprint.",
        "session_tip": "Call context_sprint_board visually check the active sprint at any time.",
        "groups": {
            "Sprints": [
                ("context_sprint_board",   "Returns markdown Kanban board of the active sprint or backlog", ""),
                ("context_sprint_create",  "Create a new sprint. Set status='active' to make it the current sprint", "project_id, name, goal?, status?, start_date?, end_date?"),
                ("context_sprint_list",    "List sprints with their task counts and status",             "project_id, status?, limit, offset"),
                ("context_sprint_update",  "Update a sprint's details or status",                        "sprint_id, name?, goal?, status?, start_date?, end_date?"),
                ("context_sprint_close",   "Close a sprint: auto-generates retrospective thread, pins summary, posts handoff", "sprint_id, closed_by, notes?"),
            ],
            "Tasks": [
                ("context_task_create",    "Create a task in backlog or a sprint",                       "project_id, title, created_by, description?, status?, priority?, assigned_to?, sprint_id?, thread_id?"),
                ("context_task_list",      "List tasks with flexible filtering",                         "project_id, sprint_id?, status?, assigned_to?, priority?, limit, offset"),
                ("context_task_get",       "Get full task details with all names resolved",              "task_id"),
                ("context_task_update",    "Update a task's status / assignment / sprint",               "task_id, title?, status?, sprint_id?, blocked_reason?"),
                ("context_task_assign",    "Quickly assign or unassign a task",                          "task_id, agent_id?"),
                ("context_task_delete",    "Permanently delete a task",                                  "task_id"),
            ],
            "Task Dependencies": [
                ("context_task_add_dependency",    "Add a dependency: task_id is blocked until depends_on is done. Cycle detection is automatic.", "task_id, depends_on, created_by"),
                ("context_task_remove_dependency", "Remove an existing dependency between two tasks",    "task_id, depends_on"),
            ],
        },
    },
}

_RECOMMENDED_FLOW = """
## Recommended Session Flow

**Every session — call these in order:**
1. `context_session_start` — messages, handoffs, presence, STM, skills in one call
2. `context_presence_update` — set status to 'working' with your current task
3. `context_skill_list_global` — load project standards (if not already in session_start)
4. `context_memory_get_short` — restore your working state

**During work:**
- `context_get_thread` / `context_post_entry` — collaborate in threads
- `context_memory_set_short` — track current state across tool calls
- `context_message_send` — notify other agents of blockers or decisions

**End of session:**
1. `context_memory_promote` — save important learnings to long-term memory
2. `context_memory_clear_short` — clean up working state
3. `context_handoff_post` — brief the next agent
4. `context_presence_update` — set status to 'idle'
"""


@mcp.tool(
    name="context_help",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_help(params: HelpInput, ctx: Context) -> str:
    """
    Index of all 58 tools organized by pillar. Call this first in any new session
    or whenever you're unsure which tool to use.
    Filter by pillar name ('core', 'memory', 'skills', 'collaboration', 'sprints') or keyword
    to narrow results. Each tool entry shows: name, purpose, and key parameters.
    For full parameter details, check the tool's own input schema.

    Args:
        params (HelpInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        topic = params.topic.lower().strip() if params.topic else None

        # Resolve topic to pillar key or keyword filter
        pillar_aliases = {
            "core": "core", "agents": "core", "projects": "core", "threads": "core",
            "entries": "core", "search": "core",
            "memory": "memory", "stm": "memory", "ltm": "memory", "short": "memory", "long": "memory",
            "skills": "skills", "personal": "skills", "global": "skills", "skill": "skills",
            "collaboration": "collaboration", "collab": "collaboration", "messages": "collaboration",
            "presence": "collaboration", "handoff": "collaboration", "handoffs": "collaboration",
            "session": "collaboration",
        }
        target_pillar = pillar_aliases.get(topic) if topic else None
        keyword = None if target_pillar else topic

        pillars_to_show = (
            {target_pillar: _HELP_INDEX[target_pillar]} if target_pillar
            else _HELP_INDEX
        )

        if params.response_format == ResponseFormat.JSON:
            out = {}
            for key, pillar in pillars_to_show.items():
                tools_flat = []
                for group, tools in pillar["groups"].items():
                    for name, desc, params_hint in tools:
                        if keyword and keyword not in name and keyword not in desc.lower():
                            continue
                        tools_flat.append({"name": name, "description": desc, "params": params_hint, "group": group})
                if tools_flat:
                    out[key] = {"label": pillar["label"], "tools": tools_flat}
            return json.dumps({"pillars": out, "total_tools": 46}, indent=2)

        # Markdown output
        lines = ["# context_help — Tool Index (46 tools)\n"]

        if not topic:
            lines.append("> Call `context_session_start` at the start of every session — it replaces 5 separate calls with one.\n")

        any_results = False
        for pillar_key, pillar in pillars_to_show.items():
            group_lines = []
            for group, tools in pillar["groups"].items():
                tool_lines = []
                for name, desc, params_hint in tools:
                    if keyword and keyword not in name and keyword not in desc.lower():
                        continue
                    tool_lines.append(f"  - **`{name}`** — {desc}\n    *params: {params_hint}*")
                if tool_lines:
                    group_lines.append(f"\n**{group}**")
                    group_lines.extend(tool_lines)

            if group_lines:
                any_results = True
                lines.append(f"## {pillar['label']}")
                lines.append(f"*{pillar['description']}*")
                lines.append(f"💡 {pillar['session_tip']}\n")
                lines.extend(group_lines)
                lines.append("")

        if not any_results:
            return f"No tools found matching '{topic}'. Try a pillar name: 'core', 'memory', 'skills', 'collaboration'."

        if not topic:
            lines.append(_RECOMMENDED_FLOW)

        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# PERSONAL SKILL TOOLS
# =============================================================================

@mcp.tool(
    name="context_skill_create_personal",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_skill_create_personal(params: SkillCreatePersonalInput, ctx: Context) -> str:
    """
    Create a personal skill — a reusable behavior, procedure, or pattern
    that only this agent uses. Personal skills capture how you individually
    approach problems. Other agents cannot see or access these.
    skill_type options: 'instruction' (a rule to follow), 'procedure' (step-by-step process),
    'template' (reusable scaffold), 'pattern' (architectural approach).

    Args:
        params (SkillCreatePersonalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found. Register with context_register_agent first.")
        existing = db.db_get_personal_skill_by_name(conn, params.agent_id, params.name)
        if existing:
            return _error(f"A personal skill named '{params.name}' already exists for this agent. Use context_skill_update_personal to modify it.")
        skill = db.db_create_personal_skill(
            conn,
            id=str(uuid.uuid4()),
            agent_id=params.agent_id,
            name=params.name,
            skill_type=params.skill_type.value,
            description=params.description,
            content=params.content,
            tags=params.tags,
            created_at=_now(),
        )
        return json.dumps(skill, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_get_personal",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_skill_get_personal(params: SkillGetPersonalInput, ctx: Context) -> str:
    """
    Retrieve a personal skill by name. Also increments the usage_count
    so frequently-used skills can be surfaced in listings.

    Args:
        params (SkillGetPersonalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        skill = db.db_get_personal_skill_by_name(conn, params.agent_id, params.name)
        if not skill:
            return _error(
                f"Personal skill '{params.name}' not found for this agent. "
                "Use context_skill_list_personal to browse available skills, or context_skill_search to search."
            )
        db.db_increment_skill_usage(conn, skill["id"])
        skill["usage_count"] += 1
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(skill, indent=2)
        lines = [
            f"## {skill['name']} ({skill['id']})",
            f"**Type:** {skill['skill_type']}  **Used:** {skill['usage_count']} times",
            f"**Updated:** {_fmt_ts(skill['updated_at'])}",
        ]
        if skill.get("tags"):
            lines.append(f"**Tags:** {skill['tags']}")
        lines.append(f"\n**Description:** {skill['description']}\n")
        lines.append(f"### Content\n\n{skill['content']}")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_list_personal",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_skill_list_personal(params: SkillListPersonalInput, ctx: Context) -> str:
    """
    List personal skills for an agent. Returns descriptions and metadata,
    not full content. Use context_skill_get_personal to retrieve a specific skill's content.
    Sort order: most-used first (usage_count DESC), then alphabetical.

    Args:
        params (SkillListPersonalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found.")
        skill_type_val = params.skill_type.value if params.skill_type else None
        skills, total = db.db_list_personal_skills(conn, params.agent_id, skill_type_val, params.tags, params.limit, params.offset)
        pagination = _pagination_meta(total, len(skills), params.offset, params.limit)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"skills": skills, **pagination}, indent=2)
        if not skills:
            return f"No personal skills found for {agent['name']}. Use context_skill_create_personal to add one."
        lines = [f"## Personal Skills — {agent['name']}\n"]
        for s in skills:
            lines.append(f"### {s['name']} `[{s['skill_type']}]`")
            lines.append(f"{s['description']}")
            if s.get("tags"):
                lines.append(f"**Tags:** {s['tags']}  **Used:** {s['usage_count']}x  **Updated:** {_fmt_ts(s['updated_at'])}")
            else:
                lines.append(f"**Used:** {s['usage_count']}x  **Updated:** {_fmt_ts(s['updated_at'])}")
            lines.append("")
        start = params.offset + 1
        end = params.offset + len(skills)
        lines.append(f"*Showing {start}–{end} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_update_personal",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_skill_update_personal(params: SkillUpdatePersonalInput, ctx: Context) -> str:
    """
    Update a personal skill. Only provided fields are changed (partial update).

    Args:
        params (SkillUpdatePersonalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        skill = db.db_get_personal_skill_by_id(conn, params.skill_id)
        if not skill:
            return _error(f"Personal skill '{params.skill_id}' not found. Use context_skill_list_personal to find valid skill IDs.")
        updated = db.db_update_personal_skill(conn, params.skill_id, params.description, params.content, params.tags, _now())
        return json.dumps(updated, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_delete_personal",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
async def context_skill_delete_personal(params: SkillDeletePersonalInput, ctx: Context) -> str:
    """
    Delete a personal skill permanently.

    Args:
        params (SkillDeletePersonalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        deleted = db.db_delete_personal_skill(conn, params.skill_id)
        if not deleted:
            return "Personal skill not found — nothing deleted."
        return f"Personal skill '{params.skill_id}' has been deleted."
    except Exception as e:
        return _error(str(e))


# =============================================================================
# GLOBAL SKILL TOOLS
# =============================================================================

@mcp.tool(
    name="context_skill_create_global",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_skill_create_global(params: SkillCreateGlobalInput, ctx: Context) -> str:
    """
    Create a global skill — a standard, convention, or pattern that ALL agents
    in this project must follow consistently. This is how you enforce consistency
    across Claude Code, Gemini, and any other agent regardless of interface.
    Set project_id to scope to one project. Omit project_id for a truly global
    standard that applies across all projects.
    All agents should call context_skill_list_global at session start to load
    current project standards.

    Args:
        params (SkillCreateGlobalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        if params.project_id:
            project = db.db_get_project_by_id(conn, params.project_id)
            if not project:
                return _error(f"Project '{params.project_id}' not found.")
        creator = db.db_get_agent_by_id(conn, params.created_by)
        if not creator:
            return _error(f"Agent '{params.created_by}' not found.")
        if db.db_check_global_skill_name_exists(conn, params.name, params.project_id):
            return _error(f"A global skill named '{params.name}' already exists in this scope. Use context_skill_update_global to modify it.")
        skill = db.db_create_global_skill(
            conn,
            id=str(uuid.uuid4()),
            project_id=params.project_id,
            name=params.name,
            skill_type=params.skill_type.value,
            description=params.description,
            content=params.content,
            tags=params.tags,
            created_by=params.created_by,
            created_at=_now(),
        )
        return json.dumps(skill, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_get_global",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_skill_get_global(params: SkillGetGlobalInput, ctx: Context) -> str:
    """
    Retrieve a global skill by name. Resolution order:
    1. Look for skill with this name in the specified project (project_id scoped)
    2. If not found, look for a truly global skill (project_id = null) with this name
    3. If not found, return error with suggestion to search.
    The version field tells you if this skill has been updated since you last read it.

    Args:
        params (SkillGetGlobalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        skill = db.db_get_global_skill_by_name(conn, params.name, params.project_id)
        if not skill:
            return _error(
                f"Global skill '{params.name}' not found. "
                "Use context_skill_list_global to browse or context_skill_search to search."
            )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(skill, indent=2)
        scope_label = skill.get("scope", "global").upper()
        lines = [
            f"## {skill['name']} `[{skill['skill_type']}]` — {scope_label}",
            f"**Skill ID:** {skill['id']}  **Version:** {skill['version']}",
            f"**Updated:** {_fmt_ts(skill['updated_at'])}",
        ]
        if skill.get("tags"):
            lines.append(f"**Tags:** {skill['tags']}")
        lines.append(f"\n**Description:** {skill['description']}\n")
        lines.append(f"### Content\n\n{skill['content']}")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_list_global",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_skill_list_global(params: SkillListGlobalInput, ctx: Context) -> str:
    """
    List global skills. If project_id is provided, returns BOTH project-scoped
    skills AND truly global skills (null project_id), sorted by scope then name.
    Call this at the start of each session to load current project standards.
    Use context_skill_get_global to retrieve a specific skill's full content.

    Args:
        params (SkillListGlobalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        skill_type_val = params.skill_type.value if params.skill_type else None
        skills, total = db.db_list_global_skills(conn, params.project_id, skill_type_val, params.tags, params.limit, params.offset)
        pagination = _pagination_meta(total, len(skills), params.offset, params.limit)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"skills": skills, **pagination}, indent=2)
        if not skills:
            return "No global skills found. Use context_skill_create_global to add project standards."
        lines = ["## Global Skills\n"]
        for s in skills:
            scope_label = "🌍 GLOBAL" if s.get("scope") == "global" else "📁 PROJECT"
            lines.append(f"### {s['name']} `[{s['skill_type']}]` {scope_label}")
            lines.append(f"{s['description']}")
            extra = f"**v{s['version']}**  **Updated:** {_fmt_ts(s['updated_at'])}"
            if s.get("tags"):
                extra += f"  **Tags:** {s['tags']}"
            lines.append(extra)
            lines.append("")
        start = params.offset + 1
        end = params.offset + len(skills)
        lines.append(f"*Showing {start}–{end} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_update_global",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_skill_update_global(params: SkillUpdateGlobalInput, ctx: Context) -> str:
    """
    Update a global skill. Automatically increments the version number.
    Agents that have previously loaded this skill should re-read it when
    they see the version has changed.

    Args:
        params (SkillUpdateGlobalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        skill = db.db_get_global_skill_by_id(conn, params.skill_id)
        if not skill:
            return _error(f"Global skill '{params.skill_id}' not found. Use context_skill_list_global to find valid skill IDs.")
        updated = db.db_update_global_skill(conn, params.skill_id, params.description, params.content, params.tags, _now())
        return json.dumps(updated, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_delete_global",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
async def context_skill_delete_global(params: SkillDeleteGlobalInput, ctx: Context) -> str:
    """
    Delete a global skill permanently.

    Args:
        params (SkillDeleteGlobalInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        deleted = db.db_delete_global_skill(conn, params.skill_id)
        if not deleted:
            return "Global skill not found — nothing deleted."
        return f"Global skill '{params.skill_id}' has been deleted."
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_skill_search",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_skill_search(params: SkillSearchInput, ctx: Context) -> str:
    """
    Full-text search across skill descriptions and content.
    If agent_id is provided, includes that agent's personal skills in results.
    If project_id is provided, includes project-scoped and global skills.
    Results are labelled by source: 'personal' or 'global'.
    Returns snippets — use context_skill_get_personal or context_skill_get_global
    to retrieve full content.

    Args:
        params (SkillSearchInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        results = db.db_search_skills_fts(conn, params.query, params.agent_id, params.project_id, params.limit, params.offset)

        rank_order = {"high": 0, "medium": 1, "low": 2}
        for r in results:
            try:
                rank = float(r.get("rank", 0))
                r["relevance"] = "high" if rank > -0.5 else ("medium" if rank > -1.5 else "low")
            except Exception:
                r["relevance"] = "low"
        results.sort(key=lambda x: rank_order.get(x["relevance"], 2))

        total = len(results)
        paginated = results[params.offset: params.offset + params.limit]
        pagination = _pagination_meta(total, len(paginated), params.offset, params.limit)

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"results": paginated, **pagination}, indent=2)
        if not paginated:
            return f"No skills found for query: `{params.query}`"
        lines = [f"## Skill Search Results for `{params.query}`\n"]
        for r in paginated:
            source_label = "👤 PERSONAL" if r["source"] == "personal" else "🌍 GLOBAL"
            lines.append(f"### {r['name']} `[{r['skill_type']}]` {source_label}")
            lines.append(f"**ID:** `{r['id']}`  **Relevance:** {r['relevance']}")
            if r.get("tags"):
                lines.append(f"**Tags:** {r['tags']}")
            if r.get("description_snippet"):
                lines.append(f"\n> {r['description_snippet']}")
            if r.get("content_snippet"):
                lines.append(f"> {r['content_snippet']}")
            lines.append("")
        start = params.offset + 1
        end = params.offset + len(paginated)
        lines.append(f"*Showing {start}–{end} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# COLLABORATION TOOLS — MESSAGES
# =============================================================================

def _staleness(ts: str) -> str:
    """Returns human-readable 'YYYY-MM-DD HH:MM UTC (Xh ago)' string."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            ago = f"{secs}s ago"
        elif secs < 3600:
            ago = f"{secs // 60}m ago"
        elif secs < 86400:
            ago = f"{secs // 3600}h ago"
        else:
            ago = f"{secs // 86400}d ago"
        return f"{dt.strftime('%Y-%m-%d %H:%M UTC')} ({ago})"
    except Exception:
        return ts


def _broadcast_expires_at() -> str:
    """48-hour expiry timestamp for broadcast messages."""
    return (datetime.now(timezone.utc) + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@mcp.tool(
    name="context_message_send",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_message_send(params: MessageSendInput, ctx: Context) -> str:
    """
    Send an async message to a specific agent or broadcast to all agents in a project.
    Messages persist until read. Use for: handing off work, flagging blockers,
    asking questions that don't belong in a thread, or notifying an agent of something important.
    Priority 'high' should be reserved for blockers or conflicts that need urgent attention.
    Broadcast messages (omit to_agent_id) auto-expire after 48 hours.
    For structured end-of-session handoffs, use context_handoff_post instead.

    Args:
        params (MessageSendInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        sender = db.db_get_agent_by_id(conn, params.from_agent_id)
        if not sender:
            return _error(f"Sender agent '{params.from_agent_id}' not found.")
        if params.to_agent_id:
            recipient = db.db_get_agent_by_id(conn, params.to_agent_id)
            if not recipient:
                return _error(f"Recipient agent '{params.to_agent_id}' not found. Use context_list_agents to find valid agent IDs.")
        if params.project_id:
            project = db.db_get_project_by_id(conn, params.project_id)
            if not project:
                return _error(f"Project '{params.project_id}' not found.")
        if params.thread_ref:
            thread = db.db_get_thread_by_id(conn, params.thread_ref)
            if not thread:
                return _error(f"Thread '{params.thread_ref}' not found.")
        is_broadcast = params.to_agent_id is None
        expires_at = _broadcast_expires_at() if is_broadcast else None
        message = db.db_message_send(
            conn,
            id=str(uuid.uuid4()),
            from_agent_id=params.from_agent_id,
            to_agent_id=params.to_agent_id,
            project_id=params.project_id,
            subject=params.subject,
            content=params.content,
            priority=params.priority.value,
            thread_ref=params.thread_ref,
            expires_at=expires_at,
            now=_now(),
        )
        return json.dumps(message, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_message_inbox",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_message_inbox(params: MessageInboxInput, ctx: Context) -> str:
    """
    Retrieve messages for an agent. Returns messages addressed directly to this agent
    AND broadcast messages (no specific recipient) in the specified project.
    Call this at the start of each session to check for pending communications.
    Messages are ordered newest first. Use unread_only=false to see full history.
    Broadcast messages expire after 48 hours and will not appear after that.

    Args:
        params (MessageInboxInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found.")
        messages, total = db.db_message_inbox(
            conn, params.agent_id, params.project_id,
            params.unread_only, params.limit, params.offset, _now()
        )
        pagination = _pagination_meta(total, len(messages), params.offset, params.limit)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"messages": messages, **pagination}, indent=2)
        if not messages:
            label = "unread messages" if params.unread_only else "messages"
            return f"No {label} found for {agent['name']}."
        lines = [f"## Inbox — {agent['name']} ({'unread only' if params.unread_only else 'all'})\n"]
        for m in messages:
            read_icon = "📭" if m["is_read"] else "📬"
            priority_tag = f" 🔴 HIGH" if m["priority"] == "high" else (" ⬇ low" if m["priority"] == "low" else "")
            broadcast_tag = " 📢 *broadcast*" if not m.get("to_agent_name") else ""
            lines.append(f"{read_icon} **{m['subject']}**{priority_tag}{broadcast_tag}")
            lines.append(f"**From:** {m['from_agent_name']}  **Received:** {_fmt_ts(m['created_at'])}")
            if m.get("project_name"):
                lines.append(f"**Project:** {m['project_name']}")
            lines.append(f"**ID:** `{m['id']}`")
            lines.append(f"> {m['content_preview']}{'...' if len(m['content_preview']) == 100 else ''}")
            if m.get("thread_ref"):
                lines.append(f"*Related thread: `{m['thread_ref']}`*")
            lines.append("")
        start = params.offset + 1
        end = params.offset + len(messages)
        lines.append(f"*Showing {start}–{end} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_message_read",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_message_read(params: MessageReadInput, ctx: Context) -> str:
    """
    Retrieve and mark a specific message as read.
    Returns the full message content. Automatically sets is_read = 1.
    Use context_message_inbox first to browse available messages.

    Args:
        params (MessageReadInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        message = db.db_message_get_by_id(conn, params.message_id)
        if not message:
            return _error(f"Message '{params.message_id}' not found or has expired.")
        db.db_message_mark_read(conn, params.message_id)
        message["is_read"] = 1
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(message, indent=2)
        to_label = message.get("to_agent_name") or "📢 broadcast"
        priority_tag = f" 🔴 HIGH PRIORITY" if message["priority"] == "high" else ""
        lines = [
            f"## {message['subject']}{priority_tag}",
            f"**From:** {message['from_agent_name']}  **To:** {to_label}",
            f"**Received:** {_fmt_ts(message['created_at'])}",
        ]
        if message.get("project_name"):
            lines.append(f"**Project:** {message['project_name']}")
        if message.get("thread_ref"):
            lines.append(f"**Related thread:** `{message['thread_ref']}`")
        lines.append(f"\n{message['content']}")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# COLLABORATION TOOLS — PRESENCE
# =============================================================================

@mcp.tool(
    name="context_presence_update",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_presence_update(params: PresenceUpdateInput, ctx: Context) -> str:
    """
    Update this agent's current status and working task.
    Call this when starting work ('working'), when blocked ('blocked'),
    when reviewing another agent's work ('reviewing'), or at session end ('idle').
    Other agents check this via context_presence_get to avoid duplicate work
    and surface blockers.

    Args:
        params (PresenceUpdateInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found.")
        if params.project_id != GLOBAL_SENTINEL:
            project = db.db_get_project_by_id(conn, params.project_id)
            if not project:
                return _error(f"Project '{params.project_id}' not found.")
        db.db_presence_upsert(conn, str(uuid.uuid4()), params.agent_id, params.project_id,
                              params.status.value, params.current_task, _now())
        msg = f"Presence updated: {agent['name']} is now **{params.status.value}**."
        if params.current_task:
            msg += f" Current task: {params.current_task}"
        return msg
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_presence_get",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_presence_get(params: PresenceGetInput, ctx: Context) -> str:
    """
    Get the current status of all agents. Call this at session start to understand
    what other agents are currently doing, avoid duplicating in-progress work,
    and identify any agents that are blocked and may need input.

    Args:
        params (PresenceGetInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        records = db.db_presence_get(conn, params.project_id)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"presence": records, "total": len(records)}, indent=2)
        if not records:
            return "No presence records found."
        status_icon = {"idle": "💤", "working": "⚡", "blocked": "🚫", "reviewing": "👀"}
        lines = ["## Agent Presence\n"]
        for r in records:
            icon = status_icon.get(r["status"], "❓")
            scope = r.get("project_name") or ("Global" if r["project_id"] == GLOBAL_SENTINEL else r["project_id"])
            lines.append(f"{icon} **{r['agent_name']}** ({r['agent_type']}) — {r['status'].upper()}")
            lines.append(f"**Scope:** {scope}  **Last seen:** {_staleness(r['updated_at'])}")
            if r.get("current_task"):
                lines.append(f"**Task:** {r['current_task']}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# COLLABORATION TOOLS — HANDOFFS
# =============================================================================

@mcp.tool(
    name="context_handoff_post",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_handoff_post(params: HandoffPostInput, ctx: Context) -> str:
    """
    Post a structured end-of-session handoff note for a project.
    Use this when ending a working session so the next agent (or your next session)
    can immediately understand the current state without reading full thread histories.
    Include what you completed, what's in-progress, any blockers, and suggested next steps.
    Reference relevant thread IDs in thread_refs for easy navigation.
    Call context_presence_update with status='idle' after posting a handoff.

    Args:
        params (HandoffPostInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.from_agent_id)
        if not agent:
            return _error(f"Agent '{params.from_agent_id}' not found.")
        project = db.db_get_project_by_id(conn, params.project_id)
        if not project:
            return _error(f"Project '{params.project_id}' not found.")
        thread_refs_str = None
        if params.thread_refs:
            for tid in params.thread_refs:
                if not db.db_get_thread_by_id(conn, tid):
                    return _error(f"Thread '{tid}' not found. Verify all thread_refs exist.")
            thread_refs_str = ",".join(params.thread_refs)
        handoff = db.db_handoff_post(
            conn,
            id=str(uuid.uuid4()),
            from_agent_id=params.from_agent_id,
            project_id=params.project_id,
            summary=params.summary,
            in_progress=params.in_progress,
            blockers=params.blockers,
            next_steps=params.next_steps,
            thread_refs=thread_refs_str,
            now=_now(),
        )
        return json.dumps(handoff, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_handoff_get",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_handoff_get(params: HandoffGetInput, ctx: Context) -> str:
    """
    Retrieve recent handoff notes for a project. Call this at session start
    to understand where the project stands before reading any threads.
    Returns the N most recent handoffs (default 5), newest first.
    Unacknowledged handoffs are marked clearly — acknowledge them with
    context_handoff_acknowledge after reading.

    Args:
        params (HandoffGetInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        project = db.db_get_project_by_id(conn, params.project_id)
        if not project:
            return _error(f"Project '{params.project_id}' not found.")
        handoffs = db.db_handoff_get_recent(conn, params.project_id, params.limit)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"handoffs": handoffs, "total": len(handoffs)}, indent=2)
        if not handoffs:
            return f"No handoffs found for project '{project['name']}'."
        lines = [f"## Handoffs — {project['name']}\n"]
        for h in handoffs:
            ack_status = "✅ acknowledged" if h.get("acknowledged_by") else "⚠️ **UNACKNOWLEDGED**"
            lines.append(f"### {_fmt_ts(h['created_at'])} — {h['from_agent_name']} {ack_status}")
            lines.append(f"**ID:** `{h['id']}`")
            lines.append(f"\n**Summary:**\n{h['summary']}")
            if h.get("in_progress"):
                lines.append(f"\n**In Progress:**\n{h['in_progress']}")
            if h.get("blockers"):
                lines.append(f"\n**Blockers:**\n{h['blockers']}")
            if h.get("next_steps"):
                lines.append(f"\n**Next Steps:**\n{h['next_steps']}")
            if h.get("thread_refs"):
                ids = [t.strip() for t in h["thread_refs"].split(",") if t.strip()]
                titles = db.db_get_thread_titles(conn, ids)
                refs = [f"`{tid}` — {titles.get(tid, 'unknown thread')}" for tid in ids]
                lines.append(f"\n**Threads:** {', '.join(refs)}")
            if h.get("acknowledged_by_name"):
                lines.append(f"\n*Acknowledged by {h['acknowledged_by_name']} at {_fmt_ts(h['acknowledged_at'])}*")
            lines.append("\n---\n")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_handoff_acknowledge",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_handoff_acknowledge(params: HandoffAcknowledgeInput, ctx: Context) -> str:
    """
    Acknowledge a handoff note, confirming you have read it and are taking over.
    This signals to the team that the handoff has been received and acted upon.

    Args:
        params (HandoffAcknowledgeInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        handoff = db.db_handoff_get_by_id(conn, params.handoff_id)
        if not handoff:
            return _error(f"Handoff '{params.handoff_id}' not found.")
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found.")
        if handoff.get("acknowledged_by"):
            return f"Handoff already acknowledged by {handoff['acknowledged_by_name']} at {_fmt_ts(handoff['acknowledged_at'])}."
        db.db_handoff_acknowledge(conn, params.handoff_id, params.agent_id, _now())
        preview = handoff["summary"][:100] + ("..." if len(handoff["summary"]) > 100 else "")
        return f"Handoff acknowledged. You are now responsible for: {preview}"
    except Exception as e:
        return _error(str(e))


# =============================================================================
# COLLABORATION TOOLS — SESSION START
# =============================================================================

@mcp.tool(
    name="context_session_start",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_session_start(params: SessionStartInput, ctx: Context) -> str:
    """
    One-shot session startup briefing. Call this at the very start of every session
    instead of calling inbox, presence, handoff, memory, and skills separately.
    Returns a consolidated view of everything you need to orient yourself:
    unread messages, recent handoffs, other agents' presence, your short-term memory,
    and current global skills for the project.
    If project_id is omitted, returns messages and presence only.
    This is the recommended first call in every working session.

    Args:
        params (SessionStartInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        agent = db.db_get_agent_by_id(conn, params.agent_id)
        if not agent:
            return _error(f"Agent '{params.agent_id}' not found.")
        now = _now()
        sections = [f"# Session Briefing — {agent['name']}\n"]

        # 1. Unread messages
        messages, msg_total = db.db_message_inbox(
            conn, params.agent_id, params.project_id, True, 5, 0, now
        )
        sections.append(f"## 📬 Messages ({msg_total} unread)")
        if not messages:
            sections.append("*No unread messages.*\n")
        else:
            for m in messages:
                priority_tag = " 🔴" if m["priority"] == "high" else ""
                broadcast_tag = " 📢" if not m.get("to_agent_name") else ""
                sections.append(f"- **{m['subject']}**{priority_tag}{broadcast_tag} — from {m['from_agent_name']} ({_fmt_ts(m['created_at'])}) `{m['id']}`")
            if msg_total > 5:
                sections.append(f"*...and {msg_total - 5} more. Use context_message_inbox to see all.*")
            sections.append("")

        # 2. Latest unacknowledged handoff (project required)
        sections.append("## 🤝 Latest Handoff")
        if not params.project_id:
            sections.append("*Provide project_id to see handoffs.*\n")
        else:
            unacked = db.db_handoff_get_recent(conn, params.project_id, 1, unacknowledged_only=True)
            if not unacked:
                sections.append("*No unacknowledged handoffs.*\n")
            else:
                h = unacked[0]
                sections.append(f"⚠️ **From {h['from_agent_name']}** — {_fmt_ts(h['created_at'])} `{h['id']}`")
                sections.append(f"{h['summary'][:300]}{'...' if len(h['summary']) > 300 else ''}")
                sections.append("*Use context_handoff_acknowledge to mark as received.*\n")

        # 3. Agent presence
        sections.append("## 👥 Team Presence")
        records = db.db_presence_get(conn, params.project_id)
        if not records:
            sections.append("*No presence records yet.*\n")
        else:
            status_icon = {"idle": "💤", "working": "⚡", "blocked": "🚫", "reviewing": "👀"}
            for r in records:
                icon = status_icon.get(r["status"], "❓")
                task = f" — {r['current_task']}" if r.get("current_task") else ""
                sections.append(f"{icon} **{r['agent_name']}** {r['status']}{task} ({_staleness(r['updated_at'])})")
            sections.append("")

        # 4. Short-term memory (project required)
        sections.append("## 🧠 Your Short-Term Memory")
        if not params.project_id:
            sections.append("*Provide project_id to see short-term memory.*\n")
        else:
            stm = db.db_stm_get_all(conn, params.agent_id, params.project_id, now)
            if not stm:
                sections.append("*No short-term memory entries.*\n")
            else:
                for e in stm:
                    sections.append(f"- **{e['key']}:** {e['value']}")
                sections.append("")

        # 5. Global skills (project required)
        sections.append(f"## 📚 Project Skills")
        if not params.project_id:
            sections.append("*Provide project_id to see project skills.*\n")
        else:
            skills, skill_total = db.db_list_global_skills(conn, params.project_id, None, None, 20, 0)
            if not skills:
                sections.append("*No global skills defined.*\n")
            else:
                sections.append(f"*{skill_total} skill(s) — use context_skill_get_global for full content.*\n")
                for s in skills:
                    scope_tag = "🌍" if s.get("scope") == "global" else "📁"
                    sections.append(f"{scope_tag} **{s['name']}** `[{s['skill_type']}]` v{s['version']} — {s['description']}")
                sections.append("")

        # 6. Sprint tasks — Option C (conditional, silent omission)
        if params.project_id:
            sprint_tasks, sprint_name = db.db_sprint_tasks_for_session(
                conn, params.agent_id, params.project_id
            )
            if sprint_tasks:
                _priority_label = {"low": "LOW", "medium": "MED", "high": "HIGH", "critical": "CRIT"}
                sections.append(f"## 📋 Your Sprint Tasks ({len(sprint_tasks)} assigned) — {sprint_name}")
                for t in sprint_tasks:
                    status_tag = t["status"].upper().replace("_", " ")
                    pri_tag    = _priority_label.get(t["priority"], t["priority"].upper())
                    line = f"- [{status_tag}] {t['title']} [{pri_tag}]"
                    if t["status"] == "blocked" and t.get("blocked_reason"):
                        line += f' — "{t["blocked_reason"]}"'
                    sections.append(line)
                sections.append("")

        return "\n".join(sections)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# SEARCH TOOL
# =============================================================================

@mcp.tool(
    name="context_search",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def context_search(params: SearchContextInput, ctx: Context) -> str:
    """
    Searches across entry content and/or thread titles using full-text search.
    Returns lightweight results with snippets only — no full content.
    After a search: use context_get_entry to read the full content of a specific entry,
    or use context_get_thread to browse all entries in a thread.
    Supports FTS5 query syntax: phrase search with quotes, prefix with *, AND/OR/NOT operators.
    Falls back to LIKE search automatically if query syntax is invalid.

    Args:
        params (SearchContextInput): The input parameters.
        ctx (Context): The fastMCP request context.

    Returns:
        str: JSON string or Markdown response.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        results = []

        if params.search_in in (SearchIn.ENTRIES, SearchIn.BOTH):
            entry_results = db.search_entries_fts(
                conn, params.query, params.project_id, params.thread_id, params.limit, params.offset
            )
            for r in entry_results:
                results.append({
                    "type": "entry",
                    "id": r["id"],
                    "thread_id": r["thread_id"],
                    "thread_title": r["thread_title"],
                    "project_id": r["project_id"],
                    "project_name": r.get("project_name", ""),
                    "agent_name": r["agent_name"],
                    "entry_type": r["type"],
                    "snippet": r["snippet"],
                    "relevance": _normalize_rank(r["rank"]),
                })

        if params.search_in in (SearchIn.THREADS, SearchIn.BOTH):
            thread_results = db.search_threads_fts(
                conn, params.query, params.project_id, params.limit, params.offset
            )
            for r in thread_results:
                results.append({
                    "type": "thread",
                    "id": r["id"],
                    "thread_id": r["thread_id"],
                    "thread_title": r["thread_title"],
                    "project_id": r["project_id"],
                    "project_name": r.get("project_name", ""),
                    "agent_name": None,
                    "entry_type": None,
                    "snippet": r["snippet"],
                    "relevance": _normalize_rank(r["rank"]),
                })

        # Sort by relevance (high > medium > low)
        rank_order = {"high": 0, "medium": 1, "low": 2}
        results.sort(key=lambda x: rank_order.get(x["relevance"], 2))

        total = len(results)
        paginated = results[params.offset: params.offset + params.limit]
        pagination = _pagination_meta(total, len(paginated), params.offset, params.limit)

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"results": paginated, **pagination}, indent=2)

        # Markdown
        if not paginated:
            return f"No results found for query: `{params.query}`"
        lines = [f"## Search Results for `{params.query}`\n"]
        for r in paginated:
            kind = r["type"].upper()
            lines.append(f"### [{kind}] {r['thread_title']}")
            lines.append(f"**Project:** {r['project_name']}  **Relevance:** {r['relevance']}")
            if r["agent_name"]:
                lines.append(f"**Agent:** {r['agent_name']}  **Type:** {r['entry_type']}")
            lines.append(f"**IDs:** thread=`{r['thread_id']}`" + (f"  entry=`{r['id']}`" if r["type"] == "entry" else ""))
            lines.append(f"\n> {r['snippet']}\n")
        start = params.offset + 1
        end = params.offset + len(paginated)
        lines.append(f"*Showing {start}–{end} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


# =============================================================================
# SPRINT BOARD TOOLS (v3)
# =============================================================================

_PRIORITY_LABEL = {"low": "[LOW]", "medium": "[MED]", "high": "[HIGH]", "critical": "[CRIT]"}


def _sprint_to_md(sprint: dict) -> str:
    tc = sprint.get("task_counts", {})
    lines = [
        f"**ID:** `{sprint['id']}`",
        f"**Status:** {sprint['status']}",
        f"**Goal:** {sprint.get('goal') or 'No goal set'}",
        f"**Dates:** {sprint.get('start_date') or '?'} to {sprint.get('end_date') or '?'}",
    ]
    if tc:
        lines.append(
            f"**Tasks:** {tc.get('total', 0)} total | "
            f"blocked={tc.get('blocked', 0)} | in_progress={tc.get('in_progress', 0)} | "
            f"done={tc.get('done', 0)}"
        )
    lines.append(f"**Created:** {_fmt_ts(sprint['created_at'])}")
    return "\n".join(lines)


@mcp.tool(
    name="context_sprint_create",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_sprint_create(params: SprintCreateInput, ctx: Context) -> str:
    """
    Create a sprint — an optional time-boxed container for tasks within a project.
    Sprints are not required. Tasks can exist in the project backlog without a sprint.
    Setting status='active' will automatically demote any currently active sprint
    in this project to 'planned'. Only one sprint per project can be active at a time.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        project = db.db_get_project_by_id(conn, params.project_id)
        if not project:
            return _error(f"Project '{params.project_id}' not found.")
        now    = _now()
        sid    = str(uuid.uuid4())
        status = params.status.value
        if status == "active":
            db.db_sprint_demote_active(conn, params.project_id, sid, now)
        sprint = db.db_sprint_create(
            conn, sid, params.project_id, params.name, params.goal,
            status, params.start_date, params.end_date, now
        )
        return json.dumps(sprint, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_sprint_list",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_sprint_list(params: SprintListInput, ctx: Context) -> str:
    """
    List sprints for a project. Returns sprint metadata including task counts per status.
    Use status='active' to find the current sprint quickly.
    """
    try:
        conn   = ctx.request_context.lifespan_context["db"]
        status = params.status.value if params.status else None
        sprints, total = db.db_sprint_list(conn, params.project_id, status, params.limit, params.offset)
        pagination = _pagination_meta(total, len(sprints), params.offset, params.limit)

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"sprints": sprints, **pagination}, indent=2)

        if not sprints:
            return "No sprints found for this project."
        lines = [f"## Sprints ({total} total)\n"]
        for s in sprints:
            lines.append(f"### {s['name']} `[{s['status'].upper()}]` `{s['id']}`")
            lines.append(_sprint_to_md(s))
            lines.append("")
        start_i = params.offset + 1
        end_i   = params.offset + len(sprints)
        lines.append(f"*Showing {start_i}–{end_i} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_sprint_update",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_sprint_update(params: SprintUpdateInput, ctx: Context) -> str:
    """
    Update a sprint's name, goal, status, or dates.
    Setting status='active' automatically demotes the current active sprint (if any)
    to 'planned'. Setting status='completed' does not affect tasks — they retain
    their current status and must be moved manually.
    """
    try:
        conn   = ctx.request_context.lifespan_context["db"]
        sprint = db.db_sprint_get_by_id(conn, params.sprint_id)
        if not sprint:
            return _error(f"Sprint '{params.sprint_id}' not found.")
        now = _now()

        fields: dict = {}
        if params.name       is not None: fields["name"]       = params.name
        if params.goal       is not None: fields["goal"]       = params.goal
        if params.start_date is not None: fields["start_date"] = params.start_date
        if params.end_date   is not None: fields["end_date"]   = params.end_date
        if params.status     is not None:
            fields["status"] = params.status.value
            if params.status == SprintStatus.ACTIVE:
                db.db_sprint_demote_active(conn, sprint["project_id"], params.sprint_id, now)

        updated = db.db_sprint_update(conn, params.sprint_id, fields, now)
        return json.dumps(updated, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_sprint_board",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_sprint_board(params: SprintBoardInput, ctx: Context) -> str:
    """
    Returns a formatted board view of all tasks in a sprint, grouped by status column.
    Omit sprint_id to automatically show the active sprint for the project.
    If no sprint is active and no sprint_id is provided, returns the project backlog.
    This is the primary tool for understanding current work state at a glance.
    Always returns markdown.
    """
    try:
        conn    = ctx.request_context.lifespan_context["db"]
        project = db.db_get_project_by_id(conn, params.project_id)
        if not project:
            return _error(f"Project '{params.project_id}' not found.")

        now = _now()
        is_backlog_view = False
        sprint = None

        if params.sprint_id:
            sprint = db.db_sprint_get_by_id(conn, params.sprint_id)
            if not sprint:
                return _error(f"Sprint '{params.sprint_id}' not found.")
            tasks = db.db_sprint_board_tasks(conn, sprint["id"])
        else:
            sprint = db.db_sprint_get_active(conn, params.project_id)
            if sprint:
                tasks = db.db_sprint_board_tasks(conn, sprint["id"])
            else:
                is_backlog_view = True
                tasks = db.db_backlog_tasks(conn, params.project_id)

        grouped: dict[str, list] = {
            "backlog": [], "todo": [], "in_progress": [],
            "blocked": [], "review": [], "done": []
        }
        for t in tasks:
            grouped.setdefault(t["status"], []).append(t)

        done_count    = len(grouped.get("done", []))
        blocked_count = len(grouped.get("blocked", []))

        if is_backlog_view:
            header = [
                "# Sprint Board: Project Backlog",
                f"**Project:** {project['name']}",
                "**Status:** No active sprint — showing unassigned backlog tasks",
                f"**Total Tasks:** {len(tasks)} | Done: {done_count} | Blocked: {blocked_count}",
            ]
        else:
            dates = f"{sprint.get('start_date') or '?'} to {sprint.get('end_date') or '?'}"
            header = [
                f"# Sprint Board: {sprint['name']}",
                f"**Project:** {project['name']}",
                f"**Goal:** {sprint.get('goal') or 'No goal set'}",
                f"**Status:** {sprint['status']}",
                f"**Dates:** {dates}",
                f"**Total Tasks:** {len(tasks)} | Done: {done_count} | Blocked: {blocked_count}",
            ]

        lines = header + ["", "---", ""]
        status_order = ["backlog", "todo", "in_progress", "blocked", "review", "done"]
        status_label = {
            "backlog": "BACKLOG", "todo": "TODO", "in_progress": "IN PROGRESS",
            "blocked": "BLOCKED", "review": "REVIEW", "done": "DONE"
        }

        for status_key in status_order:
            bucket = grouped.get(status_key, [])
            if not bucket:
                continue
            lines.append(f"## {status_label[status_key]} ({len(bucket)})")
            for t in bucket:
                assignee = t.get("assigned_to_name") or "unassigned"
                pri      = _PRIORITY_LABEL.get(t["priority"], t["priority"])
                lines.append(f"- {pri} {t['title']} — {assignee}")
                if status_key == "blocked" and t.get("blocked_reason"):
                    lines.append(f"  Reason: {t['blocked_reason']}")
                # dependency chain annotations
                deps = db.db_task_get_dependencies(conn, t["id"])
                for dep in deps["waiting_on"]:
                    if dep["status"] != "done":
                        lines.append(f"  Waiting on: \"{dep['title']}\" [{dep['status'].upper()}]")
                for dep in deps["blocks"]:
                    if dep["status"] != "done":
                        lines.append(f"  Blocks: \"{dep['title']}\" [{dep['status'].upper()}]")
            lines.append("")

        lines.append(f"---\n*Board generated at {_fmt_ts(now)}*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_task_create",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_task_create(params: TaskCreateInput, ctx: Context) -> str:
    """
    Create a task. Tasks land in the project backlog by default (no sprint required).
    Assign to a sprint via sprint_id. Link to a discussion thread via thread_id.
    status defaults to 'backlog'. If setting status='blocked' on creation,
    blocked_reason is required.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        if not db.db_get_project_by_id(conn, params.project_id):
            return _error(f"Project '{params.project_id}' not found.")
        if not db.db_get_agent_by_id(conn, params.created_by):
            return _error(f"Agent '{params.created_by}' not found.")
        if params.sprint_id:
            sprint = db.db_sprint_get_by_id(conn, params.sprint_id)
            if not sprint:
                return _error(f"Sprint '{params.sprint_id}' not found.")
            if sprint["project_id"] != params.project_id:
                return _error("Sprint does not belong to the given project.")
        if params.assigned_to and not db.db_get_agent_by_id(conn, params.assigned_to):
            return _error(f"Agent '{params.assigned_to}' not found.")
        if params.status == TaskStatus.BLOCKED and not params.blocked_reason:
            return _error("blocked_reason is required when status is 'blocked'.")

        now  = _now()
        task = db.db_task_create(
            conn, str(uuid.uuid4()), params.project_id, params.sprint_id,
            params.title, params.description, params.status.value,
            params.assigned_to, params.created_by, params.priority.value,
            params.blocked_reason, params.thread_id, params.due_date, now
        )
        return json.dumps(task, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_task_get",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_task_get(params: TaskGetInput, ctx: Context) -> str:
    """
    Retrieve a single task by UUID. Returns all fields with resolved agent names,
    sprint name, and project name for full context.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        task = db.db_task_get_full(conn, params.task_id)
        if not task:
            return _error(f"Task '{params.task_id}' not found. Use context_task_list to browse tasks.")

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(task, indent=2)

        pri = _PRIORITY_LABEL.get(task["priority"], task["priority"])
        lines = [
            f"## {task['title']} {pri}",
            f"**ID:** `{task['id']}`",
            f"**Status:** {task['status']}",
            f"**Project:** {task.get('project_name', task['project_id'])}",
            f"**Sprint:** {task.get('sprint_name') or 'Backlog'}",
            f"**Assigned to:** {task.get('assigned_to_name') or 'Unassigned'}",
            f"**Created by:** {task.get('created_by_name', task['created_by'])}",
            f"**Due:** {task.get('due_date') or 'No due date'}",
            f"**Created:** {_fmt_ts(task['created_at'])}",
            f"**Updated:** {_fmt_ts(task['updated_at'])}",
        ]
        if task.get("thread_title"):
            lines.append(f"**Thread:** {task['thread_title']} `{task['thread_id']}`")
        if task["status"] == "blocked" and task.get("blocked_reason"):
            lines.append(f"**Blocked reason:** {task['blocked_reason']}")
        if task.get("description"):
            lines.append(f"\n### Description\n{task['description']}")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_task_list",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_task_list(params: TaskListInput, ctx: Context) -> str:
    """
    List tasks for a project with optional filters.
    Omit sprint_id to see all tasks including backlog.
    Pass sprint_id='backlog' to see only tasks not assigned to any sprint.
    Filter by assigned_to with your agent UUID to see your personal workload.
    Results ordered by: priority (critical first), then created_at.
    """
    try:
        conn     = ctx.request_context.lifespan_context["db"]
        status   = params.status.value if params.status else None
        priority = params.priority.value if params.priority else None

        tasks, total = db.db_task_list(
            conn, params.project_id, params.sprint_id,
            status, params.assigned_to, priority,
            params.limit, params.offset
        )
        pagination = _pagination_meta(total, len(tasks), params.offset, params.limit)

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"tasks": tasks, **pagination}, indent=2)

        if not tasks:
            return "No tasks found matching the given filters."

        lines = [f"## Tasks ({total} total)\n"]
        for t in tasks:
            pri      = _PRIORITY_LABEL.get(t["priority"], t["priority"])
            assignee = t.get("assigned_to_name") or "unassigned"
            sprint_n = t.get("sprint_name", "Backlog")
            lines.append(f"- {pri} **{t['title']}** `{t['status']}` — {assignee} [{sprint_n}] `{t['id']}`")
            if t["status"] == "blocked" and t.get("blocked_reason"):
                lines.append(f"  ⚠️ {t['blocked_reason']}")
        start_i = params.offset + 1
        end_i   = params.offset + len(tasks)
        lines.append(f"\n*Showing {start_i}–{end_i} of {total}*")
        if pagination["has_more"]:
            lines.append(f"*Use offset={pagination['next_offset']} for next page.*")
        return "\n".join(lines)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_task_update",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
async def context_task_update(params: TaskUpdateInput, ctx: Context) -> str:
    """
    Update any field on a task. Partial update — only provided fields are changed.
    Free-flow transitions: any status can move to any other status.
    IMPORTANT: If setting status='blocked', blocked_reason is required.
    If moving away from 'blocked' to any other status, blocked_reason is
    automatically cleared.
    To move a task to the backlog, pass sprint_id as an empty string.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        task = db.db_task_get_by_id(conn, params.task_id)
        if not task:
            return _error(f"Task '{params.task_id}' not found.")
        now = _now()

        if params.status == TaskStatus.BLOCKED:
            if not params.blocked_reason and not task.get("blocked_reason"):
                return _error("blocked_reason is required when setting status to 'blocked'.")

        if params.status == TaskStatus.IN_PROGRESS:
            blocking = conn.execute(
                """SELECT t.id, t.title, t.status
                   FROM task_dependencies td
                   JOIN tasks t ON td.depends_on = t.id
                   WHERE td.task_id = ? AND t.status != 'done'""",
                (params.task_id,)
            ).fetchall()
            if blocking:
                titles = ", ".join(f"'{r['title']}' ({r['status']})" for r in blocking)
                return _error(
                    f"Cannot move to in_progress: blocked by {len(blocking)} unfinished "
                    f"task(s): {titles}. Complete those first or remove the dependencies."
                )

        fields: dict = {}
        if params.title       is not None: fields["title"]       = params.title
        if params.description is not None: fields["description"] = params.description
        if params.priority    is not None: fields["priority"]    = params.priority.value
        if params.thread_id   is not None: fields["thread_id"]   = params.thread_id
        if params.due_date    is not None: fields["due_date"]    = params.due_date

        if params.sprint_id is not None:
            fields["sprint_id"] = None if params.sprint_id == "" else params.sprint_id

        if params.status is not None:
            new_status = params.status.value
            fields["status"] = new_status
            if task["status"] == "blocked" and new_status != "blocked":
                fields["blocked_reason"] = None
            elif new_status == "blocked" and params.blocked_reason:
                fields["blocked_reason"] = params.blocked_reason
        elif params.blocked_reason is not None:
            fields["blocked_reason"] = params.blocked_reason

        updated = db.db_task_update(conn, params.task_id, fields, now)
        return json.dumps(updated, indent=2)
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_task_assign",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_task_assign(params: TaskAssignInput, ctx: Context) -> str:
    """
    Assign a task to an agent, or unassign it by omitting agent_id.
    Dedicated tool for assignment — cleaner than calling context_task_update
    just to change the assignee.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]
        task = db.db_task_get_by_id(conn, params.task_id)
        if not task:
            return _error(f"Task '{params.task_id}' not found.")
        agent_name = None
        if params.agent_id:
            agent = db.db_get_agent_by_id(conn, params.agent_id)
            if not agent:
                return _error(f"Agent '{params.agent_id}' not found.")
            agent_name = agent["name"]
        db.db_task_assign(conn, params.task_id, params.agent_id, _now())
        if agent_name:
            return f"Task '{task['title']}' assigned to {agent_name}."
        return f"Task '{task['title']}' unassigned."
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_task_delete",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
async def context_task_delete(params: TaskDeleteInput, ctx: Context) -> str:
    """
    Permanently delete a task. This cannot be undone.
    Consider setting status='done' instead if you want to preserve history.
    """
    try:
        conn  = ctx.request_context.lifespan_context["db"]
        title = db.db_task_delete(conn, params.task_id)
        if title is None:
            return "Task not found — nothing deleted."
        return f"Task '{title}' permanently deleted."
    except Exception as e:
        return _error(str(e))


# =============================================================================
# V4 Tools — Task Dependencies + Sprint Retrospective
# =============================================================================

@mcp.tool(
    name="context_task_add_dependency",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_task_add_dependency(params: TaskAddDependencyInput, ctx: Context) -> str:
    """
    Add a dependency between two tasks. task_id will be blocked by depends_on —
    meaning task_id cannot move to 'in_progress' while depends_on is not 'done'.
    Circular dependencies are rejected automatically.
    Idempotent: adding an existing dependency returns success silently.
    Both tasks must belong to the same project.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]

        task       = db.db_task_get_full(conn, params.task_id)
        dep_task   = db.db_task_get_full(conn, params.depends_on)

        if not task:
            return _error(f"Task '{params.task_id}' not found.")
        if not dep_task:
            return _error(f"Task '{params.depends_on}' not found.")
        if task["project_id"] != dep_task["project_id"]:
            return _error("Both tasks must belong to the same project.")
        if params.task_id == params.depends_on:
            return _error("A task cannot depend on itself.")
        if not db.db_get_agent_by_id(conn, params.created_by):
            return _error(f"Agent '{params.created_by}' not found.")

        if db.would_create_cycle(conn, params.task_id, params.depends_on):
            return _error("Cannot add dependency: would create a circular dependency chain.")

        try:
            db.db_task_add_dependency(conn, str(uuid.uuid4()), params.task_id, params.depends_on,
                                      params.created_by, _now())
        except sqlite3.IntegrityError:
            pass  # already exists — idempotent

        return f"Task '{task['title']}' now depends on '{dep_task['title']}'."
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_task_remove_dependency",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
)
async def context_task_remove_dependency(params: TaskRemoveDependencyInput, ctx: Context) -> str:
    """
    Remove a dependency between two tasks.
    Idempotent: if the dependency does not exist, returns a 'not found' message without error.
    """
    try:
        conn     = ctx.request_context.lifespan_context["db"]
        task     = db.db_task_get_full(conn, params.task_id)
        dep_task = db.db_task_get_full(conn, params.depends_on)

        if not task:
            return _error(f"Task '{params.task_id}' not found.")
        if not dep_task:
            return _error(f"Task '{params.depends_on}' not found.")

        removed = db.db_task_remove_dependency(conn, params.task_id, params.depends_on)
        if not removed:
            return "Dependency not found — nothing removed."
        return f"Dependency removed. Task '{task['title']}' no longer depends on '{dep_task['title']}'."
    except Exception as e:
        return _error(str(e))


@mcp.tool(
    name="context_sprint_close",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def context_sprint_close(params: SprintCloseInput, ctx: Context) -> str:
    """
    Close a sprint and automatically generate a structured retrospective.
    Computes what shipped, what carried over, what got blocked and why,
    which agents participated, and how long the sprint ran.
    Posts the retrospective as a pinned 'decision' entry in a new dedicated thread.
    Sets sprint status to 'completed'.
    Also posts a handoff note so the next session picks up with full context.
    Idempotent: if sprint is already completed, returns the existing retrospective thread link.
    """
    try:
        conn = ctx.request_context.lifespan_context["db"]

        sprint = db.db_sprint_get_by_id(conn, params.sprint_id)
        if not sprint:
            return _error(f"Sprint '{params.sprint_id}' not found.")

        if sprint["status"] == "completed":
            return f"Sprint '{sprint['name']}' is already closed."

        agent = db.db_get_agent_by_id(conn, params.closed_by)
        if not agent:
            return _error(f"Agent '{params.closed_by}' not found.")

        retro = db.db_sprint_retro_data(conn, params.sprint_id)
        tasks_by_status = retro["tasks_by_status"]
        project         = retro["project"]

        done_tasks    = tasks_by_status.get("done", [])
        blocked_tasks = tasks_by_status.get("blocked", [])
        carried_over  = [t for t in retro["all_tasks"] if t["status"] != "done"]
        agent_names   = [a["name"] for a in retro["agents"]] or ["(none)"]

        now        = _now()
        close_date = now[:10]
        start_date = sprint.get("start_date") or sprint["created_at"][:10]
        try:
            from datetime import date
            delta = (date.fromisoformat(close_date) - date.fromisoformat(start_date)).days
            duration = f"{start_date} to {close_date} ({delta} day{'s' if delta != 1 else ''})"
        except Exception:
            duration = f"{start_date} to {close_date}"

        def task_line(t):
            name = t.get("assigned_to_name") or "unassigned"
            return f"- {t['title']} — {name}"

        retro_lines = [
            f"# Sprint Retrospective: {sprint['name']}",
            "",
            f"**Project:** {project.get('name', '?')}",
            f"**Closed by:** {agent['name']}",
            f"**Duration:** {duration}",
            f"**Goal:** {sprint.get('goal') or 'No goal set'}",
            "",
            "---",
            "",
            f"## What Shipped ({len(done_tasks)} tasks)",
        ]
        if done_tasks:
            retro_lines += [task_line(t) for t in done_tasks]
        else:
            retro_lines.append("- (none)")

        retro_lines += ["", f"## Carried Over ({len(carried_over)} tasks)"]
        if carried_over:
            for t in carried_over:
                name = t.get("assigned_to_name") or "unassigned"
                retro_lines.append(f"- {t['title']} [{t['status']}] — {name}")
        else:
            retro_lines.append("- (none)")

        retro_lines += ["", f"## Blocked at Close ({len(blocked_tasks)} tasks)"]
        if blocked_tasks:
            for t in blocked_tasks:
                name = t.get("assigned_to_name") or "unassigned"
                retro_lines.append(f"- {t['title']} — {name}")
                if t.get("blocked_reason"):
                    retro_lines.append(f"  Reason: {t['blocked_reason']}")
        else:
            retro_lines.append("- (none)")

        retro_lines += [
            "",
            "## Participants",
            ", ".join(agent_names),
            "",
            "## Notes",
            params.notes if params.notes else "No additional notes.",
            "",
            "---",
            f"*Retrospective generated {_fmt_ts(now)} UTC by {agent['name']}*",
        ]
        retro_md = "\n".join(retro_lines)

        # Create a dedicated retrospective thread and pin the entry
        retro_thread_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO threads (id, project_id, title, status, created_at) VALUES (?, ?, ?, 'open', ?)",
            (retro_thread_id, sprint["project_id"], f"{sprint['name']} — Retrospective", now)
        )
        entry_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO entries (id, thread_id, agent_id, type, content, pinned, created_at, updated_at) VALUES (?, ?, ?, 'decision', ?, 1, ?, ?)",
            (entry_id, retro_thread_id, params.closed_by, retro_md, now, now)
        )

        # Mark sprint completed
        conn.execute(
            "UPDATE sprints SET status = 'completed', updated_at = ? WHERE id = ?",
            (now, params.sprint_id)
        )
        conn.commit()

        # Post handoff
        carried_titles = ", ".join(t["title"] for t in carried_over) if carried_over else "none"
        conn.execute(
            """INSERT INTO handoffs
               (id, from_agent_id, project_id, summary, in_progress, blockers, next_steps, thread_refs, acknowledged_by, acknowledged_at, created_at)
               VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, ?)""",
            (
                str(uuid.uuid4()), params.closed_by, sprint["project_id"],
                retro_md[:500],
                f"Carry over: {carried_titles}",
                json.dumps([retro_thread_id]),
                now,
            )
        )
        conn.commit()

        return retro_md
    except Exception as e:
        return _error(str(e))
