"""
HOSU Unified Production Server:
- Serves Flask REST APIs & Frontend at /api/* and /
- Serves Remote Public MCP Server over SSE at /sse and /messages
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "1_data_infrastructure"))
sys.path.insert(0, os.path.join(BASE_DIR, "1_data_infrastructure", "mcp_server"))
sys.path.insert(0, os.path.join(BASE_DIR, "2_regional_service"))

from server import mcp
from app import app as flask_app
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.middleware.cors import CORSMiddleware

try:
    from mcp.server.transport_security import TransportSecuritySettings
    security_settings = TransportSecuritySettings(enable_dns_rebinding_protection=False)
except ImportError:
    security_settings = None

try:
    from a2wsgi import WSGIMiddleware
except ImportError:
    from starlette.middleware.wsgi import WSGIMiddleware

# 1. MCP SSE Starlette App configured for public cloud hosting
if security_settings:
    mcp_sse_app = mcp.sse_app(transport_security=security_settings, host="0.0.0.0")
else:
    mcp_sse_app = mcp.sse_app(host="0.0.0.0")

# 2. Flask WSGI -> ASGI Middleware
flask_asgi = WSGIMiddleware(flask_app)

# 3. Combined Unified Application with CORS
app = Starlette(
    routes=[
        *mcp_sse_app.routes,
        Mount("/", app=flask_asgi),
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
