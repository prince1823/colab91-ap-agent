"""FastAPI application for HITL backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import datasets, feedback, transactions

# Create FastAPI app
app = FastAPI(
    title="HITL Backend API",
    description="Human-in-the-Loop backend for post-classification feedback",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(datasets.router)
app.include_router(transactions.router)
app.include_router(feedback.router)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": "HITL Backend API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy"}
