"""
Entry point for the Agent Mind Bridge MCP server.

Starts ngrok (if NGROK_ENABLED=true) eagerly before the MCP server boots,
so the public URL is always printed before the first client connects.
Registers a signal handler for clean tunnel teardown on Ctrl+C / SIGTERM.

To remove ngrok entirely, delete the block between the two
  ── NGROK START / NGROK END ──
markers below. Nothing else needs to change.
"""
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from app import mcp  # noqa: E402 — must come after load_dotenv
import tools  # noqa: F401 — registers all 46 tools onto the mcp instance


# ── NGROK START ────────────────────────────────────────────────────────────────

NGROK_ENABLED   = os.getenv("NGROK_ENABLED", "false").lower() == "true"
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")
NGROK_DOMAIN    = os.getenv("NGROK_DOMAIN", "")
PORT            = int(os.getenv("PORT", "3333"))

_ngrok_tunnel = None  # module-level handle for cleanup


def _start_ngrok() -> None:
    """Start ngrok tunnel before mcp.run() and print the public URL.

    host_header="rewrite" tells ngrok to rewrite the incoming Host header to
    the upstream address (127.0.0.1:PORT) before forwarding. This means the
    MCP server always sees a local Host header and never rejects with 421.
    """
    global _ngrok_tunnel
    if not NGROK_ENABLED:
        return
    try:
        from pyngrok import conf, ngrok

        if NGROK_AUTHTOKEN:
            conf.get_default().auth_token = NGROK_AUTHTOKEN

        options = {"host_header": "rewrite"}
        if NGROK_DOMAIN:
            options["hostname"] = NGROK_DOMAIN

        # pyngrok v7: HTTPS is default, no bind_tls needed
        _ngrok_tunnel = ngrok.connect(str(PORT), **options)
        public_url = _ngrok_tunnel.public_url

        # Normalise to HTTPS just in case
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://", 1)

        mcp_url = f"{public_url}/mcp"
        print(f"\n{'='*60}")
        print(f"  ngrok tunnel active")
        print(f"  Public MCP URL : {mcp_url}")
        print(f"  Use this URL in Claude Desktop and remote agents.")
        print(f"{'='*60}\n")

    except ImportError:
        print("[ngrok] pyngrok not installed — run: pip install pyngrok")
    except Exception as exc:
        print(f"[ngrok] Failed to start tunnel: {exc}")


def _stop_ngrok() -> None:
    """Disconnect all active ngrok tunnels — called on shutdown."""
    global _ngrok_tunnel
    if not NGROK_ENABLED:
        return
    try:
        from pyngrok import ngrok
        ngrok.disconnect_all()
        _ngrok_tunnel = None
    except Exception:
        pass


def _handle_shutdown(signum, frame) -> None:
    """Gracefully tear down ngrok before the process exits."""
    print("\n[server] Shutting down — disconnecting ngrok...")
    _stop_ngrok()
    sys.exit(0)


if NGROK_ENABLED:
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

# ── NGROK END ──────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    _start_ngrok()
    mcp.run(transport="streamable-http")
