# Invoice-Level Processing

## Overview

Transactions are now processed **by invoice** rather than row-by-row, improving accuracy through richer shared context.

**Impact:**
- ✅ Better accuracy from shared invoice context
- ✅ Same output structure (L1-L5 per row)
- ✅ Fully backward compatible

---

## High-Level Flow

The system processes transactions at the invoice level, grouping related rows together before classification:

```
1. Input Data
   └─> Raw transaction rows with invoice metadata

2. Column Canonicalization
   └─> Maps client-specific columns to standard names
   └─> Ensures required columns: invoice_date, company, supplier_name, creation_date

3. Invoice Grouping
   └─> Groups rows by invoice (same date, company, supplier, creation_date)
   └─> Each group = one invoice to process

4. For Each Invoice:
   ├─> Cache Check
   │   └─> If all rows cached → skip entire invoice
   │   └─> If partial cache → return cached, process uncached together
   │
   ├─> Context Prioritization
   │   └─> Single assessment per invoice (not per row)
   │   └─> Determines which context sources to use
   │
   ├─> Supplier Research
   │   └─> One lookup per supplier (cached across invoices)
   │
   ├─> RAG Search
   │   └─> Aggregates all row data from invoice
   │   └─> One search per invoice using rich context
   │
   ├─> Batch Classification
   │   ├─> 1 row: Use existing single-row logic
   │   ├─> 2-50 rows: One LLM call for entire invoice
   │   └─> >50 rows: Process in batches of 50
   │
   └─> Store Results
       └─> Cache each row's classification

5. Build Output
   └─> Add L1-L5 classification columns to each row
   └─> Maintains same output structure as before
```

**Key Insight:** All rows in an invoice share the same context (supplier, date, company), so processing them together provides richer information for more accurate classification.

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **One classification per row** | Maintains output structure while leveraging shared context |
| **Add `company` & `creation_date` columns** | Required for accurate invoice grouping |
| **Null handling: `<NULL>` sentinel** | Treats missing values as valid group keys, preserves all data |
| **50 rows per batch** | Balances token usage vs API efficiency |
| **LLM returns single path OR JSON list** | Handles common case (same classification) efficiently |
| **Tax override via prompt** | LLM identifies incidental tax contextually (more flexible than code) |
| **Two-tier fallback: majority → "Unknown"** | Uses invoice context for intelligent fallback |
| **RAG limits: 5 line + 3 GL descriptions** | Prevents token bloat for large invoices |
| **Hardcoded grouping columns** | Good defaults, TODO for config file |

---

## Invoice Grouping

**Grouping Columns:** `invoice_date`, `company`, `supplier_name`, `creation_date`

Rows with identical values = one invoice. Nulls use `<NULL>` sentinel (same null pattern grouped together).

**Example:**
```
5 rows → 3 invoices:
  Invoice A: Rows 1,2,5 (2024-01-15|Acme|AWS|2024-01-10)
  Invoice B: Row 3     (2024-01-20|Acme|AWS|2024-01-18)
  Invoice C: Row 4     (2024-01-15|Beta|AWS|2024-01-10)
```

---

## Processing Flow

```
1. Column Canonicalization → Maps client columns
2. Invoice Grouping → Groups by (date, company, supplier, creation_date)
3. For Each Invoice:
   ├─> Cache Check (row-level) → Skip if all cached
   ├─> Context Prioritization (invoice-level) → One decision per invoice
   ├─> Supplier Research → Cached (memory → DB → web)
   ├─> RAG Search → Aggregates all row data
   ├─> Batch Classification
   │   ├─> 1 row: classify_transaction()
   │   ├─> 2-50 rows: One LLM call
   │   └─> >50 rows: Batches of 50
   └─> Store Results → Per-row cache
4. Build Output → Add L1-L5 columns
```

---

## Batch Classification

| Invoice Size | Processing | Response Format |
|-------------|------------|-----------------|
| 1 row | Existing single-row logic | Single path |
| 2-50 rows | One LLM call | Single path OR JSON list |
| >50 rows | Batches of 50 | JSON list per batch |

**LLM Response Options:**
```
Option 1 (all rows same): "Technology|Software|Cloud Services"
Option 2 (different):     ["Tech|Software|SaaS", "Tech|Hardware|Servers", ...]
```

**Tax Override:** If invoice has mostly non-tax items + 1-2 tax lines → classify tax same as purchase items.
```
Example: 5 AWS lines + 1 tax line → All 6 = "Technology|Software|Cloud Services"
```

---

## RAG & Aggregation

**All rows scanned**, aggregated as:

| Field | Strategy |
|-------|----------|
| dept, gl_code, cost_center, po_number | First valid value |
| Line descriptions | Dedupe, first 5 unique |
| GL descriptions | Dedupe, first 3 unique |
| Supplier profile | Shared across invoice |

