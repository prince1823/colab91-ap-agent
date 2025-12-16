"""
Vercel entrypoint for the FastAPI application.

This file simply exposes the ASGI `app` object for the @vercel/python
builder, following the official FastAPI on Vercel pattern.
"""

from api.main import app

