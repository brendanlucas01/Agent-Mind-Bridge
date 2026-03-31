"""
Database access layer for the MCP communicator.

Provides SQLite database initialization and querying functions.
"""
import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL,
            archived_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agents (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            type        TEXT NOT NULL,
            description TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS threads (
            id          TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL REFERENCES projects(id),
            title       TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'open',
            created_at  TEXT NOT NULL,
            resolved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS entries (
            id          TEXT PRIMARY KEY,
            thread_id   TEXT NOT NULL REFERENCES threads(id),
            agent_id    TEXT NOT NULL REFERENCES agents(id),
            type        TEXT NOT NULL,
            content     TEXT NOT NULL,
            reply_to    TEXT REFERENCES entries(id),
            pinned      INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_threads_project ON threads(project_id);
        CREATE INDEX IF NOT EXISTS idx_entries_thread ON entries(thread_id);
        CREATE INDEX IF NOT EXISTS idx_entries_agent ON entries(agent_id);
        CREATE INDEX IF NOT EXISTS idx_entries_pinned ON entries(thread_id, pinned);

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
    """)
    conn.commit()


# --- Project queries ---

def db_create_project(conn, id, name, description, created_at) -> dict:
    """
    Create a new project record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (Any): The id parameter.
        name (Any): The name parameter.
        description (Any): The description parameter.
        created_at (Any): The created_at parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        "INSERT INTO projects (id, name, description, status, created_at) VALUES (?, ?, ?, 'active', ?)",
        (id, name, description, created_at)
    )
    conn.commit()
    return db_get_project_by_id(conn, id)


def db_get_project_by_id(conn, project_id) -> dict | None:
    """
    Retrieve a project record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        project_id (Any): The project_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


def db_get_project_by_name(conn, name) -> dict | None:
    """
    Retrieve a project record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        name (Any): The name parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def db_list_projects(conn, status, limit, offset) -> tuple[list[dict], int]:
    """
    List projects records from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        status (Any): The status parameter.
        limit (Any): The limit parameter.
        offset (Any): The offset parameter.

    Returns:
        tuple[list[dict], int]: The result of the operation.
    """
    if status:
        total = conn.execute("SELECT COUNT(*) FROM projects WHERE status = ?", (status,)).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM projects WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status, limit, offset)
        ).fetchall()
    else:
        total = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows], total


def db_archive_project(conn, project_id, archived_at) -> dict | None:
    """
    Execute database operation for db_archive_project.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        project_id (Any): The project_id parameter.
        archived_at (Any): The archived_at parameter.

    Returns:
        dict | None: The result of the operation.
    """
    conn.execute(
        "UPDATE projects SET status = 'archived', archived_at = ? WHERE id = ?",
        (archived_at, project_id)
    )
    conn.commit()
    return db_get_project_by_id(conn, project_id)


def db_get_project_thread_counts(conn, project_id) -> dict:
    """
    Retrieve a project_thread_counts record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        project_id (Any): The project_id parameter.

    Returns:
        dict: The result of the operation.
    """
    total = conn.execute("SELECT COUNT(*) FROM threads WHERE project_id = ?", (project_id,)).fetchone()[0]
    open_count = conn.execute(
        "SELECT COUNT(*) FROM threads WHERE project_id = ? AND status = 'open'", (project_id,)
    ).fetchone()[0]
    resolved_count = conn.execute(
        "SELECT COUNT(*) FROM threads WHERE project_id = ? AND status = 'resolved'", (project_id,)
    ).fetchone()[0]
    return {"total": total, "open": open_count, "resolved": resolved_count}


# --- Agent queries ---

def db_create_agent(conn, id, name, type_, description, created_at) -> dict:
    """
    Create a new agent record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (Any): The id parameter.
        name (Any): The name parameter.
        type_ (Any): The type_ parameter.
        description (Any): The description parameter.
        created_at (Any): The created_at parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        "INSERT INTO agents (id, name, type, description, created_at) VALUES (?, ?, ?, ?, ?)",
        (id, name, type_, description, created_at)
    )
    conn.commit()
    return db_get_agent_by_id(conn, id)


def db_get_agent_by_id(conn, agent_id) -> dict | None:
    """
    Retrieve a agent record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (Any): The agent_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return dict(row) if row else None


def db_get_agent_by_name(conn, name) -> dict | None:
    """
    Retrieve a agent record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        name (Any): The name parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def db_list_agents(conn) -> list[dict]:
    """
    List agents records from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.

    Returns:
        list[dict]: The result of the operation.
    """
    rows = conn.execute("SELECT * FROM agents ORDER BY created_at ASC").fetchall()
    return [dict(r) for r in rows]


def db_get_agent_activity(conn, agent_id) -> dict:
    """
    Retrieve a agent_activity record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (Any): The agent_id parameter.

    Returns:
        dict: The result of the operation.
    """
    total = conn.execute("SELECT COUNT(*) FROM entries WHERE agent_id = ?", (agent_id,)).fetchone()[0]
    type_rows = conn.execute(
        "SELECT type, COUNT(*) as cnt FROM entries WHERE agent_id = ? GROUP BY type", (agent_id,)
    ).fetchall()
    by_type = {r["type"]: r["cnt"] for r in type_rows}
    project_rows = conn.execute(
        """SELECT DISTINCT p.id, p.name FROM entries e
           JOIN threads t ON e.thread_id = t.id
           JOIN projects p ON t.project_id = p.id
           WHERE e.agent_id = ?""",
        (agent_id,)
    ).fetchall()
    projects = [{"id": r["id"], "name": r["name"]} for r in project_rows]
    return {"total_entries": total, "by_type": by_type, "projects": projects}


# --- Thread queries ---

def db_create_thread(conn, id, project_id, title, created_at) -> dict:
    """
    Create a new thread record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (Any): The id parameter.
        project_id (Any): The project_id parameter.
        title (Any): The title parameter.
        created_at (Any): The created_at parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        "INSERT INTO threads (id, project_id, title, status, created_at) VALUES (?, ?, ?, 'open', ?)",
        (id, project_id, title, created_at)
    )
    conn.commit()
    return db_get_thread_by_id(conn, id)


def db_get_thread_by_id(conn, thread_id) -> dict | None:
    """
    Retrieve a thread record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        thread_id (Any): The thread_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
    return dict(row) if row else None


def db_list_threads(conn, project_id, status, limit, offset) -> tuple[list[dict], int]:
    """
    List threads records from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        project_id (Any): The project_id parameter.
        status (Any): The status parameter.
        limit (Any): The limit parameter.
        offset (Any): The offset parameter.

    Returns:
        tuple[list[dict], int]: The result of the operation.
    """
    conditions = []
    params = []
    if project_id:
        conditions.append("t.project_id = ?")
        params.append(project_id)
    if status:
        conditions.append("t.status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    count_sql = f"SELECT COUNT(*) FROM threads t {where}"
    total = conn.execute(count_sql, params).fetchone()[0]
    list_sql = f"""
        SELECT t.*, p.name as project_name,
               (SELECT COUNT(*) FROM entries e WHERE e.thread_id = t.id) as entry_count
        FROM threads t
        JOIN projects p ON t.project_id = p.id
        {where}
        ORDER BY t.created_at DESC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(list_sql, params + [limit, offset]).fetchall()
    return [dict(r) for r in rows], total


def db_resolve_thread(conn, thread_id, resolved_at) -> dict | None:
    """
    Execute database operation for db_resolve_thread.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        thread_id (Any): The thread_id parameter.
        resolved_at (Any): The resolved_at parameter.

    Returns:
        dict | None: The result of the operation.
    """
    conn.execute(
        "UPDATE threads SET status = 'resolved', resolved_at = ? WHERE id = ?",
        (resolved_at, thread_id)
    )
    conn.commit()
    return db_get_thread_by_id(conn, thread_id)


