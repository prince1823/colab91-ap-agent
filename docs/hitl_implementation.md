# HITL (Human-in-the-Loop) Implementation

## Overview

The HITL (Human-in-the-Loop) system enables users to provide feedback on misclassified transactions and automatically determine the appropriate corrective action. The system uses an LLM agent to analyze natural language feedback and propose one of four action types:

1. **Company Context Update** - Update company information (e.g., business focus changed)
2. **Taxonomy Description Update** - Update taxonomy category descriptions
3. **Supplier Rule Creation** - Create rules for supplier-based classification
4. **Transaction Rule Creation** - Create rules based on transaction attributes (e.g., GL codes)

## Architecture

### Data Flow

```
User Feedback
    ↓
FeedbackAction Agent (LLM)
    ↓
Action Proposal
    ↓
User Approval
    ↓
Action Execution
    ↓
Bulk Preview
    ↓
Bulk Application
```

### Components

1. **Frontend (Not Implemented)** - UI for user interactions
2. **FastAPI Backend** - RESTful API for HITL workflows
3. **FeedbackAction Agent** - DSPy-based LLM agent for action planning
4. **DuckDB** - Query CSV files without loading into database
5. **SQLite** - Store feedback workflow state and rules
6. **YAML Files** - Taxonomy and company context storage

---

## Database Schema

### 1. Extended `supplier_classifications` Table

**New Columns Added:**
```sql
supplier_rule_type VARCHAR(20)        -- "category_a" or "category_b"
supplier_rule_paths JSON              -- Array of classification paths
supplier_rule_created_at DATETIME
supplier_rule_active BOOLEAN DEFAULT TRUE
```

**Purpose:** Store supplier-level classification rules globally per dataset.

**Rule Categories:**
- **Category A**: One-to-one mapping (supplier always maps to single classification)
- **Category B**: One-to-many mapping (supplier can map to multiple classifications)

---

### 2. New `user_feedback` Table

```sql
CREATE TABLE user_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Transaction reference
    csv_file_path VARCHAR(500),       -- e.g., "benchmarks/default/innova/output.csv"
    row_index INTEGER,                -- 0-based row index in CSV
    dataset_name VARCHAR(255),

    -- User input
    original_classification VARCHAR(500),
    corrected_classification VARCHAR(500),
    feedback_text TEXT,

    -- LLM output
    action_type VARCHAR(50),          -- "company_context", "taxonomy_description", "supplier_rule", "transaction_rule"
    action_details JSON,              -- Complete action-specific details
    action_reasoning TEXT,

    -- Workflow state
    status VARCHAR(20),               -- "pending", "approved", "applied"
    proposal_text TEXT,               -- Formatted proposal for user
    user_edited_text TEXT,

    -- Timestamps
    created_at DATETIME,
    approved_at DATETIME,
    applied_at DATETIME
);
```

**Purpose:** Track HITL feedback workflow from submission to completion.

**Workflow States:**
- `pending`: Feedback submitted, waiting for user approval
- `approved`: User approved the proposal
- `applied`: Action executed and bulk corrections applied

---

### 3. New `transaction_rules` Table

```sql
CREATE TABLE transaction_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name VARCHAR(255),
    rule_name VARCHAR(255),           -- e.g., "GL 1234 -> Utilities"
    rule_condition JSON,              -- e.g., {"gl_code": "1234"}
    classification_path VARCHAR(500),
    priority INTEGER DEFAULT 10,
    created_at DATETIME,
    active BOOLEAN DEFAULT TRUE
);
```

**Purpose:** Store transaction attribute-based classification rules.

**Example Rules:**
- `{"gl_code": "1234"}` → "facilities|utilities|electricity"
- `{"department": "IT"}` → "it & telecom|it services|support"

---

## API Reference

### Base URL
```
http://localhost:8000/api/v1
```

### Endpoints

#### 1. GET `/datasets`

