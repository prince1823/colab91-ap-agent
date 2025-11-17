"""Test script for research agent using real supplier data from extraction_outputs."""

from datetime import datetime
from pathlib import Path

import pandas as pd
from core.agents.research import ResearchAgent

transaction_csv = Path("extraction_outputs/FOX_20230816_161348/transaction_data.csv")

if not transaction_csv.exists():
    print(f"Transaction data not found: {transaction_csv}")
    exit(1)

df = pd.read_csv(transaction_csv, nrows=5)
supplier_names = df['Supplier Name old'].dropna().unique()[:5].tolist()

if not supplier_names:
    supplier_names = [
        "Amazon",
        "Microsoft",
        "Google",
        "Apple",
        "IBM",
    ]

agent = ResearchAgent(enable_tracing=True)
results_data = []

for supplier_name in supplier_names:
    row_data = {"supplier_name": supplier_name}
    
    try:
        profile = agent.research_supplier(supplier_name)
        row_data.update({
            "success": "Yes",
            "official_business_name": profile.official_business_name,
            "industry": profile.industry,
            "website_url": profile.website_url or "",
            "products_services": profile.products_services,
            "parent_company": profile.parent_company or "",
            "confidence": profile.confidence,
            "description": profile.description[:1000] if profile.description else "",
            "error": "",
        })
    except Exception as e:
        row_data.update({
            "success": "No",
            "official_business_name": "",
            "industry": "",
            "website_url": "",
            "products_services": "",
            "parent_company": "",
            "confidence": "",
            "description": "",
            "error": str(e),
        })
    
    results_data.append(row_data)

successful = sum(1 for r in results_data if r["success"] == "Yes")
print(f"Research complete: {successful}/{len(results_data)} successful")

results_dir = Path("results")
results_dir.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_csv_path = results_dir / f"research_{timestamp}.csv"

results_df = pd.DataFrame(results_data)
results_df.to_csv(output_csv_path, index=False)

print(f"Results saved to: {output_csv_path}")
