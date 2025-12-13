#!/bin/bash

# Start HITL API server

echo "Starting HITL API server..."
echo "API docs will be available at: http://localhost:8000/docs"
echo ""

# Run with poetry
poetry run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
