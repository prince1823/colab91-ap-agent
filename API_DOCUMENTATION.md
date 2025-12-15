# Spend Classification Backend API Documentation

## Table of Contents

1. [Overview](#overview)
2. [System Architecture & Flow](#system-architecture--flow)
3. [Getting Started](#getting-started)
4. [API Reference](#api-reference)
   - [Dataset Management](#1-dataset-management)
   - [Classification Workflow](#2-classification-workflow)
   - [Transaction Management](#3-transaction-management)
   - [Feedback & Human-in-the-Loop](#4-feedback--human-in-the-loop)
   - [Supplier Rules Management](#5-supplier-rules-management)
5. [Common Patterns](#common-patterns)
6. [Error Handling](#error-handling)

---

## Overview

The Spend Classification Backend API is a comprehensive system for classifying financial transactions using AI-powered agents. The system processes raw transaction data through a multi-stage workflow: **Canonicalization → Verification → Classification**, with built-in human-in-the-loop feedback mechanisms for continuous improvement.

### Key Features

- **Automated Column Mapping**: AI-powered canonicalization maps client-specific column names to a standard schema
- **Human Verification**: Review and modify column mappings before classification
- **Intelligent Classification**: Multi-agent system with supplier research and expert classification
- **Feedback Loop**: Submit corrections that automatically create rules for future classifications
- **Rule Management**: Direct mappings and taxonomy constraints for consistent classifications

### Base URL

```
http://localhost:8000/api/v1
```

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## System Architecture & Flow

### Complete Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    SPEND CLASSIFICATION WORKFLOW                  │
└─────────────────────────────────────────────────────────────────┘

1. DATASET SETUP
   ├─ Create/Upload Dataset (input.csv + taxonomy.yaml)
   ├─ List Available Datasets
   └─ Get Dataset Details

2. CANONICALIZATION STAGE
   ├─ Start Canonicalization (AI maps client columns → canonical schema)
   ├─ Review Canonicalization Results
   └─ Verify & Modify (Human review: add/remove columns, fix mappings)

3. CLASSIFICATION STAGE
   ├─ Start Classification (AI classifies transactions)
   └─ Monitor Status

4. TRANSACTION MANAGEMENT
   ├─ Query Classified Transactions (with filters & pagination)
   ├─ Get Single Transaction
   └─ Update Transaction Classification

5. FEEDBACK & IMPROVEMENT
   ├─ Submit Feedback (AI categorizes action type)
   ├─ Approve Feedback
   ├─ Preview Affected Rows
   └─ Apply Feedback (creates rules, updates CSV)

6. RULE MANAGEMENT
   ├─ Direct Mappings (100% confidence, skip LLM)
   └─ Taxonomy Constraints (limit LLM to specific paths)
```

### Workflow States

The system tracks dataset processing through the following states:

| State | Description | Next Actions |
|-------|-------------|--------------|
| `pending` | Dataset created, not yet processed | Start canonicalization |
| `canonicalizing` | Currently running canonicalization | Wait for completion |
| `canonicalized` | Canonicalization complete | Review and verify |
| `awaiting_verification` | Ready for human review | Verify canonicalization |
| `verified` | Verified and ready for classification | Start classification |
| `classifying` | Currently running classification | Wait for completion |
| `completed` | All stages complete | Query transactions, submit feedback |
| `failed` | Error occurred | Check error message, retry |

### File Structure

Each dataset follows this structure:

```
datasets/
  {dataset_id}/
    ├── input.csv              # Raw transaction data
    ├── taxonomy.yaml          # Taxonomy structure for classification
    ├── canonicalized.csv      # Generated after canonicalization
    └── classified.csv         # Generated after classification
```

**Note**: For datasets directly under `datasets/`, use `foldername=""` (empty string) in API calls.

---

## Getting Started

### 1. Create a Dataset

```bash
# Create dataset with input CSV and taxonomy
curl -X POST "http://localhost:8000/api/v1/datasets" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "",
    "input_csv_path": "datasets/innova/input.csv",
    "taxonomy_yaml_path": "datasets/innova/taxonomy.yaml"
  }'
```

### 2. Run Classification Workflow

```bash
# Step 1: Canonicalize
curl -X POST "http://localhost:8000/api/v1/datasets/innova/canonicalize?foldername="

# Step 2: Verify (auto-approve for testing)
curl -X POST "http://localhost:8000/api/v1/datasets/innova/verify?foldername=" \
  -H "Content-Type: application/json" \
  -d '{"auto_approve": true}'

# Step 3: Start Classification (async - returns immediately)
curl -X POST "http://localhost:8000/api/v1/datasets/innova/classify?foldername=&max_workers=4"

# Step 4: Poll Status (check progress)
curl "http://localhost:8000/api/v1/datasets/innova/status?foldername="

# Keep polling until status is "completed"
while [ "$(curl -s 'http://localhost:8000/api/v1/datasets/innova/status?foldername=' | jq -r '.status')" != "completed" ]; do
  echo "Still processing..."
  sleep 3
done
echo "✅ Classification completed!"
```

### 3. Query Results

```bash
# Get classified transactions
curl "http://localhost:8000/api/v1/transactions?dataset_id=innova&foldername=&page=1&limit=50"
```

---

## API Reference

---

## 1. Dataset Management

### List Datasets

**GET** `/datasets`

List all available datasets with optional filtering.

**Query Parameters:**
- `foldername` (optional, string): Filter by folder name. Use `""` (empty string) for datasets directly under `datasets/`

**Response:** `200 OK`
```json
[
  {
    "dataset_id": "innova",
    "foldername": "",
    "row_count": 256
  }
]
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/datasets?foldername="
```

---

### Get Dataset Details

**GET** `/datasets/{dataset_id}`

Get detailed information about a specific dataset.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier (alphanumeric, underscore, hyphen, dot only)

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name. Use `""` for direct datasets

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "row_count": 256,
  "csv_path_or_uri": "datasets/innova/classified.csv"
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/datasets/innova?foldername="
```

---

### Create Dataset (File Upload)

**POST** `/datasets/upload`

Create a new dataset by uploading CSV and YAML files directly.

**Content-Type:** `multipart/form-data`

**Form Fields:**
- `dataset_id` (required, string): Unique dataset identifier
- `foldername` (optional, string, default: "default"): Folder name. Use `""` for direct dataset access
- `input_csv` (required, file): CSV file with transaction data
- `taxonomy_yaml` (required, file): YAML file with taxonomy structure

**Response:** `201 Created`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "row_count": 256
}
```

**Example using curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/upload" \
  -F "dataset_id=innova" \
  -F "foldername=" \
  -F "input_csv=@datasets/innova/input.csv" \
  -F "taxonomy_yaml=@datasets/innova/taxonomy.yaml"
```

**Example using Python requests:**
```python
import requests

url = "http://localhost:8000/api/v1/datasets/upload"
files = {
    'input_csv': ('input.csv', open('datasets/innova/input.csv', 'rb'), 'text/csv'),
    'taxonomy_yaml': ('taxonomy.yaml', open('datasets/innova/taxonomy.yaml', 'rb'), 'application/x-yaml')
}
data = {
    'dataset_id': 'innova',
    'foldername': ''
}
response = requests.post(url, files=files, data=data)
```

**Notes:**
- CSV file must have `.csv` extension
- YAML file must have `.yaml` or `.yml` extension
- Files are saved as `input.csv` and `taxonomy.yaml` in the dataset directory

---

### Create Dataset (JSON)

**POST** `/datasets`

Create a new dataset with transactions and taxonomy provided as JSON (for programmatic access).

**Request Body:**
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "transactions": [
    {
      "supplier_name": "Verizon",
      "amount": 1000.00,
      "transaction_date": "2024-01-15"
    }
  ],
  "taxonomy": {
    "taxonomy": [...],
    "taxonomy_descriptions": {...},
    "company_context": {...}
  },
  "csv_filename": "input.csv"
}
```

**Request Fields:**
- `dataset_id` (required, string): Unique dataset identifier
- `foldername` (optional, string, default: "default"): Folder name. Use `""` for direct dataset access
- `transactions` (required, array): Array of transaction objects
- `taxonomy` (required, object): Taxonomy structure as dictionary
- `csv_filename` (optional, string, default: "transactions.csv"): CSV filename

**Response:** `201 Created`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "row_count": 1
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "",
    "transactions": [{"supplier_name": "Verizon", "amount": 1000.00}],
    "taxonomy": {"taxonomy": []}
  }'
```

---

### Update Dataset CSV

**PUT** `/datasets/{dataset_id}/csv`

Update the input CSV file for an existing dataset.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Request Body:**
```json
{
  "input_csv_path": "datasets/innova/input_updated.csv"
}
```

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "message": "Dataset CSV updated successfully"
}
```

---

### Update Dataset Taxonomy

**PUT** `/datasets/{dataset_id}/taxonomy`

Update the taxonomy YAML file for an existing dataset.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Request Body:**
```json
{
  "taxonomy_yaml_path": "datasets/innova/taxonomy_updated.yaml"
}
```

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "message": "Dataset taxonomy updated successfully"
}
```

---

### Get Dataset Taxonomy

**GET** `/datasets/{dataset_id}/taxonomy`

Get the taxonomy structure for a dataset.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "taxonomy": {
    "taxonomy": [...],
    "taxonomy_descriptions": {...},
    "company_context": {...}
  }
}
```

---

### Delete Dataset

**DELETE** `/datasets/{dataset_id}`

Delete a dataset and all associated files.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `204 No Content`

**Example:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/datasets/innova?foldername="
```

---

## 2. Classification Workflow

The classification workflow consists of three sequential stages. Each stage must be completed before moving to the next.

### 2.1 Canonicalization Stage

#### Start Canonicalization

**POST** `/datasets/{dataset_id}/canonicalize`

Start the canonicalization process. This AI-powered stage maps client-specific column names to the canonical schema.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "status": "canonicalized",
  "mapping_result": {
    "mappings": {
      "Vendor": "supplier_name",
      "Amount": "amount",
      "Date": "transaction_date"
    },
    "unmapped_client_columns": ["internal_id"],
    "validation_passed": true
  }
}
```

**Response Fields:**
- `mappings`: Dictionary mapping client column names to canonical names
- `unmapped_client_columns`: Client columns that couldn't be mapped
- `validation_passed`: Whether required canonical columns (supplier_name, amount) are present

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/canonicalize?foldername="
```

**What Happens:**
- Reads `input.csv`
- Uses AI agent to map columns to canonical schema
- Generates `canonicalized.csv`
- Updates workflow status to `canonicalized`

---

#### Get Canonicalization for Review

**GET** `/datasets/{dataset_id}/canonicalization`

Get canonicalization results for human review before verification.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "canonicalization_result": {
    "mappings": {
      "Vendor": "supplier_name",
      "Amount": "amount"
    },
    "unmapped_client_columns": ["internal_id"],
    "validation_passed": true,
    "validation_errors": []
  },
  "canonicalized_csv_path": "datasets/innova/canonicalized.csv",
  "current_canonical_columns": [
    "supplier_name",
    "amount",
    "transaction_date",
    "line_description"
  ]
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/datasets/innova/canonicalization?foldername="
```

---

### 2.2 Verification Stage

#### Verify Canonicalization

**POST** `/datasets/{dataset_id}/verify`

Approve canonicalization with optional modifications. This is the human-in-the-loop step where you can:
- **Update column mappings** (correct AI mistakes)
- **Add missing columns** important for classification (with default values)
- **Remove unwanted columns** that shouldn't be processed

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Request Body:**
```json
{
  "approved_mappings": {
    "Vendor": "supplier_name",
    "Amt": "amount"
  },
  "columns_to_add": [
    {
      "canonical_name": "invoice_date",
      "default_value": "",
      "description": "Invoice date for better classification"
    }
  ],
  "columns_to_remove": [
    "internal_reference",
    "temp_column"
  ],
  "notes": "Added invoice_date column, removed internal references",
  "auto_approve": false
}
```

**Request Fields:**
- `approved_mappings` (optional, object): Updated column mappings `{client_col: canonical_col}`
- `columns_to_add` (optional, array): Columns to add. Each object:
  - `canonical_name` (required, string): Canonical column name
  - `default_value` (optional, any): Default value for all rows (default: "")
  - `description` (optional, string): Column description
- `columns_to_remove` (optional, array): List of canonical column names to remove
- `notes` (optional, string): Verification notes
- `auto_approve` (optional, bool, default: false): Auto-approve without modifications (for testing/benchmarks)

**Response:** `200 OK`
```json
{
  "status": "verified",
  "message": "Canonicalization approved"
}
```

**Example - Add Missing Column:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/verify?foldername=" \
  -H "Content-Type: application/json" \
  -d '{
    "columns_to_add": [
      {
        "canonical_name": "cost_center",
        "default_value": "0000",
        "description": "Cost center for spend categorization"
      }
    ],
    "notes": "Added cost_center column"
  }'
```

**Example - Auto-approve (for testing):**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/verify?foldername=" \
  -H "Content-Type: application/json" \
  -d '{"auto_approve": true}'
```

**What Happens:**
- Applies any modifications (mapping updates, column additions/removals)
- Updates `canonicalized.csv` with changes
- Transitions workflow status: `canonicalized` → `awaiting_verification` → `verified`
- Dataset is now ready for classification

---

### 2.3 Classification Stage

#### Start Classification

**POST** `/datasets/{dataset_id}/classify`

Start the classification process on a verified canonicalized dataset. This endpoint starts classification **asynchronously** and returns immediately. Use the status endpoint to poll for progress.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name
- `max_workers` (optional, int, default: 4, min: 1, max: 16): Number of parallel workers

**Response:** `200 OK`
```json
{
  "status": "started",
  "dataset_id": "innova",
  "foldername": "",
  "message": "Classification started. Poll GET /datasets/{dataset_id}/status endpoint for progress."
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/classify?foldername=&max_workers=4"
```

**What Happens:**
- Classification runs in a background thread
- Returns immediately with status "started"
- Updates workflow status to `classifying`
- Progress is tracked in the database (invoices processed, percentage)
- Client should poll the status endpoint to check progress

**Polling for Progress:**
```bash
# Poll status endpoint every few seconds
while true; do
  STATUS=$(curl -s "http://localhost:8000/api/v1/datasets/innova/status?foldername=" | jq -r '.status')
  echo "Status: $STATUS"
  
  if [ "$STATUS" = "completed" ]; then
    echo "✅ Classification completed!"
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "❌ Classification failed!"
    break
  fi
  
  sleep 3
done
```

**Classification Process:**
1. **Supplier Research**: If supplier is unknown, research agent gathers information
2. **Context Prioritization**: Determines which transaction fields are most relevant
3. **Expert Classification**: Uses taxonomy RAG and LLM to classify into L1|L2|L3|L4 path
4. **Rule Application**: Applies any active supplier rules (direct mappings or constraints)

**Why Async?**
- Large datasets can take minutes or hours to classify
- HTTP requests typically timeout after 30-60 seconds
- Async pattern allows:
  - Immediate response (no timeout issues)
  - Progress tracking (see how many invoices are processed)
  - Better user experience (can check status without blocking)

---

#### Get Workflow Status

**GET** `/datasets/{dataset_id}/status`

Get the current workflow status for a dataset. This endpoint includes progress tracking for async classification.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "status": "classifying",
  "canonicalized_csv_path": "datasets/innova/canonicalized.csv",
  "classification_result_path": null,
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "error_message": null,
  "created_at": "2024-01-15T10:00:00",
  "updated_at": "2024-01-15T10:05:00",
  "progress_invoices_total": 50,
  "progress_invoices_processed": 25,
  "progress_percentage": 50
}
```

**Status Values:**
- `pending` - Not started
- `canonicalizing` - Currently running canonicalization
- `canonicalized` - Canonicalization complete, awaiting verification
- `awaiting_verification` - Ready for human review
- `verified` - Verified and ready for classification
- `classifying` - Currently running classification (async)
- `completed` - All stages complete
- `failed` - Error occurred

**Progress Fields (available when `status` is `classifying`):**
- `progress_invoices_total` (int): Total number of invoices to process
- `progress_invoices_processed` (int): Number of invoices completed
- `progress_percentage` (int): Percentage complete (0-100)

**Example:**
```bash
curl "http://localhost:8000/api/v1/datasets/innova/status?foldername="
```

**Polling Example (Python):**
```python
import requests
import time

def poll_classification_status(dataset_id, foldername="", poll_interval=3):
    """Poll classification status until completion."""
    url = f"http://localhost:8000/api/v1/datasets/{dataset_id}/status"
    params = {"foldername": foldername}
    
    while True:
        response = requests.get(url, params=params)
        data = response.json()
        
        status = data["status"]
        print(f"Status: {status}")
        
        if status == "classifying":
            progress = data.get("progress_percentage", 0)
            processed = data.get("progress_invoices_processed", 0)
            total = data.get("progress_invoices_total", "?")
            print(f"Progress: {processed}/{total} invoices ({progress}%)")
        elif status == "completed":
            print("✅ Classification completed!")
            return data
        elif status == "failed":
            print(f"❌ Classification failed: {data.get('error_message')}")
            return data
        
        time.sleep(poll_interval)

# Usage
poll_classification_status("innova", foldername="")
```

---

## 3. Transaction Management

### Query Transactions

**GET** `/transactions`

Query classified transactions from a dataset with filtering and pagination.

**Query Parameters:**
- `dataset_id` (required, string): Dataset identifier
- `foldername` (optional, string, default: "default"): Folder name
- `l1` (optional, string): Filter by L1 category (URL encode spaces: `%20`)
- `l2` (optional, string): Filter by L2 category
- `l3` (optional, string): Filter by L3 category
- `l4` (optional, string): Filter by L4 category
- `confidence` (optional, string): Filter by confidence level
- `supplier_name` (optional, string): Filter by supplier name
- `page` (optional, int, default: 1, min: 1): Page number (1-indexed)
- `limit` (optional, int, default: 50, min: 1, max: 200): Number of rows per page

**Response:** `200 OK`
```json
{
  "rows": [
    {
      "L1": "non clinical",
      "L2": "it & telecom",
      "L3": "telecom",
      "L4": "wireless services",
      "supplier_name": "verizon communication",
      "amount": 1000.00,
      ...
    }
  ],
  "total": 256,
  "page": 1,
  "pages": 6,
  "limit": 50
}
```

**Example:**
```bash
# Filter by L1 category (note: URL encode spaces)
curl "http://localhost:8000/api/v1/transactions?dataset_id=innova&foldername=&l1=non%20clinical&page=1&limit=50"
```

---

### Get Single Transaction

**GET** `/transactions/{row_index}`

Get a single transaction by row index.

**Path Parameters:**
- `row_index` (required, int): Row index (0-based)

**Query Parameters:**
- `dataset_id` (required, string): Dataset identifier
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "row_index": 42,
  "data": {
    "L1": "non clinical",
    "L2": "it & telecom",
    "L3": "telecom",
    "L4": "wireless services",
    "supplier_name": "verizon communication",
    "amount": 1000.00,
    ...
  }
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/transactions/2?dataset_id=innova&foldername="
```

---

### Update Transaction Classification

**PUT** `/transactions/{row_index}`

Manually update a transaction's classification path.

**Path Parameters:**
- `row_index` (required, int): Row index (0-based)

**Query Parameters:**
- `dataset_id` (required, string): Dataset identifier
- `foldername` (optional, string, default: "default"): Folder name

**Request Body:**
```json
{
  "classification_path": "non clinical|professional services|consulting",
  "override_rule_applied": "manual_correction_123"
}
```

**Request Fields:**
- `classification_path` (required, string): Full classification path in format `L1|L2|L3|L4`
- `override_rule_applied` (optional, string): Identifier for the override rule

**Response:** `200 OK`
```json
{
  "row_index": 42,
  "data": {
    "L1": "non clinical",
    "L2": "professional services",
    "L3": "consulting",
    "L4": "",
    "override_rule_applied": "manual_correction_123",
    ...
  }
}
```

**Example:**
```bash
curl -X PUT "http://localhost:8000/api/v1/transactions/2?dataset_id=innova&foldername=" \
  -H "Content-Type: application/json" \
  -d '{"classification_path": "non clinical|professional services|consulting"}'
```

---

## 4. Feedback & Human-in-the-Loop

The feedback system allows users to submit corrections, which are automatically analyzed by an AI agent to determine the appropriate action type and create rules for future classifications.

### Feedback Workflow

```
Submit Feedback → AI Categorizes Action → Approve → Preview → Apply
     ↓                    ↓                  ↓        ↓        ↓
  pending            action_type         approved  preview  applied
                                           ↓                  ↓
                                    Creates Rules    Updates CSV
```

### List Feedback

**GET** `/feedback`

List all feedback items with optional filters and pagination.

**Query Parameters:**
- `status` (optional, string): Filter by status (`pending`, `approved`, `applied`)
- `dataset_id` (optional, string): Filter by dataset ID
- `action_type` (optional, string): Filter by action type (`supplier_rule`, `transaction_rule`, `company_context`, `taxonomy_description`)
- `page` (optional, int, default: 1, min: 1): Page number
- `limit` (optional, int, default: 50, min: 1, max: 200): Items per page

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": 1,
      "dataset_id": "innova",
      "row_index": 2,
      "original_classification": "non-sourceable|non-sourceable|business related|business related other",
      "corrected_classification": "non clinical|professional services|consulting",
      "action_type": "supplier_rule",
      "status": "applied",
      "created_at": "2024-01-15T10:30:00"
    }
  ],
  "total": 25,
  "page": 1,
  "pages": 1,
  "limit": 50
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/feedback?status=pending&dataset_id=innova"
```

---

### Get Feedback Details

**GET** `/feedback/{feedback_id}`

Get detailed information about a specific feedback item.

**Path Parameters:**
- `feedback_id` (required, int): Feedback ID

**Response:** `200 OK`
```json
{
  "id": 1,
  "dataset_id": "innova",
  "foldername": "",
  "row_index": 2,
  "original_classification": "non-sourceable|non-sourceable|business related|business related other",
  "corrected_classification": "non clinical|professional services|consulting",
  "feedback_text": "eklectic entertainment should be professional services",
  "action_type": "supplier_rule",
  "action_details": {
    "supplier_name": "eklectic entertainment llc",
    "rule_category": "A",
    "classification_paths": ["non clinical|professional services|consulting"]
  },
  "action_reasoning": "The action type is a supplier rule because the user specified that 'eklectic entertainment' should be classified as 'professional services,' indicating a consistent classification for this supplier.",
  "status": "pending",
  "proposal_text": "Supplier Rule\nSupplier: eklectic entertainment llc\nRule Type: Category A (one-to-one mapping)\nClassification:\n  - non clinical|professional services|consulting\n\nThis rule will apply to all future transactions from this supplier.",
  "user_edited_text": null,
  "created_at": "2024-01-15T10:30:00",
  "approved_at": null,
  "applied_at": null
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/feedback/1"
```

---

### Submit Feedback

**POST** `/feedback`

Submit user feedback and get AI-generated action proposal. The AI agent analyzes the feedback and determines the appropriate action type.

**Request Body:**
```json
{
  "dataset_id": "innova",
  "foldername": "",
  "row_index": 2,
  "corrected_path": "non clinical|professional services|consulting",
  "feedback_text": "eklectic entertainment should be professional services"
}
```

**Request Fields:**
- `dataset_id` (required, string): Dataset identifier
- `foldername` (optional, string, default: ""): Folder name
- `row_index` (required, int): Row index of the transaction to correct
- `corrected_path` (required, string): Correct classification path in format `L1|L2|L3|L4`
- `feedback_text` (optional, string): Natural language explanation of the correction

**Response:** `200 OK`
```json
{
  "feedback_id": 1,
  "action_type": "supplier_rule",
  "proposal_text": "Supplier Rule\nSupplier: eklectic entertainment llc\nRule Type: Category A (one-to-one mapping)\nClassification:\n  - non clinical|professional services|consulting\n\nThis rule will apply to all future transactions from this supplier.",
  "action_details": {
    "supplier_name": "eklectic entertainment llc",
    "rule_category": "A",
    "classification_paths": ["non clinical|professional services|consulting"]
  }
}
```

**Action Types:**
- `supplier_rule`: Creates supplier classification rule
  - **Category A**: Direct mapping (100% confidence, single path, stored in `supplier_direct_mappings`)
  - **Category B**: Taxonomy constraint (multiple allowed paths, stored in `supplier_taxonomy_constraints`)
- `transaction_rule`: Creates transaction attribute-based rule (e.g., GL code rules)
- `company_context`: Updates company context in taxonomy YAML
- `taxonomy_description`: Updates taxonomy category descriptions in YAML

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "",
    "row_index": 2,
    "corrected_path": "non clinical|professional services|consulting",
    "feedback_text": "eklectic entertainment should be professional services"
  }'
```

**What Happens:**
1. AI agent analyzes the feedback and transaction data
2. Determines action type based on feedback context
3. Generates structured `action_details` and human-readable `proposal_text`
4. Creates feedback record with status `pending`

---

### Approve Feedback

**POST** `/feedback/{feedback_id}/approve`

Approve feedback with optional user edits.

**Path Parameters:**
- `feedback_id` (required, int): Feedback ID

**Request Body:**
```json
{
  "edited_text": "Optional edited proposal text"
}
```

**Request Fields:**
- `edited_text` (optional, string): User-edited proposal text

**Response:** `200 OK`
```json
{
  "status": "approved",
  "issues": []
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/feedback/1/approve" \
  -H "Content-Type: application/json" \
  -d '{"edited_text": "Updated proposal text"}'
```

**What Happens:**
- Updates feedback status from `pending` to `approved`
- Stores optional user-edited text
- Feedback is now ready to be applied

---

### Preview Affected Rows

**GET** `/feedback/{feedback_id}/preview`

Preview rows that will be affected by this action.

**Path Parameters:**
- `feedback_id` (required, int): Feedback ID

**Response:** `200 OK`
```json
{
  "rows": [
    {
      "row_idx": 2,
      "supplier_name": "eklectic entertainment llc",
      "L1": "non-sourceable",
      "L2": "non-sourceable",
      ...
    }
  ],
  "count": 1,
  "row_indices": [2]
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/feedback/1/preview"
```

**What Happens:**
- For `supplier_rule`: Finds all rows with the same supplier name
- For `transaction_rule`: Finds rows matching the rule criteria
- Returns preview of affected rows before applying changes

---

### Apply Feedback

**POST** `/feedback/{feedback_id}/apply`

Execute the approved action and apply bulk corrections to CSV.

**Path Parameters:**
- `feedback_id` (required, int): Feedback ID

**Request Body:**
```json
{
  "row_indices": [2]
}
```

**Request Fields:**
- `row_indices` (required, array of int): List of row indices to update with corrected classification

**Response:** `200 OK`
```json
{
  "updated_count": 1
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/feedback/1/apply" \
  -H "Content-Type: application/json" \
  -d '{"row_indices": [2]}'
```

**What Happens:**
- For **supplier_rule** actions:
  - Category A: Creates/updates entry in `supplier_direct_mappings` table
  - Category B: Creates/updates entry in `supplier_taxonomy_constraints` table
  - Rule is immediately active and will be used by classification pipeline for future transactions
- For **transaction_rule** actions: Creates entry in `transaction_rules` table
- For **company_context** and **taxonomy_description** actions: Updates YAML files
- Updates specified rows in CSV with corrected classification
- Sets feedback status to `applied`

**Note:** For supplier rules, the rule is created in the database and will affect future classifications even if you don't apply bulk corrections to existing rows.

---

### Delete Feedback

**DELETE** `/feedback/{feedback_id}`

Delete/reject a feedback item. Only pending feedback can be deleted.

**Path Parameters:**
- `feedback_id` (required, int): Feedback ID

**Response:** `200 OK`
```json
{
  "message": "Feedback 1 deleted successfully"
}
```

**Example:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/feedback/1"
```

---

## 5. Supplier Rules Management

Supplier rules allow you to enforce consistent classifications for specific suppliers. There are two types of rules:

1. **Direct Mappings**: 100% confidence rules that skip LLM classification entirely
2. **Taxonomy Constraints**: Limit LLM classification to specific taxonomy paths

### 5.1 Direct Mappings

Direct mappings are used when you're 100% confident that a supplier should always be classified to a specific path. These rules bypass LLM classification entirely.

#### Create Direct Mapping

**POST** `/supplier-rules/direct-mappings`

Create a direct mapping rule for a supplier.

**Request Body:**
```json
{
  "supplier_name": "AWS",
  "classification_path": "non clinical|it & telecom|cloud services|iaas",
  "dataset_name": "innova",
  "priority": 10,
  "notes": "100% confident this supplier always maps here",
  "created_by": "user@example.com"
}
```

**Request Fields:**
- `supplier_name` (required, string): Supplier name (case-insensitive matching)
- `classification_path` (required, string): Full classification path `L1|L2|L3|L4`
- `dataset_name` (optional, string): Dataset-specific rule (null for global rule)
- `priority` (optional, int, default: 10): Rule priority (higher = checked first)
- `notes` (optional, string): Notes about the rule
- `created_by` (optional, string): Creator identifier

**Response:** `200 OK`
```json
{
  "id": 1,
  "supplier_name": "AWS",
  "classification_path": "non clinical|it & telecom|cloud services|iaas",
  "dataset_name": "innova",
  "priority": 10,
  "active": true,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00",
  "created_by": "user@example.com",
  "notes": "100% confident this supplier always maps here"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/supplier-rules/direct-mappings" \
  -H "Content-Type: application/json" \
  -d '{
    "supplier_name": "AWS",
    "classification_path": "non clinical|it & telecom|cloud services|iaas",
    "dataset_name": "innova",
    "priority": 10
  }'
```

**How It Works:**
- When classification encounters this supplier, it immediately returns the stored path
- No LLM call is made
- Fastest classification method

---

#### List Direct Mappings

**GET** `/supplier-rules/direct-mappings`

List direct mapping rules with optional filters.

**Query Parameters:**
- `supplier_name` (optional, string): Filter by supplier name
- `dataset_name` (optional, string): Filter by dataset name
- `active_only` (optional, bool, default: true): Only return active mappings

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "supplier_name": "AWS",
    "classification_path": "non clinical|it & telecom|cloud services|iaas",
    "dataset_name": "innova",
    "priority": 10,
    "active": true,
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00",
    "created_by": "user@example.com",
    "notes": "100% confident this supplier always maps here"
  }
]
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/supplier-rules/direct-mappings?supplier_name=AWS"
```

---

#### Get Direct Mapping

**GET** `/supplier-rules/direct-mappings/{mapping_id}`

Get a specific direct mapping rule.

**Path Parameters:**
- `mapping_id` (required, int): Mapping ID

**Response:** `200 OK`
```json
{
  "id": 1,
  "supplier_name": "AWS",
  "classification_path": "non clinical|it & telecom|cloud services|iaas",
  "dataset_name": "innova",
  "priority": 10,
  "active": true,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00",
  "created_by": "user@example.com",
  "notes": "100% confident this supplier always maps here"
}
```

---

#### Update Direct Mapping

**PUT** `/supplier-rules/direct-mappings/{mapping_id}`

Update a direct mapping rule.

**Path Parameters:**
- `mapping_id` (required, int): Mapping ID

**Request Body:**
```json
{
  "classification_path": "non clinical|it & telecom|cloud services|paas",
  "priority": 15,
  "active": true,
  "notes": "Updated to PaaS category"
}
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "supplier_name": "AWS",
  "classification_path": "non clinical|it & telecom|cloud services|paas",
  "dataset_name": "innova",
  "priority": 15,
  "active": true,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T11:00:00",
  "created_by": "user@example.com",
  "notes": "Updated to PaaS category"
}
```

---

#### Delete Direct Mapping

**DELETE** `/supplier-rules/direct-mappings/{mapping_id}`

Delete a direct mapping rule.

**Path Parameters:**
- `mapping_id` (required, int): Mapping ID

**Query Parameters:**
- `hard_delete` (optional, bool, default: false): Hard delete (vs soft delete by setting `active=False`)

**Response:** `200 OK`
```json
{
  "message": "Direct mapping deleted successfully"
}
```

**Example:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/supplier-rules/direct-mappings/1"
```

---

### 5.2 Taxonomy Constraints

Taxonomy constraints limit the LLM classification to specific taxonomy paths. Instead of using RAG to retrieve taxonomy paths, the stored list of allowed paths is used.

#### Create Taxonomy Constraint

**POST** `/supplier-rules/taxonomy-constraints`

Create a taxonomy constraint for a supplier.

**Request Body:**
```json
{
  "supplier_name": "Microsoft",
  "allowed_taxonomy_paths": [
    "non clinical|it & telecom|software|licenses",
    "non clinical|it & telecom|software|saas",
    "non clinical|it & telecom|cloud services|paas"
  ],
  "dataset_name": "innova",
  "priority": 10,
  "notes": "Microsoft can only be in these categories",
  "created_by": "user@example.com"
}
```

**Request Fields:**
- `supplier_name` (required, string): Supplier name
- `allowed_taxonomy_paths` (required, array of strings): List of allowed classification paths
- `dataset_name` (optional, string): Dataset-specific rule
- `priority` (optional, int, default: 10): Rule priority
- `notes` (optional, string): Notes about the rule
- `created_by` (optional, string): Creator identifier

**Response:** `200 OK`
```json
{
  "id": 1,
  "supplier_name": "Microsoft",
  "allowed_taxonomy_paths": [
    "non clinical|it & telecom|software|licenses",
    "non clinical|it & telecom|software|saas",
    "non clinical|it & telecom|cloud services|paas"
  ],
  "dataset_name": "innova",
  "priority": 10,
  "active": true,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00",
  "created_by": "user@example.com",
  "notes": "Microsoft can only be in these categories"
}
```

**How It Works:**
- When classification encounters this supplier, it uses the stored paths instead of RAG
- LLM still classifies, but only from the allowed paths
- Useful when a supplier can be in multiple categories but you want to limit the options

---

#### List Taxonomy Constraints

**GET** `/supplier-rules/taxonomy-constraints`

List taxonomy constraint rules with optional filters.

**Query Parameters:**
- `supplier_name` (optional, string): Filter by supplier name
- `dataset_name` (optional, string): Filter by dataset name
- `active_only` (optional, bool, default: true): Only return active constraints

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "supplier_name": "Microsoft",
    "allowed_taxonomy_paths": [
      "non clinical|it & telecom|software|licenses",
      "non clinical|it & telecom|software|saas",
      "non clinical|it & telecom|cloud services|paas"
    ],
    "dataset_name": "innova",
    "priority": 10,
    "active": true,
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00",
    "created_by": "user@example.com",
    "notes": "Microsoft can only be in these categories"
  }
]
```

---

#### Get Taxonomy Constraint

**GET** `/supplier-rules/taxonomy-constraints/{constraint_id}`

Get a specific taxonomy constraint rule.

**Path Parameters:**
- `constraint_id` (required, int): Constraint ID

**Response:** `200 OK`
```json
{
  "id": 1,
  "supplier_name": "Microsoft",
  "allowed_taxonomy_paths": [
    "non clinical|it & telecom|software|licenses",
    "non clinical|it & telecom|software|saas",
    "non clinical|it & telecom|cloud services|paas"
  ],
  "dataset_name": "innova",
  "priority": 10,
  "active": true,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00",
  "created_by": "user@example.com",
  "notes": "Microsoft can only be in these categories"
}
```

---

#### Update Taxonomy Constraint

**PUT** `/supplier-rules/taxonomy-constraints/{constraint_id}`

Update a taxonomy constraint rule.

**Path Parameters:**
- `constraint_id` (required, int): Constraint ID

**Request Body:**
```json
{
  "allowed_taxonomy_paths": [
    "non clinical|it & telecom|software|licenses",
    "non clinical|it & telecom|software|saas"
  ],
  "priority": 15,
  "active": true,
  "notes": "Updated constraint list"
}
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "supplier_name": "Microsoft",
  "allowed_taxonomy_paths": [
    "non clinical|it & telecom|software|licenses",
    "non clinical|it & telecom|software|saas"
  ],
  "dataset_name": "innova",
  "priority": 15,
  "active": true,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T11:00:00",
  "created_by": "user@example.com",
  "notes": "Updated constraint list"
}
```

---

#### Delete Taxonomy Constraint

**DELETE** `/supplier-rules/taxonomy-constraints/{constraint_id}`

Delete a taxonomy constraint rule.

**Path Parameters:**
- `constraint_id` (required, int): Constraint ID

**Query Parameters:**
- `hard_delete` (optional, bool, default: false): Hard delete (vs soft delete by setting `active=False`)

**Response:** `200 OK`
```json
{
  "message": "Taxonomy constraint deleted successfully"
}
```

---

## Common Patterns

### Pagination

Most list endpoints support pagination:

- `page`: Page number (1-indexed, default: 1)
- `limit`: Items per page (default: 50, max: 200)

Response includes:
- `total`: Total number of items
- `pages`: Total number of pages
- `page`: Current page number
- `limit`: Items per page

### Filtering

Many endpoints support filtering via query parameters:

- **Transactions**: `l1`, `l2`, `l3`, `l4`, `supplier_name`, `confidence`
- **Feedback**: `status`, `dataset_id`, `action_type`
- **Supplier Rules**: `supplier_name`, `dataset_name`, `active_only`

**Note**: URL encode spaces in filter values (e.g., `non%20clinical` for `non clinical`)

### Foldername Handling

- Use `foldername=""` (empty string) for datasets directly under `datasets/`
- Use `foldername="default"` or other folder names for nested datasets
- Foldername is optional in most endpoints (defaults to `"default"`)

---

## Error Handling

### Error Response Format

All errors follow this format:

```json
{
  "detail": "Error message or array of validation errors",
  "error_type": "ErrorTypeName"
}
```

### HTTP Status Codes

- `200 OK` - Success
- `201 Created` - Resource created
- `204 No Content` - Success (no response body)
- `400 Bad Request` - Invalid request
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error

### Common Error Types

#### 400 Bad Request
```json
{
  "detail": "Direct mapping already exists for supplier 'AWS'",
  "error_type": "ValidationError"
}
```

#### 404 Not Found
```json
{
  "detail": "Dataset 'invalid_dataset' not found in folder ''",
  "error_type": "DatasetNotFoundError"
}
```

#### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "dataset_id"],
      "msg": "dataset_id can only contain alphanumeric characters, underscore, hyphen, and dot",
      "type": "value_error"
    }
  ],
  "error_type": "ValidationError"
}
```

### Error Types

- `DatasetNotFoundError` - Dataset doesn't exist
- `InvalidDatasetIdError` - Invalid dataset ID format
- `TransactionNotFoundError` - Transaction not found
- `FeedbackNotFoundError` - Feedback not found
- `InvalidFeedbackStateError` - Invalid feedback state transition
- `ValidationError` - Request validation failed
- `WorkflowError` - Workflow state error
- `ClassificationError` - Classification process error

---

## Notes

### Storage Backend

The API supports both local filesystem and S3 storage. Configure via environment variables:

- `STORAGE_TYPE=local` or `STORAGE_TYPE=s3`
- For S3: Set `S3_BUCKET` and optionally `S3_PREFIX`

### Dataset IDs

Must contain only alphanumeric characters, underscore, hyphen, and dot.

### Feedback Workflow States

- `pending` → `approved` → `applied`
- Only `pending` feedback can be deleted

### Supplier Rules Priority

- Higher priority rules are checked first
- Dataset-specific rules (`dataset_name` set) take precedence over global rules (`dataset_name=None`)

### Direct Mappings vs Taxonomy Constraints

- **Direct Mappings**: Skip LLM classification entirely - return stored path immediately (fastest)
- **Taxonomy Constraints**: Replace RAG retrieval with stored list - LLM still classifies but only from allowed paths

### Classification Workflow

The workflow is decoupled into three stages:

1. **Canonicalization**: Maps client columns to canonical schema (automated)
2. **Verification**: Human review where you can add/remove columns and fix mappings
3. **Classification**: Runs full classification on verified dataset

Workflow state is tracked in the database and can be paused/resumed at any stage.

---

## Quick Reference

### Complete Workflow Example

```bash
# 1. Create dataset (file upload)
curl -X POST "http://localhost:8000/api/v1/datasets/upload" \
  -F "dataset_id=innova" \
  -F "foldername=" \
  -F "input_csv=@datasets/innova/input.csv" \
  -F "taxonomy_yaml=@datasets/innova/taxonomy.yaml"

# 2. Canonicalize
curl -X POST "http://localhost:8000/api/v1/datasets/innova/canonicalize?foldername="

# 3. Verify (auto-approve)
curl -X POST "http://localhost:8000/api/v1/datasets/innova/verify?foldername=" \
  -H "Content-Type: application/json" \
  -d '{"auto_approve": true}'

# 4. Start Classification (async - returns immediately)
curl -X POST "http://localhost:8000/api/v1/datasets/innova/classify?foldername=&max_workers=4"

# 5. Poll Status (check progress)
while true; do
  STATUS=$(curl -s "http://localhost:8000/api/v1/datasets/innova/status?foldername=" | jq -r '.status')
  PROGRESS=$(curl -s "http://localhost:8000/api/v1/datasets/innova/status?foldername=" | jq -r '.progress_percentage // 0')
  echo "Status: $STATUS (Progress: $PROGRESS%)"
  
  if [ "$STATUS" = "completed" ]; then
    echo "✅ Classification completed!"
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "❌ Classification failed!"
    break
  fi
  
  sleep 3
done

# 6. Query results
curl "http://localhost:8000/api/v1/transactions?dataset_id=innova&foldername=&page=1&limit=50"

# 7. Submit feedback
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": "innova", "foldername": "", "row_index": 2, "corrected_path": "non clinical|professional services|consulting", "feedback_text": "Should be professional services"}'

# 8. Approve and apply feedback
FEEDBACK_ID=1
curl -X POST "http://localhost:8000/api/v1/feedback/$FEEDBACK_ID/approve" \
  -H "Content-Type: application/json" \
  -d '{}'
curl -X POST "http://localhost:8000/api/v1/feedback/$FEEDBACK_ID/apply" \
  -H "Content-Type: application/json" \
  -d '{"row_indices": [2]}'
```

### Async Classification Pattern

For large datasets, classification runs asynchronously:

1. **Start Classification**: POST returns immediately with `"status": "started"`
2. **Poll Status**: GET `/datasets/{dataset_id}/status` to check progress
3. **Monitor Progress**: Response includes `progress_percentage`, `progress_invoices_processed`, `progress_invoices_total`
4. **Completion**: Status changes to `"completed"` when done

**Benefits:**
- No HTTP timeouts for long-running processes
- Real-time progress tracking
- Better user experience
- Can handle datasets of any size

---

**Last Updated**: December 2024
**API Version**: 1.0.0
