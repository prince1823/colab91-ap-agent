"""
Canonical Columns Definition

Defines the standard column schema that all AP data should be mapped to.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CanonicalColumn:
    """Definition of a canonical column"""
    
    canonical_name: str
    data_type: str  # string, decimal, date, integer
    description: str
    common_aliases: List[str]
    relevance_for_spend_analysis: str  # Critical, High, Medium, Low
    validation_rules: Optional[dict] = None
    display_order: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for LLM prompt"""
        return {
            "name": self.canonical_name,
            "description": self.description,
            "data_type": self.data_type,
            "relevance_for_spend_analysis": self.relevance_for_spend_analysis,
            "common_aliases": self.common_aliases,
        }


# Standard Canonical Columns for AP Data
CANONICAL_COLUMNS = [
    # CRITICAL for spend classification
    CanonicalColumn(
        canonical_name="supplier_name",
        data_type="string",
        relevance_for_spend_analysis="Critical",
        description="Supplier/vendor name - CRITICAL for supplier-based spend categorization and supplier intelligence matching",
        common_aliases=["Vendor Name", "Supplier Name", "Payee", "Vendor", "Supplier"],
        display_order=1,
    ),
    CanonicalColumn(
        canonical_name="gl_description",
        data_type="string",
        relevance_for_spend_analysis="Critical",
        description="GL account description - CRITICAL for understanding the business categorization and spend type (e.g., 'Marketing - Digital Ads', 'IT - Software')",
        common_aliases=["GL Account Description", "Account Description", "GL Description", "Account Name", "GL Name"],
        display_order=2,
    ),
    CanonicalColumn(
        canonical_name="line_description",
        data_type="string",
        relevance_for_spend_analysis="Critical",
        description="Line item description - CRITICAL for understanding what was actually purchased (e.g., 'AWS Cloud Services', 'Office Supplies')",
        common_aliases=["Description", "Line Description", "Item Description", "Details", "Transaction Description", "Line Item Description"],
        display_order=3,
    ),
    CanonicalColumn(
        canonical_name="memo",
        data_type="string",
        relevance_for_spend_analysis="Medium",
        description="Memo/notes field - MEDIUM relevance for additional context about the transaction (e.g., operational journal entries, invoice details, transaction notes)",
        common_aliases=["Memo", "Notes", "Transaction Memo", "Invoice Memo", "Journal Memo", "Memo Field"],
        display_order=3,
    ),
    CanonicalColumn(
        canonical_name="line_memo",
        data_type="string",
        relevance_for_spend_analysis="Medium",
        description="Line-level memo/notes - MEDIUM relevance for line-item specific context and additional details about individual line items",
        common_aliases=["Line Memo", "Line Notes", "Item Memo", "Line Item Memo", "Line Item Notes"],
        display_order=3,
    ),
    
    # HIGH relevance for classification
    CanonicalColumn(
        canonical_name="gl_code",
        data_type="string",
        relevance_for_spend_analysis="High",
        description="GL account code - HIGH relevance for structured categorization and mapping to finance taxonomy",
        common_aliases=["GL Account", "Account Code", "GL Code", "Account Number", "GL Account Code"],
        display_order=4,
    ),
    CanonicalColumn(
        canonical_name="department",
        data_type="string",
        relevance_for_spend_analysis="High",
        description="Department/business unit - HIGH relevance for understanding spend context and org-specific categorization",
        common_aliases=["Department", "Dept", "Business Unit", "Division"],
        display_order=5,
    ),
    
    # MEDIUM relevance for enrichment
    CanonicalColumn(
        canonical_name="cost_center",
        data_type="string",
        relevance_for_spend_analysis="Medium",
        description="Cost center - MEDIUM relevance for expense allocation context",
        common_aliases=["Cost Center", "Cost Centre", "CC", "Cost Center Code"],
        display_order=6,
    ),
    CanonicalColumn(
        canonical_name="invoice_date",
        data_type="date",
        relevance_for_spend_analysis="Medium",
        description="Invoice/transaction date - MEDIUM relevance for temporal categorization patterns",
        common_aliases=["Invoice Date", "Inv Date", "Date", "Transaction Date", "Accounting Date"],
        display_order=7,
    ),
    CanonicalColumn(
        canonical_name="po_number",
        data_type="string",
        relevance_for_spend_analysis="Medium",
        description="Purchase order number - MEDIUM relevance for linking to contracts and negotiated categories",
        common_aliases=["PO Number", "PO #", "Purchase Order", "PO", "Purchase Order Number"],
        display_order=8,
    ),
    CanonicalColumn(
        canonical_name="supplier_address",
        data_type="string",
        relevance_for_spend_analysis="Medium",
        description="Supplier address/location - MEDIUM relevance for accurate web search and supplier identification. Map the most complete address field available (prefer complete 'Supplier Address' over individual components like City/State).",
        common_aliases=["Vendor Address", "Supplier Address", "Address", "Address Line1", "Address Line 1", "Supplier Address 1", "Location", "Vendor Location"],
        display_order=13,
    ),
    CanonicalColumn(
        canonical_name="company",
        data_type="string",
        relevance_for_spend_analysis="Medium",
        description="Company/legal entity - MEDIUM relevance for grouping transactions by business unit",
        common_aliases=["Company", "Company Name", "Legal Entity", "Entity", "Company Code"],
        display_order=14,
    ),
    CanonicalColumn(
        canonical_name="creation_date",
        data_type="date",
        relevance_for_spend_analysis="Low",
        description="Creation date of operational transaction or accounting journal - LOW relevance for classification, used for invoice grouping",
        common_aliases=["Creation Date of Operational Transaction or Accounting Journal", "Creation Date", "Journal Creation Date", "Transaction Creation Date"],
        display_order=15,
    ),

    # LOW relevance for analytics/reporting (not classification)
    CanonicalColumn(
        canonical_name="amount",
        data_type="decimal",
        relevance_for_spend_analysis="Low",
        description="Transaction amount - LOW relevance for classification (used for analytics/reporting, not categorization)",
        common_aliases=["Total", "Amount", "Cost", "Price", "Total Cost", "Total Amount", "Amount USD", "Ledger Debit Amount"],
        display_order=9,
    ),
    CanonicalColumn(
        canonical_name="currency",
        data_type="string",
        relevance_for_spend_analysis="Low",
        description="Currency code - LOW relevance for classification (used for financial reporting)",
        common_aliases=["Currency", "Currency Code", "CCY"],
        display_order=10,
    ),
    CanonicalColumn(
        canonical_name="supplier_id",
        data_type="string",
        relevance_for_spend_analysis="Low",
        description="Supplier identifier - LOW relevance for classification (just a system ID)",
        common_aliases=["Vendor ID", "Supplier ID", "Vendor Code", "Supplier Code", "Vendor Number"],
        display_order=11,
    ),
    CanonicalColumn(
        canonical_name="invoice_number",
        data_type="string",
        relevance_for_spend_analysis="Low",
        description="Invoice number - LOW relevance for classification (just a transaction ID)",
        common_aliases=["Invoice Number", "Invoice #", "Invoice No", "Invoice ID", "Inv Number", "Invoice Id"],
        display_order=12,
    ),
]


def get_canonical_columns_for_prompt() -> List[dict]:
    """
    Get canonical columns formatted for LLM prompt
    
    Returns:
        List of dictionaries with column information
    """
    return [col.to_dict() for col in CANONICAL_COLUMNS]


def get_canonical_columns_metadata() -> List[dict]:
    """
    Get canonical column metadata for UI/configuration use.
    
    Returns:
        List of dictionaries with canonical column details.
    """
    return [
        {
            "canonical_name": col.canonical_name,
            "data_type": col.data_type,
            "description": col.description,
            "relevance_for_spend_analysis": col.relevance_for_spend_analysis,
            "common_aliases": col.common_aliases,
            "display_order": col.display_order,
        }
        for col in sorted(CANONICAL_COLUMNS, key=lambda c: c.display_order)
    ]


def get_columns_by_relevance(relevance: str) -> List[str]:
    """
    Get canonical columns by relevance level
    
    Args:
        relevance: Relevance level (Critical, High, Medium, Low)
        
    Returns:
        List of column names at that relevance level
    """
    return [col.canonical_name for col in CANONICAL_COLUMNS 
            if col.relevance_for_spend_analysis == relevance]