def db_get_thread_entry_counts(conn, thread_id) -> dict:
    """
    Retrieve a thread_entry_counts record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        thread_id (Any): The thread_id parameter.

    Returns:
        dict: The result of the operation.
    """
    total = conn.execute("SELECT COUNT(*) FROM entries WHERE thread_id = ?", (thread_id,)).fetchone()[0]
    pinned = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE thread_id = ? AND pinned = 1", (thread_id,)
    ).fetchone()[0]
    return {"total_entries": total, "pinned_count": pinned}


def db_get_thread_entries(conn, thread_id, agent_id, entry_type, pinned_only, order, limit, offset) -> tuple[list[dict], int]:
    """
    Retrieve a thread_entries record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        thread_id (Any): The thread_id parameter.
        agent_id (Any): The agent_id parameter.
        entry_type (Any): The entry_type parameter.
        pinned_only (Any): The pinned_only parameter.
        order (Any): The order parameter.
        limit (Any): The limit parameter.
        offset (Any): The offset parameter.

    Returns:
        tuple[list[dict], int]: The result of the operation.
    """
    conditions = ["e.thread_id = ?"]
    params = [thread_id]
    if agent_id:
        conditions.append("e.agent_id = ?")
        params.append(agent_id)
    if entry_type:
        conditions.append("e.type = ?")
        params.append(entry_type)
    if pinned_only:
        conditions.append("e.pinned = 1")
    where = "WHERE " + " AND ".join(conditions)
    count_sql = f"SELECT COUNT(*) FROM entries e {where}"
    filtered_total = conn.execute(count_sql, params).fetchone()[0]
    direction = "ASC" if order == "asc" else "DESC"
    list_sql = f"""
        SELECT e.*, a.name as agent_name
        FROM entries e
        JOIN agents a ON e.agent_id = a.id
        {where}
        ORDER BY e.created_at {direction}
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(list_sql, params + [limit, offset]).fetchall()
    return [dict(r) for r in rows], filtered_total


def db_get_thread_all_entries(conn, thread_id) -> list[dict]:
    """
    Retrieve a thread_all_entries record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        thread_id (Any): The thread_id parameter.

    Returns:
        list[dict]: The result of the operation.
    """
    rows = conn.execute(
        """SELECT e.*, a.name as agent_name
           FROM entries e
           JOIN agents a ON e.agent_id = a.id
           WHERE e.thread_id = ?
           ORDER BY e.created_at ASC""",
        (thread_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def db_get_thread_participants(conn, thread_id) -> list[str]:
    """
    Retrieve a thread_participants record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        thread_id (Any): The thread_id parameter.

    Returns:
        list[str]: The result of the operation.
    """
    rows = conn.execute(
        """SELECT DISTINCT a.name FROM entries e
           JOIN agents a ON e.agent_id = a.id
           WHERE e.thread_id = ?""",
        (thread_id,)
    ).fetchall()
    return [r["name"] for r in rows]


# --- Entry queries ---

def db_create_entry(conn, id, thread_id, agent_id, type_, content, reply_to, created_at) -> dict:
    """
    Create a new entry record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (Any): The id parameter.
        thread_id (Any): The thread_id parameter.
        agent_id (Any): The agent_id parameter.
        type_ (Any): The type_ parameter.
        content (Any): The content parameter.
        reply_to (Any): The reply_to parameter.
        created_at (Any): The created_at parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        """INSERT INTO entries (id, thread_id, agent_id, type, content, reply_to, pinned, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (id, thread_id, agent_id, type_, content, reply_to, created_at, created_at)
    )
    conn.commit()
    return db_get_entry_by_id(conn, id)


def db_get_entry_by_id(conn, entry_id) -> dict | None:
    """
    Retrieve a entry record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        entry_id (Any): The entry_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return dict(row) if row else None


def db_update_entry(conn, entry_id, content, updated_at) -> dict | None:
    """
    Update a entry record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        entry_id (Any): The entry_id parameter.
        content (Any): The content parameter.
        updated_at (Any): The updated_at parameter.

    Returns:
        dict | None: The result of the operation.
    """
    conn.execute(
        "UPDATE entries SET content = ?, updated_at = ? WHERE id = ?",
        (content, updated_at, entry_id)
    )
    conn.commit()
    return db_get_entry_by_id(conn, entry_id)


def db_pin_entry(conn, entry_id, pinned: bool) -> dict | None:
    """
    Execute database operation for db_pin_entry.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        entry_id (Any): The entry_id parameter.
        pinned (bool): The pinned parameter.

    Returns:
        dict | None: The result of the operation.
    """
    conn.execute(
        "UPDATE entries SET pinned = ? WHERE id = ?",
        (1 if pinned else 0, entry_id)
    )
    conn.commit()
    return db_get_entry_by_id(conn, entry_id)


def db_get_entry_with_context(conn, entry_id) -> dict | None:
    """
    Retrieve a entry_with_context record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        entry_id (Any): The entry_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute(
        """SELECT e.id, e.thread_id, e.agent_id, e.type, e.content, e.reply_to,
                  e.pinned, e.created_at, e.updated_at,
                  a.name as agent_name,
                  t.title as thread_title,
                  t.project_id
           FROM entries e
           JOIN agents a ON e.agent_id = a.id
           JOIN threads t ON e.thread_id = t.id
           WHERE e.id = ?""",
        (entry_id,)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    if result.get("reply_to"):
        parent = conn.execute(
            "SELECT content FROM entries WHERE id = ?", (result["reply_to"],)
        ).fetchone()
        result["reply_to_snippet"] = (dict(parent)["content"][:100] + "...") if parent else None
    else:
        result["reply_to_snippet"] = None
    return result


# =============================================================================
# V2 SCHEMA
# =============================================================================

def init_db_v2(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        -- Skills tables
        CREATE TABLE IF NOT EXISTS personal_skills (
            id           TEXT PRIMARY KEY,
            agent_id     TEXT NOT NULL REFERENCES agents(id),
            name         TEXT NOT NULL,
            skill_type   TEXT NOT NULL,
            description  TEXT NOT NULL,
            content      TEXT NOT NULL,
            tags         TEXT,
            usage_count  INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            UNIQUE(agent_id, name)
        );

        CREATE TABLE IF NOT EXISTS global_skills (
            id           TEXT PRIMARY KEY,
            project_id   TEXT REFERENCES projects(id),
            name         TEXT NOT NULL,
            skill_type   TEXT NOT NULL,
            description  TEXT NOT NULL,
            content      TEXT NOT NULL,
            tags         TEXT,
            created_by   TEXT NOT NULL REFERENCES agents(id),
            version      INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_personal_skills_agent ON personal_skills(agent_id);
        CREATE INDEX IF NOT EXISTS idx_global_skills_project ON global_skills(project_id);

        -- FTS5 for personal skills
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

        -- FTS5 for global skills
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

        -- Memory tables
        -- agent_id and project_id use '__global__' sentinel instead of NULL
        -- so UNIQUE constraints and equality comparisons work correctly
        CREATE TABLE IF NOT EXISTS short_term_memory (
            id          TEXT PRIMARY KEY,
            agent_id    TEXT NOT NULL REFERENCES agents(id),
            project_id  TEXT NOT NULL DEFAULT '__global__',
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            expires_at  TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            UNIQUE(agent_id, project_id, key)
        );

        CREATE TABLE IF NOT EXISTS long_term_memory (
            id               TEXT PRIMARY KEY,
            agent_id         TEXT NOT NULL DEFAULT '__global__',
            project_id       TEXT NOT NULL DEFAULT '__global__',
            key              TEXT NOT NULL,
            value            TEXT NOT NULL,
            tags             TEXT,
            confidence       TEXT NOT NULL DEFAULT 'medium',
            source_thread_id TEXT REFERENCES threads(id),
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_stm_agent_project ON short_term_memory(agent_id, project_id);
        CREATE INDEX IF NOT EXISTS idx_ltm_agent_project ON long_term_memory(agent_id, project_id);
        CREATE INDEX IF NOT EXISTS idx_ltm_project ON long_term_memory(project_id);

        -- FTS5 for long-term memory (value field only)
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

        -- Collaboration tables
        -- agent_presence uses '__global__' sentinel for project_id (no NULL)
        -- agent_messages.to_agent_id stays NULL for broadcast (absence of recipient)
        -- broadcast messages get 48h auto-expiry set by server at send time
        CREATE TABLE IF NOT EXISTS agent_messages (
            id             TEXT PRIMARY KEY,
            from_agent_id  TEXT NOT NULL REFERENCES agents(id),
            to_agent_id    TEXT REFERENCES agents(id),
            project_id     TEXT REFERENCES projects(id),
            subject        TEXT NOT NULL,
            content        TEXT NOT NULL,
            priority       TEXT NOT NULL DEFAULT 'normal',
            thread_ref     TEXT REFERENCES threads(id),
            is_read        INTEGER NOT NULL DEFAULT 0,
            expires_at     TEXT,
            created_at     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_presence (
            id           TEXT PRIMARY KEY,
            agent_id     TEXT NOT NULL REFERENCES agents(id),
            project_id   TEXT NOT NULL DEFAULT '__global__',
            status       TEXT NOT NULL DEFAULT 'idle',
            current_task TEXT,
            updated_at   TEXT NOT NULL,
            UNIQUE(agent_id, project_id)
        );

        CREATE TABLE IF NOT EXISTS handoffs (
            id              TEXT PRIMARY KEY,
            from_agent_id   TEXT NOT NULL REFERENCES agents(id),
            project_id      TEXT NOT NULL REFERENCES projects(id),
            summary         TEXT NOT NULL,
            in_progress     TEXT,
            blockers        TEXT,
            next_steps      TEXT,
            thread_refs     TEXT,
            acknowledged_by TEXT REFERENCES agents(id),
            acknowledged_at TEXT,
            created_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_to_agent   ON agent_messages(to_agent_id, is_read);
        CREATE INDEX IF NOT EXISTS idx_messages_from_agent ON agent_messages(from_agent_id);
        CREATE INDEX IF NOT EXISTS idx_presence_agent      ON agent_presence(agent_id);
        CREATE INDEX IF NOT EXISTS idx_handoffs_project    ON handoffs(project_id, created_at);
    """)
    conn.commit()


