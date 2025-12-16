"""
Vercel serverless function wrapper for FastAPI application.
This file is used by Vercel to handle API requests.
"""

import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.main import app
from mangum import Mangum

# Create Mangum handler for Vercel
# Mangum converts ASGI (FastAPI) to AWS Lambda format that Vercel uses
handler = Mangum(app, lifespan="off")

