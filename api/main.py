"""FastAPI backend for results display and feedback collection."""

import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.pipeline import SpendClassificationPipeline
from core.agents.column_canonicalization.canonical_columns import (
    get_canonical_columns_metadata,
)

app = FastAPI(title="AP Agent Feedback API", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Feedback storage directory
FEEDBACK_DIR = Path("feedback")
FEEDBACK_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


# Pydantic models
class FeedbackItem(BaseModel):
    """Feedback for a single transaction."""
    transaction_id: str
    row_index: int
    feedback_type: str  # "correct", "incorrect", "correction"
    corrected_l1: Optional[str] = None
    corrected_l2: Optional[str] = None
    corrected_l3: Optional[str] = None
    corrected_l4: Optional[str] = None
    corrected_l5: Optional[str] = None
    comment: Optional[str] = None
    rating: Optional[int] = None  # 1-5 rating


class FeedbackBatch(BaseModel):
    """Batch of feedback items."""
    result_file: str
    iteration: int
    feedback_items: List[FeedbackItem]
    user_notes: Optional[str] = None


class RunRequest(BaseModel):
    """Request to run pipeline."""
    input_file: str
    taxonomy_path: str
    iteration: Optional[int] = None
    use_feedback: bool = True
    normalized_column_overrides: Optional[Dict[str, str]] = None


class ResultFile(BaseModel):
    """Result file metadata."""
    filename: str
    timestamp: str
    row_count: int
    iteration: int


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "AP Agent Feedback API"}


@app.get("/api/results")
async def list_results():
    """List all result files."""
    result_files = []
    for file in sorted(RESULTS_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            # Only count rows to avoid heavy load
            with file.open("r", newline="") as f:
                row_count = sum(1 for _ in f) - 1  # header
            iteration = 0
            if "_iter" in file.stem:
                parts = file.stem.split("_iter")
                if len(parts) > 1:
                    iteration = int(parts[-1])
            
            result_files.append({
                "filename": file.name,
                "timestamp": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
                "row_count": row_count,
                "iteration": iteration,
            })
        except Exception:
            continue
    
    return {"results": result_files}


@app.get("/api/results/{filename}")
async def get_result(filename: str):
    """Get a specific result file."""
    file_path = RESULTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    try:
        df = pd.read_csv(file_path)
        
        # Convert to dict format first, then clean NaN values
        records = df.to_dict("records")
        
        # Clean up NaN values in the records (pandas NaN can't be JSON serialized)
        def clean_nan(obj):
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, (float, np.floating)):
                if pd.isna(obj) or np.isnan(obj) or (obj != obj):  # NaN check
                    return None
                if np.isinf(obj):  # Handle infinity
                    return None
                return obj
            elif pd.isna(obj):
                return None
            return obj
        
        records = [clean_nan(record) for record in records]
        
        return {
            "filename": filename,
            "data": records,
            "columns": list(df.columns),
            "row_count": len(df),
        }
    except Exception as e:
        import traceback
        error_detail = f"Error reading file: {str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