# --- Personal Skill queries ---

def db_get_personal_skill_by_name(conn, agent_id: str, name: str) -> dict | None:
    """
    Retrieve a personal_skill record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (str): The agent_id parameter.
        name (str): The name parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute(
        "SELECT * FROM personal_skills WHERE agent_id = ? AND name = ?", (agent_id, name)
    ).fetchone()
    return dict(row) if row else None


def db_get_personal_skill_by_id(conn, skill_id: str) -> dict | None:
    """
    Retrieve a personal_skill record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        skill_id (str): The skill_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute(
        "SELECT * FROM personal_skills WHERE id = ?", (skill_id,)
    ).fetchone()
    return dict(row) if row else None


def db_create_personal_skill(conn, id, agent_id, name, skill_type, description, content, tags, created_at) -> dict:
    """
    Create a new personal_skill record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (Any): The id parameter.
        agent_id (Any): The agent_id parameter.
        name (Any): The name parameter.
        skill_type (Any): The skill_type parameter.
        description (Any): The description parameter.
        content (Any): The content parameter.
        tags (Any): The tags parameter.
        created_at (Any): The created_at parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        """INSERT INTO personal_skills (id, agent_id, name, skill_type, description, content, tags, usage_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (id, agent_id, name, skill_type, description, content, tags, created_at, created_at)
    )
    conn.commit()
    return db_get_personal_skill_by_id(conn, id)


def db_increment_skill_usage(conn, skill_id: str) -> None:
    """
    Execute database operation for db_increment_skill_usage.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        skill_id (str): The skill_id parameter.
    """
    conn.execute(
        "UPDATE personal_skills SET usage_count = usage_count + 1 WHERE id = ?", (skill_id,)
    )
    conn.commit()