**Result:** One RAG search per invoice (vs per row) using rich aggregated data.

---

## Caching

| Level | Scope | Key | Impact |
|-------|-------|-----|--------|
| L1: Exact Match | Row-level | (supplier, tx_hash, run_id) | All cached → skip invoice |
| L2: Supplier Profile | Supplier-level | supplier_name | One research per invoice |
| L3: Taxonomy RAG | Run-level | taxonomy_file | One search per invoice |

**Mixed cache hits:** Return cached immediately, process uncached together.

---

## Error Handling

**Two-Tier Fallback:**
1. Use **majority** classification from already-classified rows
2. Use **"Unknown"** if no prior classifications or no majority

**Error Types:**

| Error | Handling |
|-------|----------|
| LLM call failed | Apply fallback to batch |
| JSON parse failed | Try regex → fallback |
| Partial response (len < expected) | Keep valid, fallback for missing |
| Response too long (len > expected) | Truncate |

**All errors log:** Invoice key, batch number, row indices, error type, fallback used, raw response (first 200 chars)

---

## Edge Cases

| Case | Handling |
|------|----------|
| Single-row invoice | Delegates to existing single-row logic (no penalty) |
| Missing grouping columns | `<NULL>` sentinel, same pattern grouped |
| Mixed cache hits | Return cached, process uncached together |
| Partial failures | Store successes, log failures, continue |
| Large invoices (50+ rows) | Batches of 50 rows each, all classified |

---

## Performance Considerations

The invoice-level approach processes multiple rows together, which can reduce the number of API calls needed. The exact reduction depends on invoice size and grouping patterns.

**Memory:** ~500KB for 1000 rows (negligible)

---

## Tracing & Debugging

**Invoice metadata in traces:**
```json
{
  "invoice_key": "2024-01-15|acme|aws|2024-01-10",
  "invoice_row_count": 3,
  "row_position": 0
}
```

**Tags:** `[Invoice-level processing]`, `[Invoice-level assessment: 3 line items]`

**Logs:**
```
INFO: Grouped 1000 rows into 247 invoices (avg 4.0 rows/invoice)
DEBUG: LLM returned single path for 3 rows: Technology|Software...
```

**Tuning:**
- Consider increasing `MAX_ROWS_PER_BATCH` (currently 50) for larger invoices if token limits allow
- Monitor token usage and classification quality when adjusting

---

## Configuration

**Grouping columns** ([invoice_grouping.py:53](../core/utils/invoice_grouping.py)):
```python
grouping_columns = ['invoice_date', 'company', 'supplier_name', 'creation_date']
# TODO: Make configurable via config file
```

**Batch size & display limit** ([agent.py:47](../core/agents/spend_classification/agent.py)):
```python
self.MAX_ROWS_PER_BATCH = 50  # Controls both batch size and rows shown in prompt
```
- Determines how many rows processed per LLM call
- Also limits how many rows displayed in each batch's prompt
- Single variable ensures consistency

---

## Hardcoded Values Requiring Configuration

The following hardcoded values should be made configurable to improve flexibility and adaptability across different clients and use cases:

### 1. Batch Size Limit (`MAX_ROWS_PER_BATCH`)

**Location:** [`core/agents/spend_classification/agent.py:47`](../core/agents/spend_classification/agent.py)

**Current Value:** `50`

**Impact:**
- Controls maximum number of rows processed per LLM call for large invoices
- Also limits how many line items are displayed in the prompt to the LLM
- Used in `_format_invoice_info()` to truncate display (line 262)
- Used in `classify_invoice()` for batch splitting (line 906)

**Why Make Configurable:**
- Different LLM models have different token limits
- Some clients may have invoices with consistently more/fewer line items
- Token usage vs. API efficiency trade-off may vary by use case

**Current Usage:**
```python
self.MAX_ROWS_PER_BATCH = 50  # Hardcoded in __init__
display_transactions = invoice_transactions[:self.MAX_ROWS_PER_BATCH]  # Line 262
for batch_idx in range(0, len(invoice_transactions), self.MAX_ROWS_PER_BATCH):  # Line 906
```

---

### 2. Invoice Grouping Columns

**Location:** [`core/utils/invoice_grouping.py:53`](../core/utils/invoice_grouping.py)

**Current Value:** `['invoice_date', 'company', 'supplier_name', 'creation_date']`

**Impact:**
- Determines which columns are used to group transaction rows into invoices
- All rows with identical values across these columns are treated as one invoice
- Critical for invoice-level processing accuracy

