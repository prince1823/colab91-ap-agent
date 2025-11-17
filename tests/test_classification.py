"""Test script for spend classification agent."""

from datetime import datetime
from pathlib import Path

import pandas as pd
from core.agents.spend_classification import SpendClassifier
from core.agents.research import ResearchAgent

taxonomy_path = Path("taxonomies/FOX_20230816_161348.yaml")
transaction_csv = Path("extraction_outputs/FOX_20230816_161348/transaction_data.csv")

if not taxonomy_path.exists():
    print(f"Taxonomy file not found: {taxonomy_path}")
    print("Please ensure taxonomy files are generated first.")
    exit(1)

if not transaction_csv.exists():
    print(f"Transaction data not found: {transaction_csv}")
    exit(1)

classifier = SpendClassifier(taxonomy_path=str(taxonomy_path), enable_tracing=True)
research_agent = ResearchAgent(enable_tracing=False)

df = pd.read_csv(transaction_csv, nrows=5)
sample_transactions = []
original_rows = []

for idx, row in df.iterrows():
    supplier_name = row.get('Supplier Name old') or row.get('Supplier Name', '')
    line_desc = row.get('Line Description', '')
    memo = row.get('Memo', '')
    business_unit = row.get('Business Unit', '')
    
    if supplier_name and pd.notna(supplier_name) and str(supplier_name).strip():
        sample_transactions.append({
            "supplier_name": str(supplier_name).strip(),
            "gl_description": str(memo) if pd.notna(memo) else "",
            "line_description": str(line_desc) if pd.notna(line_desc) else "",
            "department": str(business_unit) if pd.notna(business_unit) else "",
        })
        original_rows.append(row)

results_data = []

for i, transaction in enumerate(sample_transactions):
    supplier_name = transaction["supplier_name"]
    original_row = original_rows[i]
    
    row_data = {}
    
    for col in df.columns:
        value = original_row[col]
        row_data[f"original_{col}"] = value if pd.notna(value) else ""
    
    row_data.update({
        "supplier_name": supplier_name,
        "line_description": transaction.get("line_description", ""),
        "gl_description": transaction.get("gl_description", ""),
        "department": transaction.get("department", ""),
    })
    
    try:
        supplier_profile = research_agent.research_supplier(supplier_name)
        
        classification = classifier.classify_transaction(
            supplier_profile=supplier_profile.to_dict(),
            transaction_data=transaction,
        )
        
        row_data.update({
            "success": "Yes",
            "official_business_name": supplier_profile.official_business_name,
            "supplier_industry": supplier_profile.industry,
            "supplier_products_services": supplier_profile.products_services,
            "supplier_website_url": supplier_profile.website_url or "",
            "supplier_parent_company": supplier_profile.parent_company or "",
            "supplier_confidence": supplier_profile.confidence,
            "L1": classification.L1,
            "L2": classification.L2 or "",
            "L3": classification.L3 or "",
            "L4": classification.L4 or "",
            "L5": classification.L5 or "",
            "override_rule_applied": classification.override_rule_applied or "",
            "reasoning": classification.reasoning[:500] if classification.reasoning else "",
        })
    except Exception as e:
        row_data.update({
            "success": "No",
            "error": str(e),
            "official_business_name": "",
            "supplier_industry": "",
            "supplier_products_services": "",
            "supplier_website_url": "",
            "supplier_parent_company": "",
            "supplier_confidence": "",
            "L1": "",
            "L2": "",
            "L3": "",
            "L4": "",
            "L5": "",
            "override_rule_applied": "",
            "reasoning": "",
        })
    
    results_data.append(row_data)

successful = sum(1 for r in results_data if r["success"] == "Yes")
print(f"Classification complete: {successful}/{len(results_data)} successful")

results_dir = Path("results")
results_dir.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_csv_path = results_dir / f"classification_{timestamp}.csv"

results_df = pd.DataFrame(results_data)
results_df.to_csv(output_csv_path, index=False)

print(f"Results saved to: {output_csv_path}")
