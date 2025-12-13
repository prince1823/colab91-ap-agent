# Spend Classification Backend API Documentation

## Base URL
```
http://localhost:8000/api/v1
```

## Authentication
Currently, the API does not require authentication. In production, implement authentication/authorization.

## Common Response Formats

### Success Response
All successful responses return data in the format specified by each endpoint.

### Error Response
```json
{
  "detail": "Error message",
  "error_type": "ErrorTypeName"
}
```

### HTTP Status Codes
- `200 OK` - Success
- `201 Created` - Resource created
- `400 Bad Request` - Invalid request
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error

---

## Datasets API

### List Datasets
**GET** `/datasets`

List all available datasets.

**Query Parameters:**
- `foldername` (optional, string): Filter by folder name (e.g., "default", "test_bench")

**Response:** `200 OK`
```json
[
  {
    "dataset_id": "innova",
    "foldername": "default",
    "row_count": 256
  }
]
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/datasets?foldername=default"
```

---

### Get Dataset Details
**GET** `/datasets/{dataset_id}`

Get detailed information about a specific dataset.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier (e.g., "innova", "fox")

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "default",
  "row_count": 256,
  "csv_path_or_uri": "benchmarks/default/innova/output.csv"
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/datasets/innova?foldername=default"
```

---

## Classification Workflow API

The classification workflow is a 3-stage process:
1. **Canonicalization** - Map client columns to canonical schema
2. **Verification** - Human review and modification (add/remove columns, fix mappings)
3. **Classification** - Run full classification on verified dataset

### Start Canonicalization
**POST** `/datasets/{dataset_id}/canonicalize`

Start the canonicalization stage for a dataset. This maps client-specific column names to the canonical schema.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier (e.g., "innova", "fox")

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "default",
  "status": "canonicalized",
  "mapping_result": {
    "mappings": {
      "Vendor": "supplier_name",
      "Amount": "amount",
      "Date": "transaction_date"
    },
    "unmapped_columns": ["internal_id"],
    "validation_passed": true
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/canonicalize?foldername=default"
```

---

### Get Canonicalization for Review
**GET** `/datasets/{dataset_id}/canonicalization`

Get canonicalization results for human review. Returns mappings, current columns, and paths for inspection.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "default",
  "canonicalization_result": {
    "mappings": {
      "Vendor": "supplier_name",
      "Amount": "amount",
      "Date": "transaction_date"
    },
    "unmapped_columns": ["internal_id"],
    "validation_passed": true,
    "validation_errors": []
  },
  "canonicalized_csv_path": "/path/to/datasets/default/innova/canonicalized.csv",
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
curl "http://localhost:8000/api/v1/datasets/innova/canonicalization?foldername=default"
```

---

### Verify Canonicalization (Human-in-the-Loop)
**POST** `/datasets/{dataset_id}/verify`

Approve canonicalization with optional modifications. This is the human-in-the-loop step where you can:
- **Update column mappings** (correct LLM mistakes)
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
    },
    {
      "canonical_name": "department",
      "default_value": "Unknown",
      "description": "Department code"
    }
  ],
  "columns_to_remove": [
    "internal_reference",
    "temp_column"
  ],
  "notes": "Added invoice_date and department columns, removed internal references",
  "auto_approve": false
}
```

**Request Body Fields:**
- `approved_mappings` (optional, object): Updated column mappings `{client_col: canonical_col}`
- `columns_to_add` (optional, array): Columns to add. Each object should have:
  - `canonical_name` (required, string): Canonical column name
  - `default_value` (optional, any): Default value for all rows (default: "")
  - `description` (optional, string): Description of the column
- `columns_to_remove` (optional, array): List of canonical column names to remove
- `notes` (optional, string): Verification notes
- `auto_approve` (optional, bool, default: false): Auto-approve without human review (for benchmarks)

**Response:** `200 OK`
```json
{
  "status": "verified",
  "message": "Canonicalization approved"
}
```

