from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

from db import (
    db_list_projects, db_get_project_thread_counts, db_sprint_get_active,
    db_get_project_by_id, db_list_agents, db_presence_get,
    db_sprint_board_tasks, db_task_get_dependencies, db_sprint_list,
    db_list_threads, db_get_thread_by_id, db_get_thread_entries,
    db_task_list, db_handoff_get_recent, db_list_global_skills
)

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

def humanize_time(diff):
    s = diff.total_seconds()
    if s < 60: return "just now"
    if s < 3600: return f"{int(s//60)} mins ago"
    if s < 86400: return f"{int(s//3600)} hours ago"
    return f"{int(s//86400)} days ago"

# 1. /api/health
@app.get("/api/health")
def health():
    return {"status": "ok", "db": "connected", "timestamp": str(datetime.now(timezone.utc))}

# 2. /api/projects
@app.get("/api/projects")
def get_projects():
    with get_db() as conn:
        projects, _ = db_list_projects(conn, None, 100, 0)
        for p in projects:
            counts = db_get_project_thread_counts(conn, p["id"])
            p["thread_count"] = counts["total"]
            
            ac = conn.execute("""
                SELECT COUNT(DISTINCT e.agent_id) 
                FROM entries e 
                JOIN threads t ON e.thread_id = t.id 
                WHERE t.project_id = ?
            """, (p["id"],)).fetchone()[0]
            p["agent_count"] = ac
            
            sprint = db_sprint_get_active(conn, p["id"])
            if sprint:
                p["active_sprint"] = {"id": sprint["id"], "name": sprint["name"]}
            else:
                p["active_sprint"] = None
        return projects

# 3. /api/projects/{project_id}
@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    with get_db() as conn:
        p = db_get_project_by_id(conn, project_id)
        if not p:
            raise HTTPException(status_code=404, detail="Project not found")
        
        counts = db_get_project_thread_counts(conn, project_id)
        p["open_thread_count"] = counts["open"]
        p["resolved_thread_count"] = counts["resolved"]
        
        ac = conn.execute("""
            SELECT COUNT(DISTINCT e.agent_id) 
            FROM entries e 
            JOIN threads t ON e.thread_id = t.id 
            WHERE t.project_id = ?
        """, (project_id,)).fetchone()[0]
        p["agent_count"] = ac
        
        sprint = db_sprint_get_active(conn, project_id)
        if sprint:
            task_counts = conn.execute("""
                SELECT status, COUNT(*) as cnt 
                FROM tasks WHERE sprint_id = ? GROUP BY status
            """, (sprint["id"],)).fetchall()
            tc = {c["status"]: c["cnt"] for c in task_counts}
            p["active_sprint"] = {
                "id": sprint["id"],
                "name": sprint["name"],
                "task_counts": tc
            }
        else:
            p["active_sprint"] = None
            
        return p

# 4. /api/agents
@app.get("/api/agents")
def get_agents():
    with get_db() as conn:
        agents = db_list_agents(conn)
        presence_list = db_presence_get(conn, None)
        presence_map = {p["agent_id"]: p for p in presence_list}
        
        result = []
        for a in agents:
            p = presence_map.get(a["id"])
            res = {
                "id": a["id"],
                "name": a["name"],
                "type": a["type"]
            }
            if p:
                res["status"] = p["status"]
                res["current_task"] = p["current_task"]
                res["project_name"] = p["project_name"]
                res["last_seen"] = p["updated_at"]
                if p["updated_at"]:
                    try:
                        diff = datetime.now(timezone.utc) - datetime.fromisoformat(p["updated_at"].replace('Z', '+00:00'))
                        res["last_seen_human"] = humanize_time(diff)
                    except ValueError:
                        res["last_seen_human"] = "unknown"
                else:
                    res["last_seen_human"] = "never"
            else:
                res["status"] = "idle"
                res["current_task"] = None
                res["project_name"] = None
                res["last_seen"] = None
                res["last_seen_human"] = "never"
            result.append(res)
        return result

# 5. /api/projects/{project_id}/sprint
@app.get("/api/projects/{project_id}/sprint")
def get_sprint(project_id: str):
    with get_db() as conn:
        sprint = db_sprint_get_active(conn, project_id)
        if not sprint:
            return {"sprint": None, "board": None, "summary": None}
        
        tasks = db_sprint_board_tasks(conn, sprint["id"])
        
        board = {
            "backlog": [],
            "todo": [],
            "in_progress": [],
            "blocked": [],
            "review": [],
            "done": []
        }
        summary = {"total": len(tasks), "done": 0, "blocked": 0, "in_progress": 0}
        
        for t in tasks:
            deps = db_task_get_dependencies(conn, t["id"])
            t["depends_on"] = deps["waiting_on"]
            t["blocks"] = deps["blocks"]
            
            st = t["status"]
            if st in board:
                board[st].append(t)
            else:
                board.setdefault(st, []).append(t)
                
            if st in summary:
                summary[st] += 1
                
        return {
            "sprint": sprint,
            "board": board,
            "summary": summary
        }

# 6. /api/projects/{project_id}/sprints
@app.get("/api/projects/{project_id}/sprints")
def get_sprints(project_id: str):
    with get_db() as conn:
        sprints, _ = db_sprint_list(conn, project_id, None, 100, 0)
        res = []
        for s in sprints:
            res.append({
                "id": s["id"],
                "name": s["name"],
                "status": s["status"],
                "goal": s["goal"],
                "start_date": s["start_date"],
                "end_date": s["end_date"],
                "task_count": s["task_counts"].get("total", 0),
                "done_count": s["task_counts"].get("done", 0),
                "created_at": s["created_at"]
            })
        return res