def db_list_personal_skills(conn, agent_id: str, skill_type: str | None, tag: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    """
    List personal_skills records from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (str): The agent_id parameter.
        skill_type (str | None): The skill_type parameter.
        tag (str | None): The tag parameter.
        limit (int): The limit parameter.
        offset (int): The offset parameter.

    Returns:
        tuple[list[dict], int]: The result of the operation.
    """
    conditions = ["agent_id = ?"]
    params = [agent_id]
    if skill_type:
        conditions.append("skill_type = ?")
        params.append(skill_type)
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f"%{tag}%")
    where = "WHERE " + " AND ".join(conditions)
    total = conn.execute(f"SELECT COUNT(*) FROM personal_skills {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT id, name, skill_type, description, tags, usage_count, updated_at FROM personal_skills {where} ORDER BY usage_count DESC, name ASC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()
    return [dict(r) for r in rows], total


def db_update_personal_skill(conn, skill_id: str, description: str | None, content: str | None, tags: str | None, updated_at: str) -> dict | None:
    """
    Update a personal_skill record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        skill_id (str): The skill_id parameter.
        description (str | None): The description parameter.
        content (str | None): The content parameter.
        tags (str | None): The tags parameter.
        updated_at (str): The updated_at parameter.

    Returns:
        dict | None: The result of the operation.
    """
    skill = db_get_personal_skill_by_id(conn, skill_id)
    if not skill:
        return None
    new_description = description if description is not None else skill["description"]
    new_content = content if content is not None else skill["content"]
    new_tags = tags if tags is not None else skill["tags"]
    conn.execute(
        "UPDATE personal_skills SET description = ?, content = ?, tags = ?, updated_at = ? WHERE id = ?",
        (new_description, new_content, new_tags, updated_at, skill_id)
    )
    conn.commit()
    return db_get_personal_skill_by_id(conn, skill_id)


def db_delete_personal_skill(conn, skill_id: str) -> bool:
    """
    Delete a personal_skill record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        skill_id (str): The skill_id parameter.

    Returns:
        bool: The result of the operation.
    """
    cursor = conn.execute("DELETE FROM personal_skills WHERE id = ?", (skill_id,))
    conn.commit()
    return cursor.rowcount > 0


# --- Global Skill queries ---

def db_get_global_skill_by_id(conn, skill_id: str) -> dict | None:
    """
    Retrieve a global_skill record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        skill_id (str): The skill_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute(
        "SELECT * FROM global_skills WHERE id = ?", (skill_id,)
    ).fetchone()
    return dict(row) if row else None


def db_get_global_skill_by_name(conn, name: str, project_id: str | None) -> dict | None:
    """Resolution order: project-scoped first, then global fallback."""
    if project_id:
        row = conn.execute(
            "SELECT * FROM global_skills WHERE name = ? AND project_id = ?", (name, project_id)
        ).fetchone()
        if row:
            return {**dict(row), "scope": "project"}
    row = conn.execute(
        "SELECT * FROM global_skills WHERE name = ? AND project_id IS NULL", (name,)
    ).fetchone()
    return {**dict(row), "scope": "global"} if row else None


def db_check_global_skill_name_exists(conn, name: str, project_id: str | None) -> bool:
    """Check uniqueness — handles NULL project_id manually since NULL != NULL in SQLite."""
    if project_id is None:
        row = conn.execute(
            "SELECT id FROM global_skills WHERE name = ? AND project_id IS NULL", (name,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM global_skills WHERE name = ? AND project_id = ?", (name, project_id)
        ).fetchone()
    return row is not None


def db_create_global_skill(conn, id, project_id, name, skill_type, description, content, tags, created_by, created_at) -> dict:
    """
    Create a new global_skill record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (Any): The id parameter.
        project_id (Any): The project_id parameter.
        name (Any): The name parameter.
        skill_type (Any): The skill_type parameter.
        description (Any): The description parameter.
        content (Any): The content parameter.
        tags (Any): The tags parameter.
        created_by (Any): The created_by parameter.
        created_at (Any): The created_at parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        """INSERT INTO global_skills (id, project_id, name, skill_type, description, content, tags, created_by, version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (id, project_id, name, skill_type, description, content, tags, created_by, created_at, created_at)
    )
    conn.commit()
    return db_get_global_skill_by_id(conn, id)


def db_list_global_skills(conn, project_id: str | None, skill_type: str | None, tag: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    """
    List global_skills records from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        project_id (str | None): The project_id parameter.
        skill_type (str | None): The skill_type parameter.
        tag (str | None): The tag parameter.
        limit (int): The limit parameter.
        offset (int): The offset parameter.

    Returns:
        tuple[list[dict], int]: The result of the operation.
    """
    conditions = []
    params = []
    if project_id:
        conditions.append("(project_id = ? OR project_id IS NULL)")
        params.append(project_id)
    else:
        conditions.append("project_id IS NULL")
    if skill_type:
        conditions.append("skill_type = ?")
        params.append(skill_type)
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f"%{tag}%")
    where = "WHERE " + " AND ".join(conditions)
    total = conn.execute(f"SELECT COUNT(*) FROM global_skills {where}", params).fetchone()[0]
    rows = conn.execute(
        f"""SELECT id, project_id, name, skill_type, description, tags, version, updated_at,
                   CASE WHEN project_id IS NULL THEN 'global' ELSE 'project' END as scope
            FROM global_skills {where}
            ORDER BY scope ASC, name ASC
            LIMIT ? OFFSET ?""",
        params + [limit, offset]
    ).fetchall()
    return [dict(r) for r in rows], total


def db_update_global_skill(conn, skill_id: str, description: str | None, content: str | None, tags: str | None, updated_at: str) -> dict | None:
    """
    Update a global_skill record in the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        skill_id (str): The skill_id parameter.
        description (str | None): The description parameter.
        content (str | None): The content parameter.
        tags (str | None): The tags parameter.
        updated_at (str): The updated_at parameter.

    Returns:
        dict | None: The result of the operation.
    """
    skill = db_get_global_skill_by_id(conn, skill_id)
    if not skill:
        return None
    new_description = description if description is not None else skill["description"]
    new_content = content if content is not None else skill["content"]
    new_tags = tags if tags is not None else skill["tags"]
    conn.execute(
        "UPDATE global_skills SET description = ?, content = ?, tags = ?, version = version + 1, updated_at = ? WHERE id = ?",
        (new_description, new_content, new_tags, updated_at, skill_id)
    )
    conn.commit()
    return db_get_global_skill_by_id(conn, skill_id)


def db_delete_global_skill(conn, skill_id: str) -> bool:
    """
    Delete a global_skill record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        skill_id (str): The skill_id parameter.

    Returns:
        bool: The result of the operation.
    """
    cursor = conn.execute("DELETE FROM global_skills WHERE id = ?", (skill_id,))
    conn.commit()
    return cursor.rowcount > 0


def db_search_skills_fts(conn, query: str, agent_id: str | None, project_id: str | None, limit: int, offset: int) -> list[dict]:
    """
    Execute database operation for db_search_skills_fts.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        query (str): The query parameter.
        agent_id (str | None): The agent_id parameter.
        project_id (str | None): The project_id parameter.
        limit (int): The limit parameter.
        offset (int): The offset parameter.

    Returns:
        list[dict]: The result of the operation.
    """
    results = []

    # Search personal skills if agent_id provided
    if agent_id:
        try:
            sql = """
                SELECT ps.id, ps.name, ps.skill_type, ps.tags, ps.usage_count,
                       snippet(personal_skills_fts, 0, '**', '**', '...', 15) as description_snippet,
                       snippet(personal_skills_fts, 1, '**', '**', '...', 15) as content_snippet,
                       personal_skills_fts.rank
                FROM personal_skills_fts
                JOIN personal_skills ps ON personal_skills_fts.rowid = ps.rowid
                WHERE personal_skills_fts MATCH ? AND ps.agent_id = ?
            """
            rows = conn.execute(sql, [query, agent_id]).fetchall()
        except Exception:
            like = f"%{query}%"
            rows = conn.execute(
                """SELECT id, name, skill_type, tags, usage_count,
                          description as description_snippet, content as content_snippet, 0 as rank
                   FROM personal_skills WHERE (description LIKE ? OR content LIKE ?) AND agent_id = ?""",
                [like, like, agent_id]
            ).fetchall()
        for r in rows:
            results.append({**dict(r), "source": "personal", "version": None})

    # Search global skills if project_id provided or neither provided (search all global)
    try:
        if project_id:
            gs_sql = """
                SELECT gs.id, gs.name, gs.skill_type, gs.tags, gs.version,
                       snippet(global_skills_fts, 0, '**', '**', '...', 15) as description_snippet,
                       snippet(global_skills_fts, 1, '**', '**', '...', 15) as content_snippet,
                       global_skills_fts.rank
                FROM global_skills_fts
                JOIN global_skills gs ON global_skills_fts.rowid = gs.rowid
                WHERE global_skills_fts MATCH ? AND (gs.project_id = ? OR gs.project_id IS NULL)
            """
            gs_rows = conn.execute(gs_sql, [query, project_id]).fetchall()
        else:
            gs_sql = """
                SELECT gs.id, gs.name, gs.skill_type, gs.tags, gs.version,
                       snippet(global_skills_fts, 0, '**', '**', '...', 15) as description_snippet,
                       snippet(global_skills_fts, 1, '**', '**', '...', 15) as content_snippet,
                       global_skills_fts.rank
                FROM global_skills_fts
                JOIN global_skills gs ON global_skills_fts.rowid = gs.rowid
                WHERE global_skills_fts MATCH ?
            """
            gs_rows = conn.execute(gs_sql, [query]).fetchall()
    except Exception:
        like = f"%{query}%"
        if project_id:
            gs_rows = conn.execute(
                """SELECT id, name, skill_type, tags, version,
                          description as description_snippet, content as content_snippet, 0 as rank
                   FROM global_skills WHERE (description LIKE ? OR content LIKE ?) AND (project_id = ? OR project_id IS NULL)""",
                [like, like, project_id]
            ).fetchall()
        else:
            gs_rows = conn.execute(
                """SELECT id, name, skill_type, tags, version,
                          description as description_snippet, content as content_snippet, 0 as rank
                   FROM global_skills WHERE description LIKE ? OR content LIKE ?""",
                [like, like]
            ).fetchall()
    for r in gs_rows:
        results.append({**dict(r), "source": "global", "usage_count": None})

    return results


# --- Short-term memory queries ---

GLOBAL = "__global__"


def db_stm_set(conn, id: str, agent_id: str, project_id: str, key: str, value: str, expires_at: str | None, now: str) -> None:
    """
    Execute database operation for db_stm_set.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (str): The id parameter.
        agent_id (str): The agent_id parameter.
        project_id (str): The project_id parameter.
        key (str): The key parameter.
        value (str): The value parameter.
        expires_at (str | None): The expires_at parameter.
        now (str): The now parameter.
    """
    conn.execute(
        """INSERT INTO short_term_memory (id, agent_id, project_id, key, value, expires_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(agent_id, project_id, key) DO UPDATE SET
               value      = excluded.value,
               expires_at = CASE WHEN excluded.expires_at IS NOT NULL THEN excluded.expires_at ELSE short_term_memory.expires_at END,
               updated_at = excluded.updated_at""",
        (id, agent_id, project_id, key, value, expires_at, now, now)
    )
    conn.commit()


def db_stm_get_key(conn, agent_id: str, project_id: str, key: str, now: str) -> dict | None:
    """
    Retrieve a key record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (str): The agent_id parameter.
        project_id (str): The project_id parameter.
        key (str): The key parameter.
        now (str): The now parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute(
        """SELECT * FROM short_term_memory
           WHERE agent_id = ? AND project_id = ? AND key = ?
             AND (expires_at IS NULL OR expires_at > ?)""",
        (agent_id, project_id, key, now)
    ).fetchone()
    return dict(row) if row else None


def db_stm_get_all(conn, agent_id: str, project_id: str, now: str) -> list[dict]:
    """
    Retrieve a all record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (str): The agent_id parameter.
        project_id (str): The project_id parameter.
        now (str): The now parameter.

    Returns:
        list[dict]: The result of the operation.
    """
    rows = conn.execute(
        """SELECT * FROM short_term_memory
           WHERE agent_id = ? AND project_id = ?
             AND (expires_at IS NULL OR expires_at > ?)
           ORDER BY key ASC""",
        (agent_id, project_id, now)
    ).fetchall()
    return [dict(r) for r in rows]


def db_stm_clear(conn, agent_id: str, project_id: str) -> int:
    """
    Execute database operation for db_stm_clear.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (str): The agent_id parameter.
        project_id (str): The project_id parameter.

    Returns:
        int: The result of the operation.
    """
    cursor = conn.execute(
        "DELETE FROM short_term_memory WHERE agent_id = ? AND project_id = ?",
        (agent_id, project_id)
    )
    conn.commit()
    return cursor.rowcount


# --- Long-term memory queries ---

def db_ltm_set(conn, id: str, agent_id: str, project_id: str, key: str, value: str,
               tags: str | None, confidence: str, source_thread_id: str | None, now: str) -> dict:
    """
    Execute database operation for db_ltm_set.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (str): The id parameter.
        agent_id (str): The agent_id parameter.
        project_id (str): The project_id parameter.
        key (str): The key parameter.
        value (str): The value parameter.
        tags (str | None): The tags parameter.
        confidence (str): The confidence parameter.
        source_thread_id (str | None): The source_thread_id parameter.
        now (str): The now parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        """INSERT INTO long_term_memory (id, agent_id, project_id, key, value, tags, confidence, source_thread_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id, agent_id, project_id, key, value, tags, confidence, source_thread_id, now, now)
    )
    conn.commit()
    return db_ltm_get_by_id(conn, id)


def db_ltm_get_by_id(conn, memory_id: str) -> dict | None:
    """
    Retrieve a by_id record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        memory_id (str): The memory_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute("SELECT * FROM long_term_memory WHERE id = ?", (memory_id,)).fetchone()
    return dict(row) if row else None


def db_ltm_get(conn, agent_id: str, project_id: str, key: str | None, tag: str | None,
               limit: int, offset: int) -> tuple[list[dict], int]:
    """
    Execute database operation for db_ltm_get.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (str): The agent_id parameter.
        project_id (str): The project_id parameter.
        key (str | None): The key parameter.
        tag (str | None): The tag parameter.
        limit (int): The limit parameter.
        offset (int): The offset parameter.

    Returns:
        tuple[list[dict], int]: The result of the operation.
    """
    conditions = ["agent_id = ?", "project_id = ?"]
    params: list = [agent_id, project_id]
    if key:
        conditions.append("key = ?")
        params.append(key)
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f"%{tag}%")
    where = "WHERE " + " AND ".join(conditions)
    total = conn.execute(f"SELECT COUNT(*) FROM long_term_memory {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM long_term_memory {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()
    return [dict(r) for r in rows], total


def db_ltm_delete(conn, memory_id: str) -> bool:
    """
    Execute database operation for db_ltm_delete.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        memory_id (str): The memory_id parameter.

    Returns:
        bool: The result of the operation.
    """
    cursor = conn.execute("DELETE FROM long_term_memory WHERE id = ?", (memory_id,))
    conn.commit()
    return cursor.rowcount > 0


def db_ltm_search_fts(conn, query: str, agent_id: str, project_id: str, limit: int, offset: int) -> list[dict]:
    """
    Execute database operation for db_ltm_search_fts.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        query (str): The query parameter.
        agent_id (str): The agent_id parameter.
        project_id (str): The project_id parameter.
        limit (int): The limit parameter.
        offset (int): The offset parameter.

    Returns:
        list[dict]: The result of the operation.
    """
    try:
        sql = """
            SELECT ltm.id, ltm.agent_id, ltm.project_id, ltm.key, ltm.tags,
                   ltm.confidence, ltm.source_thread_id, ltm.created_at,
                   snippet(ltm_fts, 0, '**', '**', '...', 20) as snippet,
                   ltm_fts.rank
            FROM ltm_fts
            JOIN long_term_memory ltm ON ltm_fts.rowid = ltm.rowid
            WHERE ltm_fts MATCH ? AND ltm.agent_id = ? AND ltm.project_id = ?
            ORDER BY ltm_fts.rank
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(sql, [query, agent_id, project_id, limit, offset]).fetchall()
    except Exception:
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT id, agent_id, project_id, key, tags, confidence, source_thread_id, created_at,
                      value as snippet, 0 as rank
               FROM long_term_memory
               WHERE value LIKE ? AND agent_id = ? AND project_id = ?
               LIMIT ? OFFSET ?""",
            [like, agent_id, project_id, limit, offset]
        ).fetchall()
    return [dict(r) for r in rows]


# --- Message queries ---

def db_message_get_by_id(conn, message_id: str) -> dict | None:
    """
    Retrieve a by_id record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        message_id (str): The message_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute(
        """SELECT m.*, fa.name as from_agent_name, ta.name as to_agent_name, p.name as project_name
           FROM agent_messages m
           JOIN agents fa ON m.from_agent_id = fa.id
           LEFT JOIN agents ta ON m.to_agent_id = ta.id
           LEFT JOIN projects p ON m.project_id = p.id
           WHERE m.id = ?""",
        (message_id,)
    ).fetchone()
    return dict(row) if row else None


def db_message_send(conn, id: str, from_agent_id: str, to_agent_id: str | None,
                    project_id: str | None, subject: str, content: str, priority: str,
                    thread_ref: str | None, expires_at: str | None, now: str) -> dict:
    """
    Execute database operation for db_message_send.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (str): The id parameter.
        from_agent_id (str): The from_agent_id parameter.
        to_agent_id (str | None): The to_agent_id parameter.
        project_id (str | None): The project_id parameter.
        subject (str): The subject parameter.
        content (str): The content parameter.
        priority (str): The priority parameter.
        thread_ref (str | None): The thread_ref parameter.
        expires_at (str | None): The expires_at parameter.
        now (str): The now parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        """INSERT INTO agent_messages
           (id, from_agent_id, to_agent_id, project_id, subject, content, priority, thread_ref, is_read, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (id, from_agent_id, to_agent_id, project_id, subject, content, priority, thread_ref, expires_at, now)
    )
    conn.commit()
    return db_message_get_by_id(conn, id)


def db_message_inbox(conn, agent_id: str, project_id: str | None, unread_only: bool,
                     limit: int, offset: int, now: str) -> tuple[list[dict], int]:
    """
    Execute database operation for db_message_inbox.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        agent_id (str): The agent_id parameter.
        project_id (str | None): The project_id parameter.
        unread_only (bool): The unread_only parameter.
        limit (int): The limit parameter.
        offset (int): The offset parameter.
        now (str): The now parameter.

    Returns:
        tuple[list[dict], int]: The result of the operation.
    """
    conditions = [
        "(m.to_agent_id = ? OR m.to_agent_id IS NULL)",
        "(m.expires_at IS NULL OR m.expires_at > ?)",
    ]
    params: list = [agent_id, now]
    if project_id:
        conditions.append("m.project_id = ?")
        params.append(project_id)
    if unread_only:
        conditions.append("m.is_read = 0")
    where = "WHERE " + " AND ".join(conditions)
    join = """FROM agent_messages m
              JOIN agents fa ON m.from_agent_id = fa.id
              LEFT JOIN agents ta ON m.to_agent_id = ta.id
              LEFT JOIN projects p ON m.project_id = p.id"""
    total = conn.execute(f"SELECT COUNT(*) {join} {where}", params).fetchone()[0]
    rows = conn.execute(
        f"""SELECT m.id, m.subject, m.priority, m.is_read, m.thread_ref,
                   m.expires_at, m.created_at,
                   SUBSTR(m.content, 1, 100) as content_preview,
                   fa.name as from_agent_name,
                   ta.name as to_agent_name,
                   p.name as project_name
            {join} {where}
            ORDER BY m.created_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset]
    ).fetchall()
    return [dict(r) for r in rows], total


def db_message_mark_read(conn, message_id: str) -> dict | None:
    """
    Execute database operation for db_message_mark_read.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        message_id (str): The message_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    conn.execute("UPDATE agent_messages SET is_read = 1 WHERE id = ?", (message_id,))
    conn.commit()
    return db_message_get_by_id(conn, message_id)


# --- Presence queries ---

def db_presence_upsert(conn, id: str, agent_id: str, project_id: str,
                       status: str, current_task: str | None, now: str) -> None:
    """
    Execute database operation for db_presence_upsert.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (str): The id parameter.
        agent_id (str): The agent_id parameter.
        project_id (str): The project_id parameter.
        status (str): The status parameter.
        current_task (str | None): The current_task parameter.
        now (str): The now parameter.
    """
    conn.execute(
        """INSERT INTO agent_presence (id, agent_id, project_id, status, current_task, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(agent_id, project_id) DO UPDATE SET
               status       = excluded.status,
               current_task = excluded.current_task,
               updated_at   = excluded.updated_at""",
        (id, agent_id, project_id, status, current_task, now)
    )
    conn.commit()


def db_presence_get(conn, project_id: str | None) -> list[dict]:
    """
    Execute database operation for db_presence_get.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        project_id (str | None): The project_id parameter.

    Returns:
        list[dict]: The result of the operation.
    """
    if project_id:
        rows = conn.execute(
            """SELECT ap.*, a.name as agent_name, a.type as agent_type, p.name as project_name
               FROM agent_presence ap
               JOIN agents a ON ap.agent_id = a.id
               LEFT JOIN projects p ON ap.project_id = p.id
               WHERE ap.project_id = ? OR ap.project_id = '__global__'
               ORDER BY ap.updated_at DESC""",
            (project_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT ap.*, a.name as agent_name, a.type as agent_type, p.name as project_name
               FROM agent_presence ap
               JOIN agents a ON ap.agent_id = a.id
               LEFT JOIN projects p ON ap.project_id = p.id
               ORDER BY ap.updated_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


# --- Handoff queries ---

def db_handoff_get_by_id(conn, handoff_id: str) -> dict | None:
    """
    Retrieve a by_id record from the database.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        handoff_id (str): The handoff_id parameter.

    Returns:
        dict | None: The result of the operation.
    """
    row = conn.execute(
        """SELECT h.*, fa.name as from_agent_name, aa.name as acknowledged_by_name
           FROM handoffs h
           JOIN agents fa ON h.from_agent_id = fa.id
           LEFT JOIN agents aa ON h.acknowledged_by = aa.id
           WHERE h.id = ?""",
        (handoff_id,)
    ).fetchone()
    return dict(row) if row else None


def db_handoff_post(conn, id: str, from_agent_id: str, project_id: str, summary: str,
                    in_progress: str | None, blockers: str | None, next_steps: str | None,
                    thread_refs: str | None, now: str) -> dict:
    """
    Execute database operation for db_handoff_post.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        id (str): The id parameter.
        from_agent_id (str): The from_agent_id parameter.
        project_id (str): The project_id parameter.
        summary (str): The summary parameter.
        in_progress (str | None): The in_progress parameter.
        blockers (str | None): The blockers parameter.
        next_steps (str | None): The next_steps parameter.
        thread_refs (str | None): The thread_refs parameter.
        now (str): The now parameter.

    Returns:
        dict: The result of the operation.
    """
    conn.execute(
        """INSERT INTO handoffs
           (id, from_agent_id, project_id, summary, in_progress, blockers, next_steps, thread_refs,
            acknowledged_by, acknowledged_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)""",
        (id, from_agent_id, project_id, summary, in_progress, blockers, next_steps, thread_refs, now)
    )
    conn.commit()
    return db_handoff_get_by_id(conn, id)


def db_handoff_get_recent(conn, project_id: str, limit: int,
                          unacknowledged_only: bool = False) -> list[dict]:
    sql = """SELECT h.*, fa.name as from_agent_name, aa.name as acknowledged_by_name
             FROM handoffs h
             JOIN agents fa ON h.from_agent_id = fa.id
             LEFT JOIN agents aa ON h.acknowledged_by = aa.id
             WHERE h.project_id = ?"""
    params: list = [project_id]
    if unacknowledged_only:
        sql += " AND h.acknowledged_by IS NULL"
    sql += " ORDER BY h.created_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def db_handoff_acknowledge(conn, handoff_id: str, agent_id: str, now: str) -> dict | None:
    """
    Execute database operation for db_handoff_acknowledge.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        handoff_id (str): The handoff_id parameter.
        agent_id (str): The agent_id parameter.
        now (str): The now parameter.

    Returns:
        dict | None: The result of the operation.
    """
    conn.execute(
        "UPDATE handoffs SET acknowledged_by = ?, acknowledged_at = ? WHERE id = ?",
        (agent_id, now, handoff_id)
    )
    conn.commit()
    return db_handoff_get_by_id(conn, handoff_id)


def db_get_thread_titles(conn, thread_ids: list[str]) -> dict[str, str]:
    """Returns {thread_id: title} for each id that exists."""
    if not thread_ids:
        return {}
    placeholders = ",".join("?" * len(thread_ids))
    rows = conn.execute(
        f"SELECT id, title FROM threads WHERE id IN ({placeholders})", thread_ids
    ).fetchall()
    return {r["id"]: r["title"] for r in rows}


# --- Search queries ---

def search_entries_fts(conn, query: str, project_id: str | None, thread_id: str | None, limit: int, offset: int) -> list[dict]:
    """
    Execute database operation for search_entries_fts.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        query (str): The query parameter.
        project_id (str | None): The project_id parameter.
        thread_id (str | None): The thread_id parameter.
        limit (int): The limit parameter.
        offset (int): The offset parameter.

    Returns:
        list[dict]: The result of the operation.
    """
    try:
        sql = """
            SELECT e.id, e.thread_id, e.agent_id, e.type, e.pinned, e.created_at,
                   t.title as thread_title, t.project_id,
                   p.name as project_name,
                   a.name as agent_name,
                   snippet(entries_fts, 0, '**', '**', '...', 20) as snippet,
                   entries_fts.rank
            FROM entries_fts
            JOIN entries e ON entries_fts.rowid = e.rowid
            JOIN threads t ON e.thread_id = t.id
            JOIN projects p ON t.project_id = p.id
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
        like = f"%{query}%"
        sql = """
            SELECT e.id, e.thread_id, e.agent_id, e.type, e.pinned, e.created_at,
                   t.title as thread_title, t.project_id,
                   p.name as project_name,
                   a.name as agent_name,
                   e.content as snippet,
                   0 as rank
            FROM entries e
            JOIN threads t ON e.thread_id = t.id
            JOIN projects p ON t.project_id = p.id
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


def search_threads_fts(conn, query: str, project_id: str | None, limit: int, offset: int) -> list[dict]:
    """
    Execute database operation for search_threads_fts.

    Args:
        conn (sqlite3.Connection): The conn parameter.
        query (str): The query parameter.
        project_id (str | None): The project_id parameter.
        limit (int): The limit parameter.
        offset (int): The offset parameter.

    Returns:
        list[dict]: The result of the operation.
    """
    try:
        sql = """
            SELECT t.id, t.id as thread_id, t.title as thread_title, t.project_id,
                   p.name as project_name,
                   snippet(threads_fts, 0, '**', '**', '...', 20) as snippet,
                   threads_fts.rank
            FROM threads_fts
            JOIN threads t ON threads_fts.rowid = t.rowid
            JOIN projects p ON t.project_id = p.id
            WHERE threads_fts MATCH ?
        """
        params = [query]
        if project_id:
            sql += " AND t.project_id = ?"
            params.append(project_id)
        sql += " ORDER BY threads_fts.rank LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except Exception:
        like = f"%{query}%"
        sql = """
            SELECT t.id, t.id as thread_id, t.title as thread_title, t.project_id,
                   p.name as project_name,
                   t.title as snippet,
                   0 as rank
            FROM threads t
            JOIN projects p ON t.project_id = p.id
            WHERE t.title LIKE ?
        """
        params = [like]
        if project_id:
            sql += " AND t.project_id = ?"
            params.append(project_id)
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


# =============================================================================
# V3 SCHEMA — Sprint Board
# =============================================================================

def init_db_v3(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sprints (
            id          TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL REFERENCES projects(id),
            name        TEXT NOT NULL,
            goal        TEXT,
            status      TEXT NOT NULL DEFAULT 'planned',
            start_date  TEXT,
            end_date    TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id             TEXT PRIMARY KEY,
            project_id     TEXT NOT NULL REFERENCES projects(id),
            sprint_id      TEXT REFERENCES sprints(id),
            title          TEXT NOT NULL,
            description    TEXT,
            status         TEXT NOT NULL DEFAULT 'backlog',
            assigned_to    TEXT REFERENCES agents(id),
            created_by     TEXT NOT NULL REFERENCES agents(id),
            priority       TEXT NOT NULL DEFAULT 'medium',
            blocked_reason TEXT,
            thread_id      TEXT REFERENCES threads(id),
            due_date       TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_project   ON tasks(project_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_sprint    ON tasks(sprint_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_assigned  ON tasks(assigned_to);
        CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks(project_id, status);
        CREATE INDEX IF NOT EXISTS idx_sprints_project ON sprints(project_id);
        CREATE INDEX IF NOT EXISTS idx_sprints_status  ON sprints(project_id, status);
    """)
    conn.commit()


# --- Sprint queries ---

def db_sprint_get_by_id(conn, sprint_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM sprints WHERE id = ?", (sprint_id,)).fetchone()
    return dict(row) if row else None


def db_sprint_get_active(conn, project_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM sprints WHERE project_id = ? AND status = 'active'",
        (project_id,)
    ).fetchone()
    return dict(row) if row else None


def db_sprint_demote_active(conn, project_id: str, exclude_id: str, now: str) -> None:
    """Demote any currently active sprint in this project to 'planned', except exclude_id."""
    conn.execute(
        "UPDATE sprints SET status = 'planned', updated_at = ? WHERE project_id = ? AND status = 'active' AND id != ?",
        (now, project_id, exclude_id)
    )


def db_sprint_create(conn, id: str, project_id: str, name: str, goal: str | None,
                     status: str, start_date: str | None, end_date: str | None,
                     created_at: str) -> dict:
    conn.execute(
        """INSERT INTO sprints (id, project_id, name, goal, status, start_date, end_date, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id, project_id, name, goal, status, start_date, end_date, created_at, created_at)
    )
    conn.commit()
    return db_sprint_get_by_id(conn, id)


def db_sprint_list(conn, project_id: str, status: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    conditions = ["s.project_id = ?"]
    params: list = [project_id]
    if status:
        conditions.append("s.status = ?")
        params.append(status)
    where = "WHERE " + " AND ".join(conditions)

    total = conn.execute(f"SELECT COUNT(*) FROM sprints s {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM sprints s {where} ORDER BY s.created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()

    result = []
    for row in rows:
        sprint = dict(row)
        counts = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks WHERE sprint_id = ? GROUP BY status",
            (sprint["id"],)
        ).fetchall()
        task_counts = {"backlog": 0, "todo": 0, "in_progress": 0, "blocked": 0, "review": 0, "done": 0}
        for c in counts:
            if c["status"] in task_counts:
                task_counts[c["status"]] = c["cnt"]
        task_counts["total"] = sum(v for k, v in task_counts.items() if k != "total")
        sprint["task_counts"] = task_counts
        result.append(sprint)

    return result, total


def db_sprint_update(conn, sprint_id: str, fields: dict, now: str) -> dict | None:
    if not fields:
        return db_sprint_get_by_id(conn, sprint_id)
    set_parts = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [now, sprint_id]
    conn.execute(f"UPDATE sprints SET {set_parts}, updated_at = ? WHERE id = ?", values)
    conn.commit()
    return db_sprint_get_by_id(conn, sprint_id)


_TASK_BOARD_ORDER = """
    ORDER BY CASE t.status
        WHEN 'blocked'     THEN 1
        WHEN 'in_progress' THEN 2
        WHEN 'review'      THEN 3
        WHEN 'todo'        THEN 4
        WHEN 'backlog'     THEN 5
        WHEN 'done'        THEN 6
        ELSE 7
    END,
    CASE t.priority
        WHEN 'critical' THEN 1
        WHEN 'high'     THEN 2
        WHEN 'medium'   THEN 3
        ELSE 4
    END
"""

_TASK_JOIN_COLS = """
    SELECT t.*,
           a1.name AS assigned_to_name,
           a2.name AS created_by_name
    FROM tasks t
    LEFT JOIN agents a1 ON t.assigned_to = a1.id
    LEFT JOIN agents a2 ON t.created_by  = a2.id
"""


def db_sprint_board_tasks(conn, sprint_id: str) -> list[dict]:
    rows = conn.execute(
        f"{_TASK_JOIN_COLS} WHERE t.sprint_id = ? {_TASK_BOARD_ORDER}",
        (sprint_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def db_backlog_tasks(conn, project_id: str) -> list[dict]:
    rows = conn.execute(
        f"{_TASK_JOIN_COLS} WHERE t.project_id = ? AND t.sprint_id IS NULL {_TASK_BOARD_ORDER}",
        (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- Task queries ---

def db_task_get_by_id(conn, task_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def db_task_get_full(conn, task_id: str) -> dict | None:
    row = conn.execute(
        """SELECT t.*,
                  a1.name  AS assigned_to_name,
                  a2.name  AS created_by_name,
                  s.name   AS sprint_name,
                  p.name   AS project_name,
                  th.title AS thread_title
           FROM tasks t
           LEFT JOIN agents  a1 ON t.assigned_to = a1.id
           LEFT JOIN agents  a2 ON t.created_by  = a2.id
           LEFT JOIN sprints s  ON t.sprint_id   = s.id
           LEFT JOIN projects p ON t.project_id  = p.id
           LEFT JOIN threads th ON t.thread_id   = th.id
           WHERE t.id = ?""",
        (task_id,)
    ).fetchone()
    return dict(row) if row else None


def db_task_create(conn, id: str, project_id: str, sprint_id: str | None,
                   title: str, description: str | None, status: str,
                   assigned_to: str | None, created_by: str, priority: str,
                   blocked_reason: str | None, thread_id: str | None,
                   due_date: str | None, created_at: str) -> dict:
    conn.execute(
        """INSERT INTO tasks
           (id, project_id, sprint_id, title, description, status,
            assigned_to, created_by, priority, blocked_reason, thread_id, due_date,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id, project_id, sprint_id, title, description, status,
         assigned_to, created_by, priority, blocked_reason, thread_id, due_date,
         created_at, created_at)
    )
    conn.commit()
    return db_task_get_full(conn, id)


def db_task_list(conn, project_id: str, sprint_id_filter: str | None,
                 status: str | None, assigned_to: str | None, priority: str | None,
                 limit: int, offset: int) -> tuple[list[dict], int]:
    conditions = ["t.project_id = ?"]
    params: list = [project_id]

    if sprint_id_filter is not None:
        if sprint_id_filter == "backlog":
            conditions.append("t.sprint_id IS NULL")
        else:
            conditions.append("t.sprint_id = ?")
            params.append(sprint_id_filter)

    if status:
        conditions.append("t.status = ?")
        params.append(status)
    if assigned_to:
        conditions.append("t.assigned_to = ?")
        params.append(assigned_to)
    if priority:
        conditions.append("t.priority = ?")
        params.append(priority)

    where = "WHERE " + " AND ".join(conditions)
    total = conn.execute(f"SELECT COUNT(*) FROM tasks t {where}", params).fetchone()[0]

    rows = conn.execute(
        f"""SELECT t.id, t.title, t.status, t.priority, t.blocked_reason,
                   t.sprint_id, t.due_date, t.created_at, t.updated_at,
                   a1.name AS assigned_to_name,
                   COALESCE(s.name, 'Backlog') AS sprint_name
            FROM tasks t
            LEFT JOIN agents  a1 ON t.assigned_to = a1.id
            LEFT JOIN sprints s  ON t.sprint_id   = s.id
            {where}
            ORDER BY CASE t.priority
                WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4
            END ASC, t.created_at ASC
            LIMIT ? OFFSET ?""",
        params + [limit, offset]
    ).fetchall()

    return [dict(r) for r in rows], total


def db_task_update(conn, task_id: str, fields: dict, now: str) -> dict | None:
    if not fields:
        return db_task_get_full(conn, task_id)
    set_parts = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [now, task_id]
    conn.execute(f"UPDATE tasks SET {set_parts}, updated_at = ? WHERE id = ?", values)
    conn.commit()
    return db_task_get_full(conn, task_id)


def db_task_assign(conn, task_id: str, agent_id: str | None, now: str) -> None:
    conn.execute(
        "UPDATE tasks SET assigned_to = ?, updated_at = ? WHERE id = ?",
        (agent_id, now, task_id)
    )
    conn.commit()


def db_task_delete(conn, task_id: str) -> str | None:
    """Returns the title of the deleted task, or None if not found."""
    row = conn.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None
    title = row["title"]
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    return title


def db_sprint_tasks_for_session(conn, agent_id: str, project_id: str) -> tuple[list[dict], str | None]:
    """For context_session_start Option C.
    Returns (tasks, sprint_name) if agent has assignments in the active sprint.
    Returns ([], None) if no active sprint or no assigned tasks.
    """
    sprint = db_sprint_get_active(conn, project_id)
    if not sprint:
        return [], None
    rows = conn.execute(
        """SELECT t.id, t.title, t.status, t.priority, t.blocked_reason
           FROM tasks t
           WHERE t.sprint_id = ? AND t.assigned_to = ?
           ORDER BY CASE t.status
               WHEN 'blocked'     THEN 1
               WHEN 'in_progress' THEN 2
               WHEN 'review'      THEN 3
               WHEN 'todo'        THEN 4
               WHEN 'backlog'     THEN 5
               WHEN 'done'        THEN 6
               ELSE 7
           END""",
        (sprint["id"], agent_id)
    ).fetchall()
    return [dict(r) for r in rows], sprint["name"]


# =============================================================================
# V4 — Task Dependencies + Sprint Retrospective
# =============================================================================

def init_db_v4(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS task_dependencies (
            id          TEXT PRIMARY KEY,
            task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            depends_on  TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            created_by  TEXT NOT NULL REFERENCES agents(id),
            created_at  TEXT NOT NULL,
            UNIQUE(task_id, depends_on)
        );

        CREATE INDEX IF NOT EXISTS idx_deps_task ON task_dependencies(task_id);
        CREATE INDEX IF NOT EXISTS idx_deps_on   ON task_dependencies(depends_on);
    """)
    conn.commit()


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


def db_task_get_dependencies(conn, task_id: str) -> dict:
    """
    Returns {'blocks': [...], 'waiting_on': [...]} for a given task.
    Each entry is {id, title, status}.
    """
    waiting_on = conn.execute(
        """SELECT t.id, t.title, t.status
           FROM task_dependencies td
           JOIN tasks t ON td.depends_on = t.id
           WHERE td.task_id = ?""",
        (task_id,)
    ).fetchall()
    blocks = conn.execute(
        """SELECT t.id, t.title, t.status
           FROM task_dependencies td
           JOIN tasks t ON td.task_id = t.id
           WHERE td.depends_on = ?""",
        (task_id,)
    ).fetchall()
    return {
        "waiting_on": [dict(r) for r in waiting_on],
        "blocks":     [dict(r) for r in blocks],
    }


def db_task_add_dependency(conn, id: str, task_id: str, depends_on: str,
                           created_by: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO task_dependencies (id, task_id, depends_on, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (id, task_id, depends_on, created_by, created_at)
    )
    conn.commit()


def db_task_remove_dependency(conn, task_id: str, depends_on: str) -> bool:
    """Returns True if a row was deleted, False if it didn't exist."""
    cursor = conn.execute(
        "DELETE FROM task_dependencies WHERE task_id = ? AND depends_on = ?",
        (task_id, depends_on)
    )
    conn.commit()
    return cursor.rowcount > 0


def db_sprint_retro_data(conn, sprint_id: str) -> dict:
    """
    Gathers all data needed to generate a sprint retrospective.
    Returns a dict with keys: sprint, project, tasks_by_status, agents, linked_threads.
    """
    sprint = db_sprint_get_by_id(conn, sprint_id)
    if not sprint:
        return {}

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (sprint["project_id"],)).fetchone()

    tasks = conn.execute(
        """SELECT t.*, a.name AS assigned_to_name
           FROM tasks t
           LEFT JOIN agents a ON t.assigned_to = a.id
           WHERE t.sprint_id = ?""",
        (sprint_id,)
    ).fetchall()
    tasks = [dict(r) for r in tasks]

    tasks_by_status: dict[str, list] = {}
    agent_ids: set = set()
    thread_ids: set = set()
    for t in tasks:
        tasks_by_status.setdefault(t["status"], []).append(t)
        if t.get("assigned_to"):
            agent_ids.add(t["assigned_to"])
        if t.get("thread_id"):
            thread_ids.add(t["thread_id"])

    agents = []
    if agent_ids:
        placeholders = ",".join("?" * len(agent_ids))
        agents = conn.execute(
            f"SELECT id, name FROM agents WHERE id IN ({placeholders})",
            list(agent_ids)
        ).fetchall()
        agents = [dict(r) for r in agents]

    return {
        "sprint":          dict(sprint),
        "project":         dict(project) if project else {},
        "tasks_by_status": tasks_by_status,
        "all_tasks":       tasks,
        "agents":          agents,
        "linked_threads":  list(thread_ids),
    }