**Example - Add Missing Column:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/verify?foldername=default" \
  -H "Content-Type: application/json" \
  -d '{
    "columns_to_add": [
      {
        "canonical_name": "cost_center",
        "default_value": "0000",
        "description": "Cost center for spend categorization"
      }
    ],
    "notes": "Added cost_center column for better classification"
  }'
```

**Example - Remove Unwanted Columns:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/verify?foldername=default" \
  -H "Content-Type: application/json" \
  -d '{
    "columns_to_remove": [
      "internal_id",
      "batch_number",
      "processing_timestamp"
    ],
    "notes": "Removed internal tracking columns"
  }'
```

**Example - Combined Modifications:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/verify?foldername=default" \
  -H "Content-Type: application/json" \
  -d '{
    "approved_mappings": {
      "ClientVendor": "supplier_name"
    },
    "columns_to_add": [
      {
        "canonical_name": "project_code",
        "default_value": ""
      }
    ],
    "columns_to_remove": ["temp_field", "debug_column"],
    "notes": "Fixed vendor mapping, added project_code, removed debug columns"
  }'
```

**Example - Auto-approve (for benchmarks):**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/verify?foldername=default" \
  -H "Content-Type: application/json" \
  -d '{
    "auto_approve": true
  }'
```

---

### Start Classification
**POST** `/datasets/{dataset_id}/classify`

Start the classification stage on a verified canonicalized dataset. This runs the full classification pipeline with supplier research and expert classification.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name
- `max_workers` (optional, int, default: 4, min: 1, max: 16): Number of parallel workers

**Response:** `200 OK`
```json
{
  "status": "completed",
  "dataset_id": "innova",
  "foldername": "default",
  "row_count": 256,
  "message": "Classification completed successfully"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/datasets/innova/classify?foldername=default&max_workers=4"
```

---

### Get Workflow Status
**GET** `/datasets/{dataset_id}/status`

Get the current workflow status for a dataset. Shows which stage the dataset is in and relevant paths.

**Path Parameters:**
- `dataset_id` (required, string): Dataset identifier

**Query Parameters:**
- `foldername` (optional, string, default: "default"): Folder name

**Response:** `200 OK`
```json
{
  "dataset_id": "innova",
  "foldername": "default",
  "status": "verified",
  "canonicalized_csv_path": "/path/to/datasets/default/innova/canonicalized.csv",
  "classification_result_path": null,
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "error_message": null,
  "created_at": "2024-01-15T10:00:00",
  "updated_at": "2024-01-15T10:05:00"
}
```

**Status Values:**
- `pending` - Not started
- `canonicalizing` - Currently running canonicalization
- `canonicalized` - Canonicalization complete, awaiting verification
- `awaiting_verification` - Ready for human review
- `verified` - Verified and ready for classification
- `classifying` - Currently running classification
- `completed` - All stages complete
- `failed` - Error occurred

**Example:**
```bash
curl "http://localhost:8000/api/v1/datasets/innova/status?foldername=default"
```

---

## Transactions API

### Query Transactions
**GET** `/transactions`

Query classified transactions from a dataset with filtering and pagination.

**Query Parameters:**
- `dataset_id` (required, string): Dataset identifier (e.g., "innova", "fox")
- `foldername` (optional, string, default: "default"): Folder name
- `l1` (optional, string): Filter by L1 category
- `confidence` (optional, string): Filter by confidence level
- `supplier_name` (optional, string): Filter by supplier name
- `page` (optional, int, default: 1, min: 1): Page number (1-indexed)
- `limit` (optional, int, default: 50, min: 1, max: 200): Number of rows per page

**Response:** `200 OK`
```json
{
  "rows": [
    {
      "L1": "it & telecom",
      "L2": "cloud services",
      "L3": "iaas",
      "supplier_name": "AWS",
      "confidence": "high",
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
curl "http://localhost:8000/api/v1/transactions?dataset_id=innova&l1=it%20%26%20telecom&page=1&limit=50"
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
    "L1": "it & telecom",
    "L2": "cloud services",
    "L3": "iaas",
    "supplier_name": "AWS",
    "amount": 1000.00,
    ...
  }
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/transactions/42?dataset_id=innova"
```

