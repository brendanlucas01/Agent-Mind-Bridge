"""
Pydantic models and enumerations for the MCP communicator.

Provides data validation and type definitions for shared context resources like projects, agents, threads, and memories.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from enum import Enum


class ResponseFormat(str, Enum):
    """
    Response format options.
    """
    MARKDOWN = "markdown"
    JSON = "json"


class AgentType(str, Enum):
    """
    Available agent types.
    """
    CLAUDE = "claude"
    GEMINI = "gemini"
    OPENAI = "openai"
    HUMAN = "human"
    OTHER = "other"


class EntryType(str, Enum):
    """
    Types of entries available in a thread.
    """
    PROPOSAL = "proposal"
    FEEDBACK = "feedback"
    DECISION = "decision"
    NOTE = "note"


class ProjectStatus(str, Enum):
    """
    Status of a project.
    """
    ACTIVE = "active"
    ARCHIVED = "archived"


class ThreadStatus(str, Enum):
    """
    Status of a thread.
    """
    OPEN = "open"
    RESOLVED = "resolved"


class SearchIn(str, Enum):
    """
    Search scope limits.
    """
    ENTRIES = "entries"
    THREADS = "threads"
    BOTH = "both"


# --- Project Models ---

class CreateProjectInput(BaseModel):
    """
    Input model for CreateProject.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(..., description="Unique project name (e.g. 'browser-extension', 'job-board')", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Optional project description", max_length=500)


class ListProjectsInput(BaseModel):
    """
    Input model for ListProjects.
    """
    model_config = ConfigDict(extra='forbid')
    status: Optional[ProjectStatus] = Field(None, description="Filter by status: 'active' or 'archived'. Omit for all.")
    limit: int = Field(default=20, ge=1, le=100, description="Max results to return")
    offset: int = Field(default=0, ge=0, description="Number of results to skip")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="'markdown' for readable output, 'json' for structured data")


