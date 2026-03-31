#!/bin/bash

# Agent Mind Bridge — Start all services
# Usage: ./start.sh

set -e

echo "Starting Agent Mind Bridge..."

# 1. Environment Check
if [ ! -f ".env" ]; then
    echo "  [!] Warning: .env file not found. Copying from .env.example..."
    cp .env.example .env
fi

# 2. Dependency Check (Dashboard)
if [ ! -d "dashboard/node_modules" ]; then
    echo "  [*] Installing dashboard dependencies (npm install)..."
    cd dashboard && npm install && cd ..
fi

# 3. Start Services
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
