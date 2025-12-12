"""FastAPI backend for results display and feedback collection."""

import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import yaml

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.pipeline import SpendClassificationPipeline
from core.agents.column_canonicalization.canonical_columns import (
    get_canonical_columns_metadata,
)
from core.agents.feedback_analysis import FeedbackAnalyzer
from core.actions.executor import ActionExecutor
from pathlib import Path

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
# Use absolute paths relative to the project root (parent of api/)
BASE_DIR = Path(__file__).parent.parent
FEEDBACK_DIR = BASE_DIR / "feedback"
FEEDBACK_DIR.mkdir(exist_ok=True)
RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)
NORMALIZED_OVERRIDES_FILE = BASE_DIR / "normalized_column_overrides.json"


def load_saved_overrides() -> Dict[str, str]:
    """Load normalized column overrides from disk."""
    if not NORMALIZED_OVERRIDES_FILE.exists():
        return {}
    try:
        with NORMALIZED_OVERRIDES_FILE.open("r") as f:
            data = json.load(f)
        return {
            col: name
            for col, name in data.items()
            if isinstance(col, str) and isinstance(name, str) and name.strip()
        }
    except Exception:
        # On any read/parse error, fall back to defaults without raising
        return {}


def save_overrides(overrides: Dict[str, str]) -> None:
    """Persist normalized column overrides to disk."""
    with NORMALIZED_OVERRIDES_FILE.open("w") as f:
        json.dump(overrides, f, indent=2)


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


