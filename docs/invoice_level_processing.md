# Invoice-Level Processing

## Overview

Transactions are now processed **by invoice** rather than row-by-row, reducing API calls by ~70-90% while improving accuracy through richer shared context.

**Impact:**
- ✅ Better accuracy from shared invoice context
- ✅ ~70-90% fewer API calls (1 per invoice vs 1 per row)
- ✅ Same output structure (L1-L5 per row)
- ✅ Fully backward compatible

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **One classification per row** | Maintains output structure while leveraging shared context |
| **Add `company` & `creation_date` columns** | Required for accurate invoice grouping |
| **Null handling: `<NULL>` sentinel** | Treats missing values as valid group keys, preserves all data |
| **15 rows per batch** | Balances token usage vs API efficiency |
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
   │   ├─> 2-15 rows: One LLM call
   │   └─> >15 rows: Batches of 15
   └─> Store Results → Per-row cache
4. Build Output → Add L1-L5 columns
```

---

## Batch Classification

| Invoice Size | Processing | Response Format |
|-------------|------------|-----------------|
| 1 row | Existing single-row logic | Single path |
| 2-15 rows | One LLM call | Single path OR JSON list |
| >15 rows | Batches of 15 | JSON list per batch |

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
| Large invoices (15+ rows) | Batches of 15 rows each, all classified |

---

## Performance

**API Call Reduction:**

| Operation | Before | After | Savings |
|-----------|--------|-------|---------|
| Context Prioritization | 1/row | 1/invoice | ~70-90% |
| Supplier Research | 1/supplier (cached) | Same | - |
| Classification | 1/row | 1/batch | Varies |

**Example (1000 rows, 4 rows/invoice avg):**
- Before: 1000 prioritization calls
- After: 250 prioritization calls
- **75% reduction**

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

**Performance Tuning:**
- Consider increasing `MAX_ROWS_PER_BATCH` (currently 15) for larger invoices if token limits allow
- Higher values = fewer API calls but larger prompts
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
self.MAX_ROWS_PER_BATCH = 15  # Controls both batch size and rows shown in prompt
```
- Determines how many rows processed per LLM call
- Also limits how many rows displayed in each batch's prompt
- Single variable ensures consistency

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
