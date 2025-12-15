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

### 1. Supplier Rules Tables

**Supplier rules are stored in dedicated tables:**

#### `supplier_direct_mappings` Table
```sql
CREATE TABLE supplier_direct_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name VARCHAR(255) NOT NULL,
    classification_path VARCHAR(500) NOT NULL,  -- L1|L2|L3|L4|L5
    dataset_name VARCHAR(255),                  -- NULL = applies to all datasets
    priority INTEGER DEFAULT 10,
    created_at DATETIME,
    updated_at DATETIME,
    active BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(255),                     -- "hitl_feedback" or user name
    notes TEXT
);
```

**Purpose:** Store Category A supplier rules (100% confidence, single path). When a supplier in this table is encountered, skip LLM classification entirely and directly map all transactions to the specified classification path.

#### `supplier_taxonomy_constraints` Table
```sql
CREATE TABLE supplier_taxonomy_constraints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name VARCHAR(255) NOT NULL,
    allowed_taxonomy_paths JSON NOT NULL,        -- Array of allowed paths
    dataset_name VARCHAR(255),                  -- NULL = applies to all datasets
    priority INTEGER DEFAULT 10,
    created_at DATETIME,
    updated_at DATETIME,
    active BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(255),                     -- "hitl_feedback" or user name
    notes TEXT
);
```

**Purpose:** Store Category B supplier rules (multiple allowed paths). When a supplier in this table is encountered, instead of using RAG to retrieve taxonomy paths, use the stored list of allowed taxonomy paths for LLM classification.

**Rule Categories:**
- **Category A (DirectMapping)**: One-to-one mapping (supplier always maps to single classification, 100% confidence, skip LLM)
- **Category B (TaxonomyConstraint)**: One-to-many mapping (supplier can map to multiple classifications, constrains LLM to specific paths)

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

#### 0. GET `/feedback`

List all feedback items with optional filters and pagination.

**Query Parameters:**
- `status` (optional): Filter by status ("pending", "approved", "applied")
- `dataset_id` (optional): Filter by dataset ID
- `action_type` (optional): Filter by action type ("company_context", "taxonomy_description", "supplier_rule", "transaction_rule")
- `page` (optional, default: 1): Page number (1-indexed)
- `limit` (optional, default: 50, max: 200): Items per page

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "dataset_id": "innova",
      "row_index": 42,
      "original_classification": "facilities|utilities|electricity",
      "corrected_classification": "it & telecom|cloud services|iaas",
      "action_type": "supplier_rule",
      "status": "pending",
      "created_at": "2024-01-15T10:30:00"
    }
  ],
  "total": 25,
  "page": 1,
  "pages": 1,
  "limit": 50
}
```

**Example cURL:**
```bash
curl "http://localhost:8000/api/v1/feedback?status=pending&dataset_id=innova&page=1&limit=50"
```

---

#### 1. GET `/feedback/{feedback_id}`

Get detailed information about a specific feedback item.

**Path Parameters:**
- `feedback_id` (required): Feedback ID

**Response:**
```json
{
  "id": 1,
  "dataset_id": "innova",
  "foldername": "default",
  "row_index": 42,
  "original_classification": "facilities|utilities|electricity",
  "corrected_classification": "it & telecom|cloud services|iaas",
  "feedback_text": "This supplier always provides cloud infrastructure services",
  "action_type": "supplier_rule",
  "action_details": {
    "supplier_name": "AWS",
    "rule_category": "A",
    "classification_paths": ["it & telecom|cloud services|iaas"]
  },
  "action_reasoning": "User indicated supplier always provides this service",
  "status": "pending",
  "proposal_text": "Supplier Rule\nSupplier: AWS\n...",
  "user_edited_text": null,
  "created_at": "2024-01-15T10:30:00",
  "approved_at": null,
  "applied_at": null
}
```

**Example cURL:**
```bash
curl "http://localhost:8000/api/v1/feedback/1"
```

---

#### 2. DELETE `/feedback/{feedback_id}`

Delete/reject a feedback item. Only pending feedback can be deleted.

**Path Parameters:**
- `feedback_id` (required): Feedback ID

**Response:**
```json
{
  "message": "Feedback 1 deleted successfully"
}
```

**Example cURL:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/feedback/1"
```

---

#### 7. GET `/datasets`

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

#### 8. GET `/transactions`

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

Submit user feedback and get LLM-generated action proposal.

**Request Body:**
```json
{
  "dataset_id": "innova",
  "foldername": "default",
  "row_index": 42,
  "corrected_path": "it & telecom|cloud services|iaas",
  "feedback_text": "This supplier always provides cloud infrastructure services"
}
```