List available datasets.

**Response:**
```json
[
  {
    "csv_path": "benchmarks/default/innova/output.csv",
    "dataset_name": "innova",
    "foldername": "default",
    "row_count": 1500
  }
]
```

---

#### 2. GET `/transactions`

Query classified transactions from CSV.

**Query Parameters:**
- `csv_path` (required): Path to output CSV
- `l1` (optional): Filter by L1 category
- `confidence` (optional): Filter by confidence level
- `supplier_name` (optional): Filter by supplier name
- `page` (default: 1): Page number
- `limit` (default: 50): Rows per page

**Response:**
```json
{
  "rows": [...],
  "total": 1500,
  "page": 1,
  "pages": 30,
  "limit": 50
}
```

---

#### 3. POST `/feedback`

Submit user feedback.

**Request Body:**
```json
{
  "csv_path": "benchmarks/default/innova/output.csv",
  "row_index": 42,
  "corrected_path": "it & telecom|cloud services|iaas",
  "feedback_text": "This supplier always provides cloud infrastructure services",
  "dataset_name": "innova"
}
```

**Response:**
```json
{
  "feedback_id": 1,
  "action_type": "supplier_rule",
  "proposal_text": "Supplier Rule\nSupplier: AWS\n...",
  "action_details": {
    "supplier_name": "AWS",
    "rule_category": "A",
    "classification_paths": ["it & telecom|cloud services|iaas"]
  }
}
```

---

#### 4. POST `/feedback/{id}/approve`

Approve feedback proposal.

**Request Body:**
```json
{
  "edited_text": "Optional edited proposal text"
}
```

**Response:**
```json
{
  "status": "approved",
  "issues": []
}
```

---

#### 5. GET `/feedback/{id}/preview`

Preview affected rows.

**Response:**
```json
{
  "rows": [...],
  "count": 15,
  "row_indices": [42, 87, 133, ...]
}
```

---

#### 6. POST `/feedback/{id}/apply`

Execute action and apply bulk corrections.

**Request Body:**
```json
{
  "row_indices": [42, 87, 133]
}
```

**Response:**
```json
{
  "updated_count": 3
}
```

---

## FeedbackAction Agent

### DSPy Signature

**Inputs:**
- `original_classification`: Wrong L1|L2|L3|L4 path
- `corrected_classification`: User's correction
- `natural_language_feedback`: User's explanation
- `transaction_data`: Full transaction details (JSON)
- `taxonomy_structure`: Available taxonomy paths
- `taxonomy_descriptions`: Current descriptions
- `company_context`: Current company context

**Outputs:**
- `action_type`: One of 4 action types
- `action_reasoning`: Why this action was chosen
- `action_details`: Complete action-specific details (JSON)

### Action Type Determination

The LLM analyzes natural language feedback to determine the action:

**Action 1 (company_context)**: Triggered by feedback like:
- "Our company pivoted to streaming"
- "We focus on digital media now"
- "Business model changed"

**Action 2 (taxonomy_description)**: Triggered by feedback like:
- "This category includes cloud services"
- "SaaS category should cover subscription software"

**Action 3 (supplier_rule)**: Triggered by feedback like:
- "AWS always provides cloud infrastructure"
- "This supplier is a hardware vendor"

**Action 4 (transaction_rule)**: Triggered by feedback like:
- "GL code 1234 is always utilities"
- "IT department expenses are IT services"

---

## Action Types Detailed

### Action 1: Company Context Update

**Action Details Format:**
```json
{
  "field_name": "business_focus",
  "current_value": "Broadcast Television",
  "proposed_value": "Streaming and Digital Media"
}
```

**Execution:**
- Updates `taxonomies/{dataset_name}.yaml` file
- Modifies `company_context` section
- No database changes

**Formatted Proposal:**
```
Company Context Update
Field: business_focus

Current:
Broadcast Television

Proposed:
Streaming and Digital Media

You can edit the proposed text above before approving.
```