class NormalizedColumnOverrides(BaseModel):
    """Overrides for canonical/normalized column display names."""
    overrides: Dict[str, str]


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
    try:
        # Ensure RESULTS_DIR exists
        if not RESULTS_DIR.exists():
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Find all CSV files
        csv_files = list(RESULTS_DIR.glob("*.csv"))
        if not csv_files:
            return {"results": [], "message": f"No CSV files found in {RESULTS_DIR.absolute()}"}
        
        for file in sorted(csv_files, key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                # Skip row counting for list endpoint to avoid hanging on large files
                # Row count will be shown when file is actually loaded
                file_size = file.stat().st_size
                
                # Quick estimation for display only (avoid reading entire file)
                # Estimate based on file size - rough approximation
                if file_size > 0:
                    # Rough estimate: assume average 200-500 bytes per row
                    estimated_rows = max(0, int(file_size / 300))
                else:
                    estimated_rows = 0
                
                iteration = 0
                if "_iter" in file.stem:
                    parts = file.stem.split("_iter")
                    if len(parts) > 1:
                        try:
                            iteration = int(parts[-1])
                        except ValueError:
                            iteration = 0
                
                result_files.append({
                    "filename": file.name,
                    "timestamp": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
                    "row_count": estimated_rows,  # Estimated, actual count shown when loaded
                    "iteration": iteration,
                })
            except Exception as e:
                # Log but continue processing other files
                import logging
                logging.warning(f"Error processing file {file.name}: {e}")
                continue
        
        return {"results": result_files}
    except Exception as e:
        import traceback
        error_detail = f"Error listing results: {str(e)}\n{traceback.format_exc()}\nRESULTS_DIR: {RESULTS_DIR.absolute()}"
        raise HTTPException(status_code=500, detail=error_detail)


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


class ProcessFeedbackRequest(BaseModel):
    """Request to process feedback and generate proposals."""
    result_file: str
    feedback_item_index: int
    taxonomy_path: Optional[str] = None


class ActionProposal(BaseModel):
    """Action proposal from feedback analysis."""
    action_type: str
    description: str
    proposed_change: str
    metadata: Dict[str, Any]


@app.post("/api/feedback/process", response_model=ActionProposal)
async def process_feedback(request: ProcessFeedbackRequest):
    """Process feedback and generate action proposal."""
    # Load feedback file
    feedback_files = sorted(FEEDBACK_DIR.glob(f"feedback_{request.result_file}_*.json"))
    if not feedback_files:
        raise HTTPException(status_code=404, detail="Feedback file not found")
    
    # Use most recent feedback file
    with open(feedback_files[-1], "r") as f:
        feedback_data = json.load(f)
    
    feedback_items = feedback_data.get("feedback_items", [])
    if request.feedback_item_index >= len(feedback_items):
        raise HTTPException(status_code=404, detail="Feedback item index out of range")
    
    feedback_item = feedback_items[request.feedback_item_index]
    
    # Load result file to get transaction data
    result_path = RESULTS_DIR / request.result_file
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    result_df = pd.read_csv(result_path)
    row_idx = feedback_item.get("row_index", 0)
    if row_idx >= len(result_df):
        raise HTTPException(status_code=404, detail="Row index out of range")
    
    transaction_row = result_df.iloc[row_idx]
    transaction_data = transaction_row.to_dict()
    
    # Get taxonomy path
    taxonomy_path = request.taxonomy_path
    if not taxonomy_path:
        # Try to infer from result file or use default
        taxonomy_path = "taxonomies/FOX_20230816_161348.yaml"
    
    base_dir = Path(__file__).parent.parent
    taxonomy_file = Path(taxonomy_path)
    if not taxonomy_file.is_absolute():
        taxonomy_file = base_dir / taxonomy_file
    
    if not taxonomy_file.exists():
        raise HTTPException(status_code=404, detail=f"Taxonomy file not found: {taxonomy_file}")
    
    # Prepare supplier context (simplified for now)
    supplier_context = {
        "supplier_name": transaction_data.get("supplier_name", ""),
    }
    
    # Analyze feedback
    analyzer = FeedbackAnalyzer()
    
    # Add original classification to feedback item
    original_classification = {
        "L1": transaction_data.get("L1"),
        "L2": transaction_data.get("L2"),
        "L3": transaction_data.get("L3"),
        "L4": transaction_data.get("L4"),
        "L5": transaction_data.get("L5"),
    }
    feedback_item["original_classification"] = original_classification
    
    # Extract corrected classification to metadata
    action_metadata = {
        "corrected_l1": feedback_item.get("corrected_l1"),
        "corrected_l2": feedback_item.get("corrected_l2"),
        "corrected_l3": feedback_item.get("corrected_l3"),
        "corrected_l4": feedback_item.get("corrected_l4"),
        "corrected_l5": feedback_item.get("corrected_l5"),
        "supplier_name": transaction_data.get("supplier_name"),
        "gl_code": transaction_data.get("gl_code"),
    }
    
    action = analyzer.analyze_feedback(
        feedback_item=feedback_item,
        transaction_data=transaction_data,
        supplier_context=supplier_context,
        taxonomy_path=taxonomy_file,
    )
    
    # Merge action metadata with feedback metadata
    action.metadata.update(action_metadata)
    
    return {
        "action_type": action.action_type.value,
        "description": action.description,
        "proposed_change": action.proposed_change,
        "metadata": action.metadata,
    }


class ApproveActionRequest(BaseModel):
    """Request to approve and execute an action."""
    result_file: str
    feedback_item_index: int
    action_proposal: ActionProposal
    edited_text: Optional[str] = None
    taxonomy_path: Optional[str] = None


@app.post("/api/feedback/approve")
async def approve_action(request: ApproveActionRequest):
    """Approve and execute feedback action."""
    # Load result file
    result_path = RESULTS_DIR / request.result_file
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    result_df = pd.read_csv(result_path)
    
    # Get taxonomy path
    taxonomy_path = request.taxonomy_path
    if not taxonomy_path:
        taxonomy_path = "taxonomies/FOX_20230816_161348.yaml"
    
    base_dir = Path(__file__).parent.parent
    taxonomy_file = Path(taxonomy_path)
    if not taxonomy_file.is_absolute():
        taxonomy_file = base_dir / taxonomy_file
    
    # Create action executor
    executor = ActionExecutor(taxonomy_path=taxonomy_file, results_df=result_df)
    
    # Convert proposal back to action
    from core.agents.feedback_analysis.model import FeedbackAction, ActionType
    action = FeedbackAction(
        action_type=ActionType(request.action_proposal.action_type),
        description=request.action_proposal.description,
        proposed_change=request.edited_text or request.action_proposal.proposed_change,
        metadata=request.action_proposal.metadata,
    )
    
    # Find applicable rows
    applicable_rows = executor.find_applicable_rows(action, result_df)
    
    # Execute action
    execution_result = executor.execute_action(action, request.edited_text)
    
    # If supplier DB or rule action, return applicable rows for bulk approval
    if action.action_type.value in ["supplier_db_update", "rule_creation"]:
        applicable_data = applicable_rows.to_dict("records") if not applicable_rows.empty else []
        return {
            "status": "success",
            "execution_result": execution_result,
            "applicable_rows_count": len(applicable_rows),
            "applicable_rows": applicable_data[:100],  # Limit to first 100 for response
            "requires_bulk_approval": len(applicable_rows) > 0,
        }
    
    return {
        "status": "success",
        "execution_result": execution_result,
        "requires_bulk_approval": False,
    }


class ApplyBulkChangesRequest(BaseModel):
    """Request to apply bulk changes."""
    result_file: str
    action_proposal: ActionProposal
    approved: bool


@app.post("/api/feedback/apply-bulk")
async def apply_bulk_changes(request: ApplyBulkChangesRequest):
    """Apply bulk changes to results file."""
    if not request.approved:
        return {"status": "cancelled", "message": "Bulk changes not approved"}
    
    # Load result file
    result_path = RESULTS_DIR / request.result_file
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    result_df = pd.read_csv(result_path)
    
    # Create action executor
    executor = ActionExecutor(results_df=result_df)
    
    # Convert proposal to action
    from core.agents.feedback_analysis.model import FeedbackAction, ActionType
    action = FeedbackAction(
        action_type=ActionType(request.action_proposal.action_type),
        description=request.action_proposal.description,
        proposed_change=request.action_proposal.proposed_change,
        metadata=request.action_proposal.metadata,
    )
    
    # Find applicable rows
    applicable_rows = executor.find_applicable_rows(action, result_df)
    
    # Apply bulk changes
    updated_df = executor.apply_bulk_changes(action, applicable_rows, result_df)
    
    # Save updated file (append _updated to filename)
    output_path = result_path.parent / f"{result_path.stem}_updated{result_path.suffix}"
    updated_df.to_csv(output_path, index=False)
    
    return {
        "status": "success",
        "updated_file": output_path.name,
        "rows_updated": len(applicable_rows),
        "total_rows": len(result_df),
    }


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
    columns = get_canonical_columns_metadata()
    saved_overrides = load_saved_overrides()
    resolved_overrides = {
        col["canonical_name"]: saved_overrides.get(col["canonical_name"], col["canonical_name"])
        for col in columns
    }
    return {"columns": columns, "overrides": resolved_overrides}


@app.get("/api/normalized-column-overrides")
async def get_normalized_column_overrides():
    """Return canonical column metadata with any saved normalized name overrides."""
    columns = get_canonical_columns_metadata()
    saved_overrides = load_saved_overrides()
    resolved_overrides = {
        col["canonical_name"]: saved_overrides.get(col["canonical_name"], col["canonical_name"])
        for col in columns
    }
    return {"columns": columns, "overrides": resolved_overrides}


@app.post("/api/normalized-column-overrides")
async def update_normalized_column_overrides(payload: NormalizedColumnOverrides):
    """Persist normalized column name overrides for reuse across sessions."""
    columns = get_canonical_columns_metadata()
    valid_columns = {col["canonical_name"] for col in columns}

    cleaned_overrides = {}
    for canonical_name in valid_columns:
        incoming_value = payload.overrides.get(canonical_name)
        if isinstance(incoming_value, str) and incoming_value.strip():
            cleaned_overrides[canonical_name] = incoming_value.strip()
        else:
            cleaned_overrides[canonical_name] = canonical_name

    try:
        save_overrides(cleaned_overrides)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save overrides: {str(exc)}")

    return {"status": "success", "overrides": cleaned_overrides}


@app.get("/api/taxonomy/{taxonomy_file}/structure")
async def get_taxonomy_structure(taxonomy_file: str):
    """Get taxonomy structure for populating dropdowns (L1, L2, L3, L4)."""
    base_dir = Path(__file__).parent.parent
    taxonomy_path = base_dir / "taxonomies" / taxonomy_file
    
    if not taxonomy_path.exists():
        raise HTTPException(status_code=404, detail=f"Taxonomy file not found: {taxonomy_file}")
    
    try:
        with open(taxonomy_path, 'r') as f:
            taxonomy_data = yaml.safe_load(f)
        
        # Extract taxonomy paths
        taxonomy_list = taxonomy_data.get("taxonomy", [])
        
        # Build hierarchical structure
        structure = {
            "L1": [],
            "L2": {},
            "L3": {},
            "L4": {},
        }
        
        for path in taxonomy_list:
            parts = [p.strip() for p in path.split("|")]
            
            # L1
            if len(parts) > 0 and parts[0] not in structure["L1"]:
                structure["L1"].append(parts[0])
            
            # L2 (grouped by L1)
            if len(parts) > 1:
                l1 = parts[0]
                if l1 not in structure["L2"]:
                    structure["L2"][l1] = []
                if parts[1] not in structure["L2"][l1]:
                    structure["L2"][l1].append(parts[1])
            
            # L3 (grouped by L1|L2)
            if len(parts) > 2:
                l1_l2 = f"{parts[0]}|{parts[1]}"
                if l1_l2 not in structure["L3"]:
                    structure["L3"][l1_l2] = []
                if parts[2] not in structure["L3"][l1_l2]:
                    structure["L3"][l1_l2].append(parts[2])
            
            # L4 (grouped by L1|L2|L3)
            if len(parts) > 3:
                l1_l2_l3 = f"{parts[0]}|{parts[1]}|{parts[2]}"
                if l1_l2_l3 not in structure["L4"]:
                    structure["L4"][l1_l2_l3] = []
                if parts[3] not in structure["L4"][l1_l2_l3]:
                    structure["L4"][l1_l2_l3].append(parts[3])
        
        # Sort all lists
        structure["L1"].sort()
        for l1 in structure["L2"]:
            structure["L2"][l1].sort()
        for key in structure["L3"]:
            structure["L3"][key].sort()
        for key in structure["L4"]:
            structure["L4"][key].sort()
        
        return {
            "taxonomy_file": taxonomy_file,
            "max_depth": taxonomy_data.get("max_taxonomy_depth", 3),
            "structure": structure,
        }
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Error loading taxonomy: {str(e)}\n{traceback.format_exc()}")


@app.get("/api/taxonomy/list")
async def list_taxonomies():
    """List all available taxonomy files."""
    base_dir = Path(__file__).parent.parent
    taxonomies_dir = base_dir / "taxonomies"
    
    if not taxonomies_dir.exists():
        return {"taxonomies": []}
    
    taxonomy_files = []
    for file in sorted(taxonomies_dir.glob("*.yaml")):
        try:
            with open(file, 'r') as f:
                data = yaml.safe_load(f)
                taxonomy_files.append({
                    "filename": file.name,
                    "client_name": data.get("client_name", ""),
                    "project_id": data.get("project_id", ""),
                    "max_depth": data.get("max_taxonomy_depth", 3),
                })
        except Exception:
            continue
    
    return {"taxonomies": taxonomy_files}


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

