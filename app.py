"""
Main application module for the MCP communicator.

This module initializes the FastMCP server and sets up the SQLite database using WAL mode.
ngrok tunnel management has been moved to server.py for eager startup before mcp.run().
"""
import os
import sqlite3
from contextlib import asynccontextmanager

from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from db import init_db, init_db_v2, init_db_v3, init_db_v4

load_dotenv(Path(__file__).parent / ".env", override=True)

DB_PATH = os.getenv("DB_PATH", "shared_context.db")
HOST    = os.getenv("HOST", "127.0.0.1")
PORT    = int(os.getenv("PORT", "3333"))


@asynccontextmanager
async def lifespan(server):
    """
    Manage the lifecycle of the FastMCP server.

    Initializes the SQLite database with WAL and foreign keys enabled, sets up the schema,
    and closes the database on server shutdown.

    Args:
        server (FastMCP): The FastMCP server instance.

    Yields:
        Dict[str, Any]: A dictionary containing the database connection under the 'db' key.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    init_db_v2(conn)
    init_db_v3(conn)
    init_db_v4(conn)

    yield {"db": conn}

    conn.close()


mcp = FastMCP("context_mcp", lifespan=lifespan, host=HOST, port=PORT)