---

### Action 2: Taxonomy Description Update

**Action Details Format:**
```json
{
  "taxonomy_path": "it & telecom|cloud services|iaas",
  "current_description": "Infrastructure as a service...",
  "proposed_description": "Cloud infrastructure including compute, storage, and networking..."
}
```

**Execution:**
- Updates `taxonomies/{dataset_name}.yaml` file
- Modifies `taxonomy_descriptions` section
- No database changes

---

### Action 3: Supplier Rule

**Action Details Format:**
```json
{
  "supplier_name": "AWS",
  "rule_category": "A",
  "classification_paths": ["it & telecom|cloud services|iaas"]
}
```

**Rule Categories:**
- **Category A**: Single classification path (one-to-one)
- **Category B**: Multiple classification paths (one-to-many)

**Execution:**
- Updates `supplier_classifications` table
- Sets `supplier_rule_*` columns for the supplier+dataset
- Global per dataset (not scoped to specific run)

**Bulk Application:**
- Finds all rows with matching `supplier_name` in CSV
- Updates L1, L2, L3, L4 columns
- Sets `override_rule_applied = 'feedback_{id}'`

---

### Action 4: Transaction Rule

**Action Details Format:**
```json
{
  "condition_field": "gl_code",
  "condition_value": "1234",
  "classification_path": "facilities|utilities|electricity",
  "rule_name": "GL 1234 -> Utilities"
}
```

**Execution:**
- Inserts into `transaction_rules` table
- Rule applies to all transactions matching condition

**Bulk Application:**
- Finds all rows where `condition_field = condition_value`
- Updates classification columns
- Sets `override_rule_applied`

---

## Workflow Example

### User Journey

1. **User reviews classified transactions**
   - GET `/transactions?csv_path=...&page=1`
   - Sees row 42 is misclassified

2. **User submits feedback**
   ```json
   POST /feedback
   {
     "csv_path": "benchmarks/default/innova/output.csv",
     "row_index": 42,
     "corrected_path": "it & telecom|cloud services|iaas",
     "feedback_text": "AWS always provides cloud infrastructure",
     "dataset_name": "innova"
   }
   ```

3. **LLM analyzes and proposes action**
   - FeedbackAction agent determines this is a supplier rule (Action 3)
   - Returns proposal: "Create supplier rule for AWS"

4. **User approves proposal**
   ```json
   POST /feedback/1/approve
   {
     "edited_text": null
   }
   ```

5. **User previews affected rows**
   ```json
   GET /feedback/1/preview
   // Returns 15 rows with AWS as supplier
   ```

6. **User applies corrections**
   ```json
   POST /feedback/1/apply
   {
     "row_indices": [42, 87, 133, ...]
   }
   ```

7. **System executes**
   - Creates supplier rule in `supplier_classifications` table
   - Updates 15 rows in output.csv
   - Sets feedback status to "applied"

---

## Design Decisions

### 1. Why DuckDB for CSV Queries?

**Rationale:**
- Query CSV files directly without loading into database
- No data duplication
- Fast SQL queries with pagination and filtering
- Simpler architecture

**Alternative Considered:** Load CSV into SQLite `classified_transactions` table
- **Rejected:** Data duplication, requires ingestion step

---

### 2. Why Global Supplier Rules?

**Rationale:**
- Supplier behavior typically consistent across runs
- Simpler implementation
- Avoids rule duplication

**Alternative Considered:** Per-run supplier rules
- **Rejected:** More complex, likely unnecessary

---

### 3. Why No transaction_snapshot in user_feedback?

**Rationale:**
- Can always read from CSV using `csv_file_path` + `row_index`
- Avoids data duplication
- CSV is source of truth

**Alternative Considered:** Store full transaction in database
- **Rejected:** Redundant data storage

---

### 4. Why Hybrid Approach for Proposal Formatting?