**Field Descriptions:**
- `dataset_id` (required): Dataset identifier (e.g., "innova", "fox")
- `foldername` (optional, default: "default"): Folder name for dataset organization
- `row_index` (required): Row index in CSV (0-based)
- `corrected_path` (required): Corrected classification path (L1|L2|L3|L4 format)
- `feedback_text` (required): Natural language explanation of why classification was wrong

**Response:**
```json
{
  "feedback_id": 1,
  "action_type": "supplier_rule",
  "proposal_text": "Supplier Rule\nSupplier: AWS\nRule Type: Category A (one-to-one mapping)\nClassification:\n  - it & telecom|cloud services|iaas\n\nThis rule will apply to all future transactions from this supplier.",
  "action_details": {
    "supplier_name": "AWS",
    "rule_category": "A",
    "classification_paths": ["it & telecom|cloud services|iaas"]
  }
}
```

**Example cURL:**
```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "default",
    "row_index": 42,
    "corrected_path": "it & telecom|cloud services|iaas",
    "feedback_text": "AWS always provides cloud infrastructure services"
  }'
```

---

#### 4. POST `/feedback/{feedback_id}/approve`

Approve feedback proposal with optional user edits.

**Path Parameters:**
- `feedback_id` (required): Feedback ID from submission

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

**Example cURL:**
```bash
curl -X POST "http://localhost:8000/api/v1/feedback/1/approve" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

#### 5. GET `/feedback/{feedback_id}/preview`

Preview rows that will be affected by this action.

**Path Parameters:**
- `feedback_id` (required): Feedback ID

**Response:**
```json
{
  "rows": [
    {
      "row_idx": 42,
      "supplier_name": "AWS",
      "L1": "facilities",
      "L2": "utilities",
      "amount": 5000.00
    },
    {
      "row_idx": 87,
      "supplier_name": "AWS",
      "L1": "it & telecom",
      "L2": "software",
      "amount": 12000.00
    }
  ],
  "count": 15,
  "row_indices": [42, 87, 133, 201, 245, 312, 378, 445, 512, 589, 656, 723, 790, 857, 924]
}
```

**Example cURL:**
```bash
curl "http://localhost:8000/api/v1/feedback/1/preview"
```

---

#### 6. POST `/feedback/{feedback_id}/apply`

Execute action and apply bulk corrections to CSV.

**Path Parameters:**
- `feedback_id` (required): Feedback ID (must be in "approved" status)

**Request Body:**
```json
{
  "row_indices": [42, 87, 133]
}
```

**Field Descriptions:**
- `row_indices` (required): List of row indices to update with corrected classification

**Response:**
```json
{
  "updated_count": 3
}
```

**What This Does:**
1. Executes the action (creates rule, updates taxonomy, etc.)
2. Updates specified rows in CSV with corrected classification
3. Sets feedback status to "applied"

**Example cURL:**
```bash
curl -X POST "http://localhost:8000/api/v1/feedback/1/apply" \
  -H "Content-Type: application/json" \
  -d '{
    "row_indices": [42, 87, 133]
  }'
```

**Note:** For supplier rules, the rule is created in the database and will affect future classifications even if you don't apply bulk corrections to existing rows.

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
- **Category A (DirectMapping)**: Single classification path (one-to-one, 100% confidence)
  - Example: `{"rule_category": "A", "classification_paths": ["it & telecom|cloud services|iaas"]}`
  - When this supplier is encountered, ALL transactions are directly mapped to this path without LLM classification
  - Stored in `supplier_direct_mappings` table
  
- **Category B (TaxonomyConstraint)**: Multiple classification paths (one-to-many)
  - Example: `{"rule_category": "B", "classification_paths": ["it & telecom|cloud services|iaas", "it & telecom|cloud services|paas"]}`
  - When this supplier is encountered, LLM classification is constrained to only these paths (replaces RAG)
  - Stored in `supplier_taxonomy_constraints` table

**Execution:**
- **Category A**: Creates/updates entry in `supplier_direct_mappings` table
- **Category B**: Creates/updates entry in `supplier_taxonomy_constraints` table
- Deactivates any existing rules for the same supplier+dataset (ensures only one active rule)
- Rules are global per dataset (not scoped to specific run)
- Rules are immediately available for future classifications

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

## Complete Workflow Examples

### Example 1: Supplier Rule - Category A (Direct Mapping)

**Scenario:** User finds that AWS transactions are always cloud infrastructure services.

#### Step 1: Submit Feedback

```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "default",
    "row_index": 42,
    "corrected_path": "it & telecom|cloud services|iaas",
    "feedback_text": "AWS always provides cloud infrastructure services. Every transaction from AWS should be classified as IaaS."
  }'