@app.get("/api/results/{filename}/page")
async def get_result_page(filename: str, offset: int = 0, limit: int = 500):
    """Get a specific result file page (offset/limit)."""
    file_path = RESULTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    if limit <= 0:
        limit = 1
    if limit > 2000:
        limit = 2000
    if offset < 0:
        offset = 0

    try:
        # Read header
        with file_path.open("r", newline="") as f:
            reader = csv.reader(f)
            headers = next(reader)

        # Read only requested window
        df = pd.read_csv(
            file_path,
            skiprows=range(1, offset + 1),
            nrows=limit,
            names=headers,
            header=0,
        )
        # Count total rows
        with file_path.open("r", newline="") as f:
            total_rows = sum(1 for _ in f) - 1

        records = df.to_dict("records")

        def clean_nan(obj):
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, (float, np.floating)):
                if pd.isna(obj) or np.isnan(obj) or (obj != obj):  # NaN check
                    return None
                if np.isinf(obj):  # Handle infinity
                    return None
                return obj
            elif pd.isna(obj):
                return None
            return obj

        records = [clean_nan(record) for record in records]

        return {
            "filename": filename,
            "data": records,
            "columns": list(df.columns),
            "row_count": len(df),
            "total_rows": total_rows,
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        import traceback
        error_detail = f"Error reading file: {str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)


@app.post("/api/feedback")
async def submit_feedback(feedback_batch: FeedbackBatch):
    """Submit feedback for a batch of transactions."""
    timestamp = datetime.now().isoformat()
    feedback_file = FEEDBACK_DIR / f"feedback_{feedback_batch.result_file}_{feedback_batch.iteration}_{timestamp.replace(':', '-')}.json"
    
    feedback_data = {
        "result_file": feedback_batch.result_file,
        "iteration": feedback_batch.iteration,
        "timestamp": timestamp,
        "user_notes": feedback_batch.user_notes,
        "feedback_items": [item.dict() for item in feedback_batch.feedback_items],
    }
    
    with open(feedback_file, "w") as f:
        json.dump(feedback_data, f, indent=2)
    
    return {"status": "success", "feedback_file": feedback_file.name, "items_count": len(feedback_batch.feedback_items)}


@app.get("/api/feedback/{result_file}")
async def get_feedback(result_file: str):
    """Get all feedback for a specific result file."""
    feedback_files = sorted(FEEDBACK_DIR.glob(f"feedback_{result_file}_*.json"))
    all_feedback = []
    
    for file in feedback_files:
        with open(file, "r") as f:
            all_feedback.append(json.load(f))
    
    return {"result_file": result_file, "feedback_batches": all_feedback}


@app.get("/api/feedback")
async def list_all_feedback():
    """List all feedback files."""
    feedback_files = sorted(FEEDBACK_DIR.glob("feedback_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    feedback_list = []
    
    for file in feedback_files:
        try:
            with open(file, "r") as f:
                data = json.load(f)
                feedback_list.append({
                    "filename": file.name,
                    "result_file": data.get("result_file"),
                    "iteration": data.get("iteration"),
                    "timestamp": data.get("timestamp"),
                    "items_count": len(data.get("feedback_items", [])),
                })
        except Exception:
            continue
    
    return {"feedback": feedback_list}


@app.post("/api/run")
async def run_pipeline(request: RunRequest):
    """Run the pipeline with optional feedback integration."""
    # Handle both absolute and relative paths
    base_dir = Path(__file__).parent.parent
    input_path = Path(request.input_file)
    if not input_path.is_absolute():
        input_path = base_dir / input_path
    
    taxonomy_path = Path(request.taxonomy_path)
    if not taxonomy_path.is_absolute():
        taxonomy_path = base_dir / taxonomy_path
    
    if not input_path.exists():
        raise HTTPException(status_code=404, detail=f"Input file not found: {input_path}")
    if not taxonomy_path.exists():
        raise HTTPException(status_code=404, detail=f"Taxonomy file not found: {taxonomy_path}")
    
    # Load input data
    if input_path.suffix == ".csv":
        df = pd.read_csv(input_path)
    elif input_path.suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(input_path)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format")
    
    # Initialize pipeline
    iteration = request.iteration or 0
    pipeline = SpendClassificationPipeline(
        taxonomy_path=str(taxonomy_path),
        enable_tracing=True
    )
    
    # Process transactions first to get result structure
    result_df = pipeline.process_transactions(
        df,
        normalized_column_overrides=request.normalized_column_overrides,
    )
    
    # Load feedback if requested and available
    if request.use_feedback and iteration > 0:
        # Load feedback from previous iterations
        feedback_examples = load_feedback_examples(request.input_file, iteration - 1)
        if feedback_examples:
            # Integrate feedback into pipeline with result data
            integrate_feedback(pipeline, feedback_examples, result_df)
            
            # Re-process with feedback (optional - you might want to just use it for next run)
            # For now, we'll use feedback in the next iteration
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{input_path.stem}_iter{iteration}_{timestamp}.csv"
    output_path = RESULTS_DIR / output_filename
    result_df.to_csv(output_path, index=False)
    
    return {
        "status": "success",
        "output_file": output_filename,
        "row_count": len(result_df),
        "iteration": iteration,
        "normalized_column_overrides": request.normalized_column_overrides or {},
    }


@app.get("/api/canonical-columns")
async def list_canonical_columns():
    """List canonical columns and metadata for column normalization UI."""
    return {"columns": get_canonical_columns_metadata()}


def load_feedback_examples(input_file: str, max_iteration: int) -> List[Dict]:
    """Load feedback examples from previous iterations."""
    examples = []
    base_name = Path(input_file).stem
    
    for iter_num in range(max_iteration + 1):
        feedback_files = FEEDBACK_DIR.glob(f"feedback_*_iter{iter_num}_*.json")
        for file in feedback_files:
            with open(file, "r") as f:
                data = json.load(f)
                for item in data.get("feedback_items", []):
                    if item.get("feedback_type") == "correction":
                        examples.append({
                            "transaction_id": item.get("transaction_id"),
                            "corrected": {
                                "L1": item.get("corrected_l1"),
                                "L2": item.get("corrected_l2"),
                                "L3": item.get("corrected_l3"),
                                "L4": item.get("corrected_l4"),
                                "L5": item.get("corrected_l5"),
                            },
                            "iteration": iter_num,
                        })
    
    return examples


def integrate_feedback(pipeline: SpendClassificationPipeline, feedback_examples: List[Dict], result_df: pd.DataFrame = None):
    """Integrate feedback examples into the pipeline for improvement."""
    if feedback_examples and result_df is not None:
        # Enrich feedback examples with transaction data
        enriched_examples = []
        for example in feedback_examples:
            # Find matching row in result_df
            transaction_id = example.get('transaction_id')
            # Try to match by supplier_name or row index
            if 'row_index' in example:
                try:
                    row_idx = example['row_index']
                    if row_idx < len(result_df):
                        row = result_df.iloc[row_idx]
                        # Format transaction data
                        transaction_data = {
                            'supplier_name': row.get('supplier_name', ''),
                            'line_description': row.get('line_description', ''),
                            'gl_description': row.get('gl_description', ''),
                            'department': row.get('department', ''),
                            'amount': row.get('amount', ''),
                        }
                        # Get supplier profile if available
                        supplier_profile = {}
                        if 'supplier_name' in row:
                            supplier_name = row['supplier_name']
                            # Try to get from cache or use basic info
                            supplier_profile = {'supplier_name': supplier_name}
                        
                        enriched_examples.append({
                            'transaction_data': transaction_data,
                            'supplier_profile': supplier_profile,
                            'corrected': example.get('corrected', {}),
                        })
                except Exception:
                    continue
        
        # Add examples to classification agent
        if enriched_examples:
            pipeline.classification_agent.add_feedback_examples(enriched_examples)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