# 7. /api/projects/{project_id}/threads
@app.get("/api/projects/{project_id}/threads")
def get_threads(project_id: str, limit: int = Query(20), offset: int = Query(0)):
    with get_db() as conn:
        threads, _ = db_list_threads(conn, project_id, None, limit, offset)
        res = []
        for t in threads:
            last_entry = conn.execute("""
                SELECT e.created_at, a.name 
                FROM entries e JOIN agents a ON e.agent_id = a.id 
                WHERE e.thread_id = ? ORDER BY e.created_at DESC LIMIT 1
            """, (t["id"],)).fetchone()
            res.append({
                "id": t["id"],
                "title": t["title"],
                "status": t["status"],
                "entry_count": t["entry_count"],
                "created_at": t["created_at"],
                "last_entry_at": last_entry["created_at"] if last_entry else None,
                "last_entry_agent": last_entry["name"] if last_entry else None
            })
        return res

# 8. /api/threads/{thread_id}/entries
@app.get("/api/threads/{thread_id}/entries")
def get_entries(thread_id: str, limit: int = Query(50), offset: int = Query(0)):
    with get_db() as conn:
        thread = db_get_thread_by_id(conn, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        project = db_get_project_by_id(conn, thread["project_id"])
        
        entries, total = db_get_thread_entries(conn, thread_id, None, None, False, "asc", limit, offset)
        
        return {
            "thread": {
                "id": thread["id"],
                "title": thread["title"],
                "status": thread["status"],
                "project_name": project["name"] if project else None
            },
            "entries": entries,
            "total": total,
            "has_more": (offset + limit) < total
        }

# 9. /api/projects/{project_id}/activity
@app.get("/api/projects/{project_id}/activity")
def get_activity(project_id: str, limit: int = Query(30)):
    with get_db() as conn:
        entries = conn.execute("""
            SELECT e.id, e.type, e.content as text, e.created_at, e.thread_id,
                   t.title as thread_title, a.name as agent_name, a.type as agent_type,
                   'entry' as item_type
            FROM entries e
            JOIN threads t ON e.thread_id = t.id
            JOIN agents a ON e.agent_id = a.id
            WHERE t.project_id = ?
            ORDER BY e.created_at DESC LIMIT ?
        """, (project_id, limit)).fetchall()
        
        messages = conn.execute("""
            SELECT m.id, m.subject as text, m.priority, m.is_read, m.created_at,
                   fa.name as from_agent_name, ta.name as to_agent_name,
                   'message' as item_type
            FROM agent_messages m
            JOIN agents fa ON m.from_agent_id = fa.id
            LEFT JOIN agents ta ON m.to_agent_id = ta.id
            WHERE m.project_id = ?
            ORDER BY m.created_at DESC LIMIT ?
        """, (project_id, limit)).fetchall()
        
        combined = [dict(r) for r in entries] + [dict(r) for r in messages]
        combined.sort(key=lambda x: x["created_at"], reverse=True)
        combined = combined[:limit]
        
        res = []
        for item in combined:
            try:
                diff = datetime.now(timezone.utc) - datetime.fromisoformat(item["created_at"].replace('Z', '+00:00'))
                ts_human = humanize_time(diff)
            except Exception:
                ts_human = "unknown"
                
            if item["item_type"] == "entry":
                action = "posted a " + item["type"]
                text_content = str(item["text"])
                res.append({
                    "type": "entry",
                    "agent_name": item["agent_name"],
                    "agent_type": item["agent_type"],
                    "action": action,
                    "thread_id": item["thread_id"],
                    "thread_title": item["thread_title"],
                    "entry_id": item["id"],
                    "content_preview": text_content[:80] + ("..." if len(text_content) > 80 else ""),
                    "timestamp": item["created_at"],
                    "timestamp_human": ts_human
                })
            else:
                res.append({
                    "type": "message",
                    "from_agent": item["from_agent_name"],
                    "to_agent": item["to_agent_name"] or "broadcast",
                    "subject": item["text"],
                    "priority": item["priority"],
                    "priority_flag": item["priority"] == "high" and not item["is_read"],
                    "is_read": bool(item["is_read"]),
                    "timestamp": item["created_at"],
                    "timestamp_human": ts_human
                })
        return res

# 10. /api/projects/{project_id}/tasks
@app.get("/api/projects/{project_id}/tasks")
def get_tasks(project_id: str, status: Optional[str] = None, limit: int = Query(20)):
    with get_db() as conn:
        tasks, _ = db_task_list(conn, project_id, None, status, None, None, limit, 0)
        return tasks

# 11. /api/projects/{project_id}/handoffs
@app.get("/api/projects/{project_id}/handoffs")
def get_handoffs(project_id: str, limit: int = Query(1)):
    with get_db() as conn:
        handoffs = db_handoff_get_recent(conn, project_id, limit)
        for h in handoffs:
            try:
                diff = datetime.now(timezone.utc) - datetime.fromisoformat(h["created_at"].replace('Z', '+00:00'))
                h["created_at_human"] = humanize_time(diff)
            except Exception:
                h["created_at_human"] = "unknown"
        return handoffs

# 12. /api/projects/{project_id}/skills
@app.get("/api/projects/{project_id}/skills")
def get_skills(project_id: str):
    with get_db() as conn:
        skills, _ = db_list_global_skills(conn, project_id, None, None, 100, 0)
        # Keep response lean
        lean_skills = []
        for s in skills:
            lean_skills.append({
                "id": s["id"],
                "name": s["name"],
                "skill_type": s["skill_type"],
                "description": s["description"],
                "version": s["version"],
                "scope": s.get("scope", "global"),
                "updated_at": s["updated_at"]
            })
        return lean_skills