```

**Response:**
```json
{
  "feedback_id": 1,
  "action_type": "supplier_rule",
  "proposal_text": "Supplier Rule\nSupplier: AWS\nRule Type: Category A (one-to-one mapping)\nClassification:\n  - it & telecom|cloud services|iaas\n\nThis rule will apply to all future transactions from this supplier.",
  "action_details": {
    "supplier_name": "AWS",
    "rule_category": "A",
    "classification_paths": ["it & telecom|cloud services|iaas"]
  }
}
```

#### Step 2: Review and Approve

```bash
curl -X POST "http://localhost:8000/api/v1/feedback/1/approve" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:**
```json
{
  "status": "approved",
  "issues": []
}
```

#### Step 3: Preview Affected Rows

```bash
curl "http://localhost:8000/api/v1/feedback/1/preview"
```

**Response:**
```json
{
  "rows": [
    {
      "row_idx": 42,
      "supplier_name": "AWS",
      "L1": "facilities",
      "L2": "utilities",
      "amount": 5000.00
    },
    {
      "row_idx": 87,
      "supplier_name": "AWS",
      "L1": "it & telecom",
      "L2": "software",
      "amount": 12000.00
    },
    {
      "row_idx": 133,
      "supplier_name": "AWS",
      "L1": "it & telecom",
      "L2": "cloud services",
      "amount": 8000.00
    }
  ],
  "count": 3,
  "row_indices": [42, 87, 133]
}
```

#### Step 4: Apply Feedback

```bash
curl -X POST "http://localhost:8000/api/v1/feedback/1/apply" \
  -H "Content-Type: application/json" \
  -d '{
    "row_indices": [42, 87, 133]
  }'
```

**Response:**
```json
{
  "updated_count": 3
}
```

**What Happens:**
1. Creates entry in `supplier_direct_mappings` table:
   ```sql
   INSERT INTO supplier_direct_mappings 
   (supplier_name, classification_path, dataset_name, priority, created_by, notes, active)
   VALUES 
   ('aws', 'it & telecom|cloud services|iaas', 'innova', 10, 'hitl_feedback', 'Created via HITL feedback (ID: 1)', TRUE);
   ```
2. Updates 3 rows in the CSV with the corrected classification
3. Sets feedback status to "applied"
4. **Future Impact:** All future transactions from AWS will automatically be classified as "it & telecom|cloud services|iaas" without LLM classification

---

### Example 2: Supplier Rule - Category B (Taxonomy Constraint)

**Scenario:** User finds that Microsoft can provide either SaaS or IaaS services, but always within cloud services.

#### Step 1: Submit Feedback

```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "default",
    "row_index": 156,
    "corrected_path": "it & telecom|cloud services|saas",
    "feedback_text": "Microsoft provides cloud services, specifically either SaaS or IaaS. Their transactions should be constrained to these two categories only."
  }'
```

**Response:**
```json
{
  "feedback_id": 2,
  "action_type": "supplier_rule",
  "proposal_text": "Supplier Rule\nSupplier: Microsoft\nRule Type: Category B (multiple possible classifications)\nClassification:\n  - it & telecom|cloud services|saas\n  - it & telecom|cloud services|iaas\n\nThis rule will apply to all future transactions from this supplier.",
  "action_details": {
    "supplier_name": "Microsoft",
    "rule_category": "B",
    "classification_paths": [
      "it & telecom|cloud services|saas",
      "it & telecom|cloud services|iaas"
    ]
  }
}
```

#### Step 2: Approve and Apply

```bash
# Approve
curl -X POST "http://localhost:8000/api/v1/feedback/2/approve" \
  -H "Content-Type: application/json" \
  -d '{}'

# Apply
curl -X POST "http://localhost:8000/api/v1/feedback/2/apply" \
  -H "Content-Type: application/json" \
  -d '{"row_indices": [156, 201, 245]}'
```

**What Happens:**
1. Creates entry in `supplier_taxonomy_constraints` table:
   ```sql
   INSERT INTO supplier_taxonomy_constraints 
   (supplier_name, allowed_taxonomy_paths, dataset_name, priority, created_by, notes, active)
   VALUES 
   ('microsoft', '["it & telecom|cloud services|saas", "it & telecom|cloud services|iaas"]', 'innova', 10, 'hitl_feedback', 'Created via HITL feedback (ID: 2)', TRUE);
   ```