**Rationale:**
- Code retrieves current values from YAML/database
- LLM generates proposed new values
- User sees clear before/after diff
- LLM doesn't need to read files (simpler prompt)

**Alternative Considered:** LLM reads and formats everything
- **Rejected:** More complex, less reliable formatting

---

### 5. CSV Path Convention

**Current:** `benchmarks/{foldername}/{dataset_name}/output.csv`

**Rationale:**
- Matches existing benchmark structure
- Clear organization by dataset
- Easy to scan for available datasets

---

## Future Improvements

### 1. User Authentication
- Add user management system
- Track who created rules and feedback
- Enable `created_by` fields (currently removed for MVP)

### 2. Audit Logging
- Implement `taxonomy_changes` table
- Track all YAML modifications
- Enable rollback capability
- View change history

### 3. Rule Conflict Resolution
- Define priority system for overlapping rules
- Implement conflict detection
- Allow users to resolve conflicts

### 4. Rollback Capability
- Store original values before bulk updates
- Enable undo functionality
- Audit trail for all changes

### 5. Real-time Pipeline Integration
- Integrate HITL into classification pipeline
- Pause on low-confidence classifications
- Get user feedback in real-time
- Continue processing after feedback

### 6. Multi-user Concurrency
- Handle multiple users editing same CSV
- Lock mechanisms for concurrent updates
- Merge conflict resolution

### 7. Advanced Rule Types
- Composite rules (multiple conditions)
- Fuzzy matching for supplier names
- Regular expression patterns
- Date-based rules

### 8. Rule Testing & Validation
- Test rules before applying
- Show impact analysis
- Validate rule logic
- Prevent contradictory rules

### 9. Bulk Rule Management
- Import/export rules
- Bulk activate/deactivate
- Rule versioning
- Rule templates

### 10. Analytics & Reporting
- Track feedback trends
- Measure rule effectiveness
- Identify problematic categories
- User feedback metrics

---

## Running the HITL Backend

### Installation

```bash
# Install dependencies
poetry install

# Or with pip
pip install duckdb fastapi uvicorn
```

### Start the Server

```bash
# Development mode with auto-reload
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Access API Documentation

Open browser to:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## File Structure

```
/api/
  main.py                          # FastAPI app
  /routers/
    datasets.py                    # GET /datasets
    transactions.py                # GET /transactions
    feedback.py                    # Feedback workflow endpoints
  /models/
    requests.py                    # Pydantic request models
    responses.py                   # Pydantic response models

/core/
  /database/
    models.py                      # SQLAlchemy models (3 tables)
    schema.py                      # Database initialization & migration

  /agents/
    /feedback_action/
      agent.py                     # FeedbackAction class
      signature.py                 # DSPy signature

  /hitl/
    csv_service.py                 # DuckDB CSV queries
    feedback_service.py            # Main workflow orchestration
    taxonomy_updates.py            # Actions 1 & 2
    supplier_rule.py               # Action 3
    transaction_rule.py            # Action 4
    yaml_service.py                # YAML read/write

/docs/
  hitl_implementation.md           # This file
```

---

## Summary

The HITL system enables efficient post-classification feedback with intelligent action planning. The LLM agent analyzes natural language feedback to determine the appropriate corrective action, reducing manual work and improving classification accuracy over time.

**Key Features:**
- Single LLM call per feedback submission
- 4 distinct action types
- Hybrid proposal formatting (code + LLM)
- DuckDB for efficient CSV queries
- SQLite for workflow state
- FastAPI for RESTful API
- Comprehensive bulk operations

**Implementation Status:**
- ✅ Database schema & migrations
- ✅ CSV service with DuckDB
- ✅ YAML service
- ✅ FeedbackAction agent
- ✅ Action executors
- ✅ Feedback service
- ✅ FastAPI routers
- ⏳ Frontend UI (not implemented)