**Why Make Configurable:**
- Different clients may have different invoice identification schemes
- Some clients may need additional columns (e.g., `invoice_number`, `document_id`)
- Some clients may not have `creation_date` or may use different date fields
- Grouping strategy may need to vary by client data structure

**Current Usage:**
```python
grouping_columns = ['invoice_date', 'company', 'supplier_name', 'creation_date']  # Line 53
invoice_key = create_invoice_key(row_dict, grouping_columns)  # Line 61
```

**Note:** Already has TODO comments indicating need for configuration (lines 45, 52).

---

### 3. Data Fields Displayed to LLM (`_format_invoice_info`)

**Location:** [`core/agents/spend_classification/agent.py:196-303`](../core/agents/spend_classification/agent.py)

**Current Hardcoded Fields:**

#### Invoice-Level Shared Fields (Lines 222-228)
```python
for field_name, label in [
    ('invoice_date', 'Invoice Date'),
    ('company', 'Company'),
    ('po_number', 'PO Number'),
    ('department', 'Department'),
    ('cost_center', 'Cost Center'),
]:
```

#### Line Item Fields (Lines 265-293)
- `line_description` - Line description (truncated to 150 chars)
- `gl_description` - GL description (truncated to 100 chars)
- `gl_code` - GL code
- `amount` - Transaction amount

#### Aggregation Limits in `classify_invoice()` (Lines 852-880)
- **Structured fields aggregated:** `['department', 'gl_code', 'cost_center', 'po_number']` (line 852)
- **Line descriptions:** First 5 unique values (line 865)
- **GL descriptions:** First 3 unique values (line 877)

**Why Make Configurable:**
- Different clients have different data quality and field availability
- Some clients may have more informative fields that should be prioritized
- Field truncation limits (150/100 chars) may need adjustment
- Aggregation limits (5 line descriptions, 3 GL descriptions) may need tuning
- Field selection should adapt to what's available in the data

**Current Behavior:**
- Fixed set of fields always shown (if available)
- Truncation limits are hardcoded
- Aggregation limits are hardcoded
- No way to prioritize different fields based on client needs

**Recommendation:**
- Make field selection configurable (which fields to show, in what order)
- Make truncation limits configurable
- Make aggregation limits configurable
- Allow field prioritization based on data availability or client preferences

---

### Summary of Configuration Needs

| Item | Current Value | Location | Priority | Impact |
|------|---------------|----------|----------|--------|
| **MAX_ROWS_PER_BATCH** | `50` | `agent.py:47` | High | Affects token usage and API efficiency |
| **Grouping Columns** | `['invoice_date', 'company', 'supplier_name', 'creation_date']` | `invoice_grouping.py:53` | High | Critical for invoice identification |
| **Shared Fields Display** | `['invoice_date', 'company', 'po_number', 'department', 'cost_center']` | `agent.py:222-228` | Medium | Affects LLM context quality |
| **Line Item Fields** | `['line_description', 'gl_description', 'gl_code', 'amount']` | `agent.py:265-293` | Medium | Affects classification accuracy |
| **Line Desc Aggregation** | `5 unique values` | `agent.py:865` | Low | Prevents token bloat |
| **GL Desc Aggregation** | `3 unique values` | `agent.py:877` | Low | Prevents token bloat |
| **Truncation Limits** | `150 chars (line), 100 chars (GL)` | `agent.py:271, 278` | Low | Affects information completeness |

**Next Steps:**
1. Create configuration schema for these values
2. Add to `core/config.py` or separate config file
3. Update `ExpertClassifier.__init__()` to accept configuration
4. Update `group_transactions_by_invoice()` to use configurable columns
5. Refactor `_format_invoice_info()` to use configurable field selection

---

## Code References

**New Files:**
- [core/utils/invoice_grouping.py](../core/utils/invoice_grouping.py)

**Modified Files:**
- [canonical_columns.py](../core/agents/column_canonicalization/canonical_columns.py) - Added `company` (L113), `creation_date` (L121)
- [spend_classification/agent.py](../core/agents/spend_classification/agent.py) - Batch classification, `_parse_multi_classification_response()`
- [context_prioritization/agent.py](../core/agents/context_prioritization/agent.py) - `assess_invoice_context()`
- [pipeline.py](../core/pipeline.py) - `_classify_invoice()`, main orchestration

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Too many invoices (1:1 with rows) | Check NULL values, verify column mappings |
| Too few invoices (all rows together) | Add discriminating columns, check data quality |
| Classification quality degraded | Increase limits (5 line → more, 3 GL → more) |
| Cache hit rate dropped | Verify transaction hash unchanged |

---

## Future Enhancements

- Configurable grouping columns (config file)
- Parallel invoice processing
- Invoice-level cache (deduplicate identical invoices)
- ML-based invoice detection

---

**Last Updated:** 2025-12-09