---

### Update Transaction Classification
**PUT** `/transactions/{row_index}`

Update a transaction's classification path.

**Path Parameters:**
- `row_index` (required, int): Row index (0-based)

**Query Parameters:**
- `dataset_id` (required, string): Dataset identifier
- `foldername` (optional, string, default: "default"): Folder name

**Request Body:**
```json
{
  "classification_path": "it & telecom|cloud services|iaas",
  "override_rule_applied": "manual_correction_123"
}
```

**Response:** `200 OK`
```json
{
  "row_index": 42,
  "data": {
    "L1": "it & telecom",
    "L2": "cloud services",
    "L3": "iaas",
    "override_rule_applied": "manual_correction_123",
    ...
  }
}
```

**Example:**
```bash
curl -X PUT "http://localhost:8000/api/v1/transactions/42?dataset_id=innova" \
  -H "Content-Type: application/json" \
  -d '{"classification_path": "it & telecom|cloud services|iaas"}'
```

---

## Feedback API

### List Feedback
**GET** `/feedback`

List all feedback items with optional filters and pagination.

**Query Parameters:**
- `status` (optional, string): Filter by status ("pending", "approved", "applied")
- `dataset_id` (optional, string): Filter by dataset ID
- `action_type` (optional, string): Filter by action type ("company_context", "taxonomy_description", "supplier_rule", "transaction_rule")
- `page` (optional, int, default: 1, min: 1): Page number
- `limit` (optional, int, default: 50, min: 1, max: 200): Items per page

**Response:** `200 OK`
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

**Example:**
```bash
curl "http://localhost:8000/api/v1/feedback/1"
```

---

### Submit Feedback
**POST** `/feedback`

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

**Response:** `200 OK`
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

**Action Types:**
- `supplier_rule`: Creates supplier classification rule
  - Category A: Direct mapping (100% confidence, single path, stored in `supplier_direct_mappings`)
  - Category B: Taxonomy constraint (multiple allowed paths, stored in `supplier_taxonomy_constraints`)
- `transaction_rule`: Creates transaction attribute-based rule (e.g., GL code rules)
- `company_context`: Updates company context in taxonomy YAML
- `taxonomy_description`: Updates taxonomy category descriptions in YAML

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "innova",
    "foldername": "default",
    "row_index": 42,
    "corrected_path": "it & telecom|cloud services|iaas",
    "feedback_text": "This supplier always provides cloud infrastructure services"
  }'
```

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
      "row_idx": 42,
      "L1": "it & telecom",
      "supplier_name": "AWS",
      ...
    }
  ],
  "count": 15,
  "row_indices": [42, 87, 133, ...]
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/feedback/1/preview"
```

---

### Apply Feedback
**POST** `/feedback/{feedback_id}/apply`

Execute action and apply bulk corrections to CSV.

**Path Parameters:**
- `feedback_id` (required, int): Feedback ID

**Request Body:**
```json
{
  "row_indices": [42, 87, 133]
}
```

**Response:** `200 OK`
```json
{
  "updated_count": 3
}
```

**What Happens:**
- For **supplier_rule** actions:
  - Category A: Creates/updates entry in `supplier_direct_mappings` table
  - Category B: Creates/updates entry in `supplier_taxonomy_constraints` table
  - Rule is immediately active and will be used by classification pipeline for future transactions
- For **transaction_rule** actions: Creates entry in `transaction_rules` table
- For **company_context** and **taxonomy_description** actions: Updates YAML files
- Updates specified rows in CSV with corrected classification
- Sets feedback status to "applied"

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/feedback/1/apply" \
  -H "Content-Type: application/json" \
  -d '{"row_indices": [42, 87, 133]}'