2. Updates rows in CSV
3. **Future Impact:** When Microsoft transactions are classified, the LLM will only consider these two paths (replaces RAG search)

---

### Example 3: Transaction Rule

**Scenario:** User finds that GL code 1234 always represents utilities expenses.

#### Step 1: Submit Feedback

```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "default",
    "row_index": 89,
    "corrected_path": "facilities|utilities|electricity",
    "feedback_text": "GL code 1234 is always used for electricity utilities. Any transaction with this GL code should be classified as facilities|utilities|electricity."
  }'
```

**Response:**
```json
{
  "feedback_id": 3,
  "action_type": "transaction_rule",
  "proposal_text": "Transaction Rule\nRule: if gl_code = 1234, always classify as facilities|utilities|electricity\n\nRule Name: GL 1234 -> Utilities",
  "action_details": {
    "condition_field": "gl_code",
    "condition_value": "1234",
    "classification_path": "facilities|utilities|electricity",
    "rule_name": "GL 1234 -> Utilities"
  }
}
```

#### Step 2: Approve and Apply

```bash
# Approve
curl -X POST "http://localhost:8000/api/v1/feedback/3/approve" \
  -H "Content-Type: application/json" \
  -d '{}'

# Preview affected rows
curl "http://localhost:8000/api/v1/feedback/3/preview"

# Apply
curl -X POST "http://localhost:8000/api/v1/feedback/3/apply" \
  -H "Content-Type: application/json" \
  -d '{"row_indices": [89, 142, 203, 267]}'
```

**What Happens:**
1. Creates entry in `transaction_rules` table
2. Updates all rows with `gl_code = "1234"` in CSV
3. **Future Impact:** All future transactions with GL code 1234 will be automatically classified as "facilities|utilities|electricity"

---

### Example 4: Company Context Update

**Scenario:** Company pivoted from broadcast television to streaming services.

#### Step 1: Submit Feedback

```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "default",
    "row_index": 12,
    "corrected_path": "media & entertainment|streaming|subscription",
    "feedback_text": "Our company has pivoted from broadcast television to streaming and digital media. The business focus has changed."
  }'
```

**Response:**
```json
{
  "feedback_id": 4,
  "action_type": "company_context",
  "proposal_text": "Company Context Update\nField: business_focus\n\nCurrent:\nBroadcast Television\n\nProposed:\nStreaming and Digital Media\n\nYou can edit the proposed text above before approving.",
  "action_details": {
    "field_name": "business_focus",
    "current_value": "Broadcast Television",
    "proposed_value": "Streaming and Digital Media"
  }
}
```

#### Step 2: Approve

```bash
curl -X POST "http://localhost:8000/api/v1/feedback/4/approve" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**What Happens:**
1. Updates `taxonomies/innova.yaml` file:
   ```yaml
   company_context:
     business_focus: "Streaming and Digital Media"
   ```
2. No database changes
3. **Future Impact:** Future classifications will use the updated company context

---

### Example 5: Taxonomy Description Update

**Scenario:** User wants to clarify what the IaaS category includes.

#### Step 1: Submit Feedback

```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "default",
    "row_index": 78,
    "corrected_path": "it & telecom|cloud services|iaas",
    "feedback_text": "The IaaS category should include cloud infrastructure services like compute, storage, and networking. It should not include SaaS applications."
  }'
```

**Response:**
```json
{
  "feedback_id": 5,
  "action_type": "taxonomy_description",
  "proposal_text": "Taxonomy Description Update\nPath: it & telecom|cloud services|iaas\n\nCurrent Description:\nInfrastructure as a service providing virtualized computing resources.\n\nProposed Description:\nCloud infrastructure including compute, storage, and networking services. Does not include SaaS applications or software subscriptions.",
  "action_details": {
    "taxonomy_path": "it & telecom|cloud services|iaas",
    "current_description": "Infrastructure as a service providing virtualized computing resources.",
    "proposed_description": "Cloud infrastructure including compute, storage, and networking services. Does not include SaaS applications or software subscriptions."
  }
}
```

#### Step 2: Approve

```bash
curl -X POST "http://localhost:8000/api/v1/feedback/5/approve" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**What Happens:**
1. Updates `taxonomies/innova.yaml` file:
   ```yaml
   taxonomy_descriptions:
     "it & telecom|cloud services|iaas": "Cloud infrastructure including compute, storage, and networking services. Does not include SaaS applications or software subscriptions."
   ```
2. No database changes
3. **Future Impact:** Future classifications will use the updated taxonomy description for better accuracy

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
