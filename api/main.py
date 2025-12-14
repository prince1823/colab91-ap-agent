"""FastAPI application for HITL backend."""

import logging
from typing import List

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.exceptions import (
    DatasetNotFoundError,
    FeedbackNotFoundError,
    InvalidDatasetIdError,
    InvalidFeedbackStateError,
    TransactionNotFoundError,
)
from api.routers import classification, datasets, feedback, supplier_rules, transactions
from core.config import get_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Spend Classification Backend API",
    description="Backend API for spend classification, including transaction management, HITL feedback, and supplier rules",
    version="1.0.0",
)

# Get CORS origins from config (default to empty list for security)
config = get_config()
# CORS origins can be set via CORS_ORIGINS env var as comma-separated list
cors_origins_str: str = getattr(config, "cors_origins", "")
cors_origins: List[str] = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()] if cors_origins_str else []

# Add CORS middleware with configurable origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ["*"],  # Default to * for development
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["X-Total-Count", "X-Page", "X-Pages"],
)


# Exception handlers
@app.exception_handler(DatasetNotFoundError)
async def dataset_not_found_handler(request: Request, exc: DatasetNotFoundError):
    """Handle dataset not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error_type": "DatasetNotFoundError"},
    )


@app.exception_handler(InvalidDatasetIdError)
async def invalid_dataset_id_handler(request: Request, exc: InvalidDatasetIdError):
    """Handle invalid dataset ID errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "error_type": "InvalidDatasetIdError"},
    )


@app.exception_handler(TransactionNotFoundError)
async def transaction_not_found_handler(request: Request, exc: TransactionNotFoundError):
    """Handle transaction not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error_type": "TransactionNotFoundError"},
    )


@app.exception_handler(FeedbackNotFoundError)
async def feedback_not_found_handler(request: Request, exc: FeedbackNotFoundError):
    """Handle feedback not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "error_type": "FeedbackNotFoundError"},
    )


@app.exception_handler(InvalidFeedbackStateError)
async def invalid_feedback_state_handler(request: Request, exc: InvalidFeedbackStateError):
    """Handle invalid feedback state errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "error_type": "InvalidFeedbackStateError"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    # Convert errors to JSON-serializable format
    errors = exc.errors()
    # Ensure all error values are strings
    serializable_errors = []
    for error in errors:
        serializable_error = {}
        for key, value in error.items():
            # Convert non-serializable values to strings
            if isinstance(value, (ValueError, Exception)):
                serializable_error[key] = str(value)
            else:
                serializable_error[key] = value
        serializable_errors.append(serializable_error)
    
    logger.warning(f"Validation error: {serializable_errors}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": serializable_errors, "error_type": "ValidationError"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    # Ensure error detail is always a string, not an exception object
    error_detail = str(exc) if exc else "Internal server error"
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": error_detail, "error_type": type(exc).__name__},
    )

# Include routers
app.include_router(datasets.router)
app.include_router(transactions.router)
app.include_router(feedback.router)
app.include_router(supplier_rules.router)
app.include_router(classification.router)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": "Spend Classification Backend API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy"}