```

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

## Supplier Rules API

### Direct Mappings (100% Confidence)

#### Create Direct Mapping
**POST** `/supplier-rules/direct-mappings`

Create a direct mapping rule for a supplier. When this supplier is encountered, all transactions will be directly mapped to the specified classification path without LLM classification.

**Request Body:**
```json
{
  "supplier_name": "AWS",
  "classification_path": "it & telecom|cloud services|iaas",
  "dataset_name": "innova",
  "priority": 10,
  "notes": "100% confident this supplier always maps here",
  "created_by": "user@example.com"
}
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "supplier_name": "AWS",
  "classification_path": "it & telecom|cloud services|iaas",
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
    "classification_path": "it & telecom|cloud services|iaas",
    "dataset_name": "innova",
    "priority": 10
  }'
```

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
    "classification_path": "it & telecom|cloud services|iaas",
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
  "classification_path": "it & telecom|cloud services|iaas",
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
  "classification_path": "it & telecom|cloud services|paas",
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
  "classification_path": "it & telecom|cloud services|paas",
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
- `hard_delete` (optional, bool, default: false): Hard delete (vs soft delete by setting active=False)

**Response:** `200 OK`
```json
{
  "message": "Direct mapping deleted successfully"
}
```

---

### Taxonomy Constraints

#### Create Taxonomy Constraint
**POST** `/supplier-rules/taxonomy-constraints`

Create a taxonomy constraint for a supplier. When this supplier is encountered, instead of using RAG to retrieve taxonomy paths, use the stored list of allowed paths for LLM classification.

**Request Body:**
```json
{
  "supplier_name": "Microsoft",
  "allowed_taxonomy_paths": [
    "it & telecom|software|licenses",
    "it & telecom|software|saas",
    "it & telecom|cloud services|paas"
  ],
  "dataset_name": "innova",
  "priority": 10,
  "notes": "Microsoft can only be in these categories",
  "created_by": "user@example.com"
}
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "supplier_name": "Microsoft",
  "allowed_taxonomy_paths": [
    "it & telecom|software|licenses",
    "it & telecom|software|saas",
    "it & telecom|cloud services|paas"
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
      "it & telecom|software|licenses",
      "it & telecom|software|saas",
      "it & telecom|cloud services|paas"
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
    "it & telecom|software|licenses",
    "it & telecom|software|saas",
    "it & telecom|cloud services|paas"
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
    "it & telecom|software|licenses",
    "it & telecom|software|saas"
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
    "it & telecom|software|licenses",
    "it & telecom|software|saas"
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
- `hard_delete` (optional, bool, default: false): Hard delete (vs soft delete by setting active=False)

**Response:** `200 OK`
```json
{
  "message": "Taxonomy constraint deleted successfully"
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Direct mapping already exists for supplier 'AWS'",
  "error_type": "ValidationError"
}
```

### 404 Not Found
```json
{
  "detail": "Dataset 'invalid_dataset' not found in folder 'default'",
  "error_type": "DatasetNotFoundError"
}
```

### 422 Unprocessable Entity
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

---

## Interactive API Documentation

FastAPI automatically generates interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide interactive documentation where you can test endpoints directly from the browser.

---

## Notes

1. **Storage Backend**: The API supports both local filesystem and S3 storage. Configure via environment variables:
   - `STORAGE_TYPE=local` or `STORAGE_TYPE=s3`
   - For S3: Set `S3_BUCKET` and optionally `S3_PREFIX`

2. **Dataset IDs**: Must contain only alphanumeric characters, underscore, hyphen, and dot.

3. **Feedback Workflow**: 
   - Submit → Pending
   - Approve → Approved
   - Apply → Applied
   - Only pending feedback can be deleted

4. **Supplier Rules Priority**: Higher priority rules are checked first. Dataset-specific rules take precedence over global rules (dataset_name=None).

5. **Direct Mappings**: Skip LLM classification entirely - return stored path immediately.

6. **Taxonomy Constraints**: Replace RAG retrieval with stored list - LLM still classifies but only from allowed paths.

7. **Classification Workflow**: The workflow is decoupled into three stages:
   - **Canonicalization**: Maps client columns to canonical schema (automated)
   - **Verification**: Human review where you can add/remove columns and fix mappings
   - **Classification**: Runs full classification on verified dataset
   - Workflow state is tracked in the database and can be paused/resumed at any stage

