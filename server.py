"""Entry point for the MCP communicator server."""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from app import mcp  # noqa: E402 — must come after load_dotenv
import tools  # noqa: F401 — registers all 46 tools onto the mcp instance

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