class GetProjectInput(BaseModel):
    """
    Input model for GetProject.
    """
    model_config = ConfigDict(extra='forbid')
    project_id: str = Field(..., description="Project UUID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ArchiveProjectInput(BaseModel):
    """
    Input model for ArchiveProject.
    """
    model_config = ConfigDict(extra='forbid')
    project_id: str = Field(..., description="Project UUID to archive")


# --- Agent Models ---

class RegisterAgentInput(BaseModel):
    """
    Input model for RegisterAgent.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(..., description="Unique agent name (e.g. 'claude-code', 'gemini-antigravity')", min_length=1, max_length=100)
    type: AgentType = Field(..., description="Agent type: 'claude' | 'gemini' | 'openai' | 'human' | 'other'")
    description: Optional[str] = Field(None, description="Optional description of this agent's role", max_length=300)


class ListAgentsInput(BaseModel):
    """
    Input model for ListAgents.
    """
    model_config = ConfigDict(extra='forbid')
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetAgentInput(BaseModel):
    """
    Input model for GetAgent.
    """
    model_config = ConfigDict(extra='forbid')
    agent_id: str = Field(..., description="Agent UUID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Thread Models ---

class CreateThreadInput(BaseModel):
    """
    Input model for CreateThread.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    project_id: str = Field(..., description="Project UUID this thread belongs to")
    title: str = Field(..., description="Thread title describing the topic or task", min_length=1, max_length=200)


class ListThreadsInput(BaseModel):
    """
    Input model for ListThreads.
    """
    model_config = ConfigDict(extra='forbid')
    project_id: Optional[str] = Field(None, description="Filter by project UUID. Omit for all projects.")
    status: Optional[ThreadStatus] = Field(None, description="Filter by 'open' or 'resolved'. Omit for all.")
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetThreadInput(BaseModel):
    """
    Input model for GetThread.
    """
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
    """
    Input model for ResolveThread.
    """
    model_config = ConfigDict(extra='forbid')
    thread_id: str = Field(..., description="Thread UUID to mark as resolved")


class ExportThreadInput(BaseModel):
    """
    Input model for ExportThread.
    """
    model_config = ConfigDict(extra='forbid')
    thread_id: str = Field(..., description="Thread UUID to export as a markdown document")


# --- Entry Models ---

class PostEntryInput(BaseModel):
    """
    Input model for PostEntry.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    thread_id: str = Field(..., description="Thread UUID to post into")
    agent_id: str = Field(..., description="Agent UUID of the author")
    type: EntryType = Field(..., description="Entry type: 'proposal' | 'feedback' | 'decision' | 'note'")
    content: str = Field(..., description="The entry content (markdown supported)", min_length=1, max_length=50000)
    reply_to: Optional[str] = Field(None, description="Optional entry UUID this is a reply to")


class UpdateEntryInput(BaseModel):
    """
    Input model for UpdateEntry.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    entry_id: str = Field(..., description="Entry UUID to update")
    content: str = Field(..., description="New content to replace the existing content", min_length=1, max_length=50000)


class PinEntryInput(BaseModel):
    """
    Input model for PinEntry.
    """
    model_config = ConfigDict(extra='forbid')
    entry_id: str = Field(..., description="Entry UUID to pin or unpin")
    pinned: bool = Field(..., description="True to pin/star, False to unpin")


class GetEntryInput(BaseModel):
    """
    Input model for GetEntry.
    """
    model_config = ConfigDict(extra='forbid')
    entry_id: str = Field(..., description="Entry UUID to retrieve")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Memory Enums ---

GLOBAL_SENTINEL = "__global__"

class Confidence(str, Enum):
    """
    Confidence levels for memory entries.
    """
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"

class MemoryScope(str, Enum):
    """
    Scope configurations for memory entries.
    """
    AGENT_PROJECT = "agent_project"
    PROJECT       = "project"
    GLOBAL        = "global"


# --- Short-Term Memory Models ---

class MemorySetShortInput(BaseModel):
    """
    Input model for MemorySetShort.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:   str           = Field(..., description="Agent UUID")
    project_id: str           = Field(..., description="Project UUID, or '__global__' for cross-project scope")
    key:        str           = Field(..., description="Memory key", min_length=1, max_length=200)
    value:      str           = Field(..., description="Memory value", min_length=1, max_length=10000)
    expires_at: Optional[str] = Field(None, description="Optional ISO timestamp when this memory expires")


class MemoryGetShortInput(BaseModel):
    """
    Input model for MemoryGetShort.
    """
    model_config = ConfigDict(extra='forbid')
    agent_id:        str            = Field(..., description="Agent UUID")
    project_id:      str            = Field(..., description="Project UUID, or '__global__' for cross-project scope")
    key:             Optional[str]  = Field(None, description="Specific key to retrieve. Omit to get all keys in scope.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class MemoryClearShortInput(BaseModel):
    """
    Input model for MemoryClearShort.
    """
    model_config = ConfigDict(extra='forbid')
    agent_id:   str = Field(..., description="Agent UUID")
    project_id: str = Field(..., description="Project UUID, or '__global__' for cross-project scope")


# --- Long-Term Memory Models ---

class MemorySetLongInput(BaseModel):
    """
    Input model for MemorySetLong.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:         str           = Field(default=GLOBAL_SENTINEL, description="Agent UUID, or '__global__' for non-agent-specific memory")
    project_id:       str           = Field(..., description="Project UUID, or '__global__' for cross-project memory")
    key:              str           = Field(..., description="Memory key", min_length=1, max_length=200)
    value:            str           = Field(..., description="Memory value", min_length=1, max_length=50000)
    tags:             Optional[str] = Field(None, description="Comma-separated tags")
    confidence:       Confidence    = Field(default=Confidence.MEDIUM)
    source_thread_id: Optional[str] = Field(None, description="Thread UUID where this fact was learned")


class MemoryGetLongInput(BaseModel):
    """
    Input model for MemoryGetLong.
    """
    model_config = ConfigDict(extra='forbid')
    agent_id:        str            = Field(default=GLOBAL_SENTINEL, description="Agent UUID, or '__global__'")
    project_id:      str            = Field(..., description="Project UUID, or '__global__'")
    key:             Optional[str]  = Field(None, description="Specific key. Omit to browse all memories in scope.")
    tags:            Optional[str]  = Field(None, description="Filter by tag")
    limit:           int            = Field(default=20, ge=1, le=100)
    offset:          int            = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class MemoryDeleteLongInput(BaseModel):
    """
    Input model for MemoryDeleteLong.
    """
    model_config = ConfigDict(extra='forbid')
    memory_id: str = Field(..., description="Long-term memory UUID to delete")


class MemorySearchInput(BaseModel):
    """
    Input model for MemorySearch.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    query:           str            = Field(..., description="FTS5 search query across memory values", min_length=1, max_length=300)
    agent_id:        str            = Field(default=GLOBAL_SENTINEL, description="Agent UUID, or '__global__'")
    project_id:      str            = Field(..., description="Project UUID, or '__global__'")
    limit:           int            = Field(default=10, ge=1, le=50)
    offset:          int            = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class MemoryPromoteInput(BaseModel):
    """
    Input model for MemoryPromote.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:         str           = Field(..., description="Agent UUID (owner of the short-term memory)")
    project_id:       str           = Field(..., description="Project UUID of the short-term memory, or '__global__'")
    key:              str           = Field(..., description="Short-term memory key to promote")
    target_scope:     MemoryScope   = Field(..., description="'agent_project' | 'project' | 'global'")
    override_value:   Optional[str] = Field(None, description="Rewrite the value when promoting. Omit to use current value as-is.")
    tags:             Optional[str] = Field(None)
    confidence:       Confidence    = Field(default=Confidence.MEDIUM)
    source_thread_id: Optional[str] = Field(None)
    clear_after:      bool          = Field(default=True, description="Delete the short-term entry after promoting. Default: true.")


# --- Skill Enums ---

class SkillType(str, Enum):
    """
    Supported skill types.
    """
    INSTRUCTION = "instruction"
    PROCEDURE   = "procedure"
    TEMPLATE    = "template"
    PATTERN     = "pattern"


# --- Personal Skill Models ---

class SkillCreatePersonalInput(BaseModel):
    """
    Input model for SkillCreatePersonal.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:    str           = Field(..., description="Agent UUID — owner of this skill")
    name:        str           = Field(..., description="Unique skill name for this agent", min_length=1, max_length=100)
    skill_type:  SkillType     = Field(..., description="'instruction' | 'procedure' | 'template' | 'pattern'")
    description: str           = Field(..., description="One-line summary used for discovery and search", min_length=1, max_length=300)
    content:     str           = Field(..., description="Full skill content", min_length=1, max_length=50000)
    tags:        Optional[str] = Field(None, description="Comma-separated tags")


class SkillGetPersonalInput(BaseModel):
    """
    Input model for SkillGetPersonal.
    """
    model_config = ConfigDict(extra='forbid')
    agent_id:        str            = Field(..., description="Agent UUID")
    name:            str            = Field(..., description="Skill name to retrieve")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SkillListPersonalInput(BaseModel):
    """
    Input model for SkillListPersonal.
    """
    model_config = ConfigDict(extra='forbid')
    agent_id:        str                 = Field(..., description="Agent UUID")
    skill_type:      Optional[SkillType] = Field(None, description="Filter by type")
    tags:            Optional[str]       = Field(None, description="Filter by tag (single tag)")
    limit:           int                 = Field(default=20, ge=1, le=100)
    offset:          int                 = Field(default=0, ge=0)
    response_format: ResponseFormat      = Field(default=ResponseFormat.MARKDOWN)


class SkillUpdatePersonalInput(BaseModel):
    """
    Input model for SkillUpdatePersonal.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    skill_id:    str           = Field(..., description="Personal skill UUID")
    description: Optional[str] = Field(None, description="Updated one-line description", max_length=300)
    content:     Optional[str] = Field(None, description="Updated skill content", max_length=50000)
    tags:        Optional[str] = Field(None, description="Updated comma-separated tags")


class SkillDeletePersonalInput(BaseModel):
    """
    Input model for SkillDeletePersonal.
    """
    model_config = ConfigDict(extra='forbid')
    skill_id: str = Field(..., description="Personal skill UUID to delete")


# --- Global Skill Models ---

class SkillCreateGlobalInput(BaseModel):
    """
    Input model for SkillCreateGlobal.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    project_id:  Optional[str] = Field(None, description="Project UUID. Omit for a truly global skill.")
    name:        str           = Field(..., description="Unique skill name within this scope", min_length=1, max_length=100)
    skill_type:  SkillType     = Field(..., description="'instruction' | 'procedure' | 'template' | 'pattern'")
    description: str           = Field(..., description="One-line summary", min_length=1, max_length=300)
    content:     str           = Field(..., description="Full skill content — all agents will follow this", min_length=1, max_length=50000)
    tags:        Optional[str] = Field(None, description="Comma-separated tags")
    created_by:  str           = Field(..., description="Agent UUID creating this skill")


class SkillGetGlobalInput(BaseModel):
    """
    Input model for SkillGetGlobal.
    """
    model_config = ConfigDict(extra='forbid')
    name:            str            = Field(..., description="Skill name to retrieve")
    project_id:      Optional[str]  = Field(None, description="Project UUID. Resolution: project-scoped first, then global fallback.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SkillListGlobalInput(BaseModel):
    """
    Input model for SkillListGlobal.
    """
    model_config = ConfigDict(extra='forbid')
    project_id:      Optional[str]       = Field(None, description="Project UUID. Returns project-scoped AND global skills. Omit for global-only.")
    skill_type:      Optional[SkillType] = Field(None, description="Filter by type")
    tags:            Optional[str]       = Field(None, description="Filter by tag")
    limit:           int                 = Field(default=20, ge=1, le=100)
    offset:          int                 = Field(default=0, ge=0)
    response_format: ResponseFormat      = Field(default=ResponseFormat.MARKDOWN)


class SkillUpdateGlobalInput(BaseModel):
    """
    Input model for SkillUpdateGlobal.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    skill_id:    str           = Field(..., description="Global skill UUID")
    description: Optional[str] = Field(None, max_length=300)
    content:     Optional[str] = Field(None, max_length=50000)
    tags:        Optional[str] = Field(None)


class SkillDeleteGlobalInput(BaseModel):
    """
    Input model for SkillDeleteGlobal.
    """
    model_config = ConfigDict(extra='forbid')
    skill_id: str = Field(..., description="Global skill UUID to delete")


class SkillSearchInput(BaseModel):
    """
    Input model for SkillSearch.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    query:           str            = Field(..., description="FTS5 search query across skill descriptions and content", min_length=1, max_length=300)
    agent_id:        Optional[str]  = Field(None, description="Include personal skills for this agent in results")
    project_id:      Optional[str]  = Field(None, description="Include project-scoped and global skills in results")
    limit:           int            = Field(default=10, ge=1, le=50)
    offset:          int            = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Collaboration Enums ---

class AgentStatus(str, Enum):
    """
    Data model for AgentStatus.
    """
    IDLE      = "idle"
    WORKING   = "working"
    BLOCKED   = "blocked"
    REVIEWING = "reviewing"


class MessagePriority(str, Enum):
    """
    Data model for MessagePriority.
    """
    LOW    = "low"
    NORMAL = "normal"
    HIGH   = "high"


# --- Message Models ---

class MessageSendInput(BaseModel):
    """
    Input model for MessageSend.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    from_agent_id: str                  = Field(..., description="Sending agent UUID")
    to_agent_id:   Optional[str]        = Field(None, description="Recipient agent UUID. Omit to broadcast to all agents.")
    project_id:    Optional[str]        = Field(None, description="Project UUID to scope this message")
    subject:       str                  = Field(..., description="Message subject", min_length=1, max_length=200)
    content:       str                  = Field(..., description="Message body", min_length=1, max_length=10000)
    priority:      MessagePriority      = Field(default=MessagePriority.NORMAL, description="'low' | 'normal' | 'high'")
    thread_ref:    Optional[str]        = Field(None, description="Thread UUID this message relates to")


class MessageInboxInput(BaseModel):
    """
    Input model for MessageInbox.
    """
    model_config = ConfigDict(extra='forbid')
    agent_id:        str            = Field(..., description="Agent UUID to fetch inbox for")
    project_id:      Optional[str]  = Field(None, description="Filter to a specific project. Omit for full inbox across all projects.")
    unread_only:     bool           = Field(default=True, description="True returns only unread messages (default). False returns full history.")
    limit:           int            = Field(default=20, ge=1, le=100)
    offset:          int            = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class MessageReadInput(BaseModel):
    """
    Input model for MessageRead.
    """
    model_config = ConfigDict(extra='forbid')
    message_id:      str            = Field(..., description="Message UUID to retrieve and mark as read")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Presence Models ---

class PresenceUpdateInput(BaseModel):
    """
    Input model for PresenceUpdate.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    agent_id:     str            = Field(..., description="Agent UUID")
    project_id:   str            = Field(default="__global__", description="Project UUID, or '__global__' for general presence")
    status:       AgentStatus    = Field(..., description="'idle' | 'working' | 'blocked' | 'reviewing'")
    current_task: Optional[str]  = Field(None, description="What this agent is currently doing", max_length=500)


class PresenceGetInput(BaseModel):
    """
    Input model for PresenceGet.
    """
    model_config = ConfigDict(extra='forbid')
    project_id:      Optional[str]  = Field(None, description="Project UUID. Returns project-specific AND global presence. Omit for all agents.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Handoff Models ---

class HandoffPostInput(BaseModel):
    """
    Input model for HandoffPost.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    from_agent_id: str                  = Field(..., description="Agent UUID posting this handoff")
    project_id:    str                  = Field(..., description="Project UUID this handoff is for")
    summary:       str                  = Field(..., description="What was accomplished this session", min_length=1, max_length=5000)
    in_progress:   Optional[str]        = Field(None, description="What's half-done", max_length=2000)
    blockers:      Optional[str]        = Field(None, description="What's stuck and why", max_length=2000)
    next_steps:    Optional[str]        = Field(None, description="Suggested actions for the next agent", max_length=2000)
    thread_refs:   Optional[list[str]]  = Field(None, description="List of thread UUIDs relevant to this handoff")


class HandoffGetInput(BaseModel):
    """
    Input model for HandoffGet.
    """
    model_config = ConfigDict(extra='forbid')
    project_id:      str            = Field(..., description="Project UUID")
    limit:           int            = Field(default=5, ge=1, le=20, description="Number of recent handoffs to return")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class HandoffAcknowledgeInput(BaseModel):
    """
    Input model for HandoffAcknowledge.
    """
    model_config = ConfigDict(extra='forbid')
    handoff_id: str = Field(..., description="Handoff UUID to acknowledge")
    agent_id:   str = Field(..., description="Agent UUID acknowledging this handoff")


# --- Session Start Model ---

class SessionStartInput(BaseModel):
    """
    Input model for SessionStart.
    """
    model_config = ConfigDict(extra='forbid')
    agent_id:        str            = Field(..., description="Your agent UUID")
    project_id:      Optional[str]  = Field(None, description="Project UUID you're working on. Omit for messages + presence only.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Help Model ---

class HelpInput(BaseModel):
    """
    Input model for Help.
    """
    model_config = ConfigDict(extra='forbid')
    topic:           Optional[str]  = Field(None, description="Filter by pillar ('core', 'memory', 'skills', 'collaboration') or keyword. Omit for full index.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# --- Search Models ---

class SearchContextInput(BaseModel):
    """
    Input model for SearchContext.
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    query: str = Field(..., description="Search query. Supports FTS5 syntax: phrases in quotes, prefix with *, AND/OR/NOT operators.", min_length=1, max_length=500)
    project_id: Optional[str] = Field(None, description="Scope search to a specific project UUID")
    thread_id: Optional[str] = Field(None, description="Scope search to a specific thread UUID")
    search_in: SearchIn = Field(default=SearchIn.BOTH, description="'entries' | 'threads' | 'both'")
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)
