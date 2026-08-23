"""
HOSU Unified Production Server:
- Serves Flask REST APIs & Frontend at /api/* and /
- Serves Remote Public MCP Server over SSE at /sse and /messages
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "song", "1_data_infrastructure"))
sys.path.insert(0, os.path.join(BASE_DIR, "song", "1_data_infrastructure", "mcp_server"))
sys.path.insert(0, os.path.join(BASE_DIR, "song", "2_regional_service"))

from server import mcp
from app import app as flask_app
from starlette.applications import Starlette
from starlette.routing import Mount

try:
    from a2wsgi import WSGIMiddleware
except ImportError:
    from starlette.middleware.wsgi import WSGIMiddleware

# 1. MCP SSE Starlette App
mcp_sse_app = mcp.sse_app()

# 2. Flask WSGI -> ASGI Middleware
flask_asgi = WSGIMiddleware(flask_app)

# 3. Combined Unified Application
app = Starlette(
    routes=[
        *mcp_sse_app.routes,
        Mount("/", app=flask_asgi),
    ]
)
