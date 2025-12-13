"""Expert Spend Classification Agent using ChainOfThought (single-shot) with semantic pre-search."""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import dspy
import yaml

from core.agents.context_prioritization.model import PrioritizationDecision
from core.agents.spend_classification.model import ClassificationResult
from core.agents.spend_classification.signature import SpendClassificationSignature
from core.agents.spend_classification.tools import validate_path, lookup_paths
from core.agents.taxonomy_rag import TaxonomyRetriever
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.utils.transaction_utils import is_valid_value
from core.utils.invoice_config import InvoiceProcessingConfig, DEFAULT_CONFIG
from core.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class ExpertClassifier:
    """ChainOfThought-based Spend Classification Agent with semantic taxonomy pre-search."""

    def __init__(
        self,
        taxonomy_path: Optional[str] = None,
        lm: Optional[dspy.LM] = None,
        enable_tracing: bool = True,
    ):
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="expert_classification")

        if lm is None:
            lm = get_llm_for_agent("spend_classification")

        dspy.configure(lm=lm)

        self.taxonomy_path = str(taxonomy_path) if taxonomy_path else None
        self._taxonomy_cache: Dict[str, Dict] = {}
        self._cache_lock = threading.Lock()
        self._current_taxonomy: List[str] = []

        # Invoice processing configuration
        self.invoice_config: InvoiceProcessingConfig = DEFAULT_CONFIG
        self.MAX_ROWS_PER_BATCH = self.invoice_config.max_rows_per_batch
        
        self.research_agent = None  # Research agent (for supplier research, not company domain context)
        self._company_context_cache: Dict[str, str] = {}  # Cache company domain context
        self._classifier = None  # ChainOfThought classifier instance
        self.db_manager = None  # Will be set by pipeline for classification caching
        self._taxonomy_retriever = TaxonomyRetriever()  # RAG component for taxonomy retrieval


    def load_taxonomy(self, taxonomy_path: Union[str, Path]) -> Dict:
        """Load taxonomy from YAML with caching."""
        path_str = str(taxonomy_path)
        
        # Check cache first (outside lock for performance)
        if path_str in self._taxonomy_cache:
            return self._taxonomy_cache[path_str]
        
        # Load file outside lock to avoid blocking
        with open(path_str, 'r') as f:
            data = yaml.safe_load(f)
        
        # Update cache inside lock with double-check
        with self._cache_lock:
            if path_str not in self._taxonomy_cache:
                self._taxonomy_cache[path_str] = data
        
        return self._taxonomy_cache[path_str]

    def _format_supplier_info(self, supplier_profile: Dict) -> str:
        if not supplier_profile:
            return "{}"
        relevant = {
            'name': supplier_profile.get('supplier_name', ''),
            'industry': supplier_profile.get('industry', ''),
            'products_services': supplier_profile.get('products_services', ''),
            'service_type': supplier_profile.get('service_type', ''),
            'description': (str(supplier_profile.get('description', '') or ''))[:300],
        }
        return json.dumps({k: v for k, v in relevant.items() if v}, indent=2)

    def _format_transaction_info(self, transaction_data: Dict) -> str:
        """Format transaction data, presenting all available signals clearly.
        
        No hardcoded priorities or pattern detection - presents raw data organized
        by field type. The LLM will identify patterns and decide what matters.
        """
        parts = []
        
        # Organize fields by type for clarity, but present all available data
        structured_fields = []
        description_fields = []
        reference_fields = []
        other_fields = []
        
        # Structured/contextual fields
        if is_valid_value(transaction_data.get('department')):
            structured_fields.append(('Department', transaction_data['department']))
        
        if is_valid_value(transaction_data.get('gl_code')):
            structured_fields.append(('GL Code', transaction_data['gl_code']))
        
        if is_valid_value(transaction_data.get('cost_center')):
            structured_fields.append(('Cost Center', transaction_data['cost_center']))
        
        if is_valid_value(transaction_data.get('amount')):
            try:
                amount_val = float(str(transaction_data['amount']).replace(',', ''))
                amount_str = f"${amount_val:,.2f}" if amount_val >= 1 else f"${amount_val:.2f}"
                structured_fields.append(('Amount', amount_str))
            except (ValueError, TypeError):
                structured_fields.append(('Amount', transaction_data['amount']))
        
        # Reference/identifier fields
        if is_valid_value(transaction_data.get('po_number')):
            reference_fields.append(('PO Number', transaction_data['po_number']))
        
        if is_valid_value(transaction_data.get('invoice_number')):
            reference_fields.append(('Invoice Number', transaction_data['invoice_number']))
        
        if is_valid_value(transaction_data.get('invoice_date')):
            reference_fields.append(('Invoice Date', transaction_data['invoice_date']))
        
        # Description fields (present raw - LLM identifies patterns)
        if is_valid_value(transaction_data.get('line_description')):
            description_fields.append(('Line Description', transaction_data['line_description']))
        
        if is_valid_value(transaction_data.get('gl_description')):
            description_fields.append(('GL Description', transaction_data['gl_description']))
        
        if is_valid_value(transaction_data.get('memo')):
            description_fields.append(('Memo', transaction_data['memo']))
        
        if is_valid_value(transaction_data.get('line_memo')):
            description_fields.append(('Line Memo', transaction_data['line_memo']))
        
        # Other fields
        excluded_fields = {'supplier_name', 'L1', 'L2', 'L3', 'L4', 'L5', 'classification_path', 
                          'pipeline_output', 'expected_output', 'error', 'reasoning',
                          'line_description', 'gl_description', 'memo', 'line_memo', 'department', 'gl_code', 
                          'invoice_number', 'po_number', 'invoice_date', 'amount', 'cost_center',
                          'currency', 'supplier_address'}
        for key, value in sorted(transaction_data.items()):
            if key not in excluded_fields and is_valid_value(value):
                other_fields.append((key.replace('_', ' ').title(), value))
        
        # Format sections
        if structured_fields:
            parts.append("Transaction Context:")
            for label, value in structured_fields:
                parts.append(f"  {label}: {value}")
        
        if description_fields:
            if parts:
                parts.append("")
            parts.append("Descriptions:")
            for label, value in description_fields:
                # Show full description - LLM will identify patterns
                display_value = str(value)
                if len(display_value) > 200:
                    display_value = display_value[:197] + "..."
                parts.append(f"  {label}: {display_value}")
        
        if reference_fields:
            if parts:
                parts.append("")
            parts.append("References:")
            for label, value in reference_fields:
                parts.append(f"  {label}: {value}")
        
        if other_fields:
            if parts:
                parts.append("")
            parts.append("Additional Information:")
            for label, value in other_fields:
                display_value = str(value)
                if len(display_value) > 150:
                    display_value = display_value[:147] + "..."
                parts.append(f"  {label}: {display_value}")
        
        # Add field completeness summary (contextual, not hardcoded patterns)
        if parts:
            field_counts = {
                'structured': len(structured_fields),
                'descriptions': len(description_fields),
                'references': len(reference_fields),
                'other': len(other_fields)
            }
            
            # Only show if there are fields available
            if any(field_counts.values()):
                parts.append("")
                available_info = []
                if field_counts['structured'] > 0:
                    available_info.append(f"{field_counts['structured']} structured field(s)")
                if field_counts['descriptions'] > 0:
                    available_info.append(f"{field_counts['descriptions']} description field(s)")
                if field_counts['references'] > 0:
                    available_info.append(f"{field_counts['references']} reference field(s)")
                if field_counts['other'] > 0:
                    available_info.append(f"{field_counts['other']} other field(s)")
                
                parts.append(f"Data Completeness: {', '.join(available_info)} available")
                parts.append("(Evaluate which fields provide the most relevant signals for this transaction)")
        
        return "\n".join(parts) if parts else "No transaction details available"

    def _format_invoice_info(self, invoice_transactions: List[Dict]) -> str:
        """
        Format invoice-level transaction data from multiple line items.

        Aggregates information across all rows in an invoice to provide
        comprehensive context while highlighting shared vs. varying fields.

        Args:
            invoice_transactions: List of transaction data dictionaries

        Returns:
            Formatted string with invoice-level view
        """
        if not invoice_transactions:
            return "No transaction details available"

        # If single row, use existing single-row formatting
        if len(invoice_transactions) == 1:
            return self._format_transaction_info(invoice_transactions[0])

        parts = []
        parts.append(f"Invoice contains {len(invoice_transactions)} line items:")
        parts.append("")

        # Shared/invoice-level fields (take from first row with valid value)
        shared_fields = []
        for field_name, label in [
            ('invoice_date', 'Invoice Date'),
            ('company', 'Company'),
            ('po_number', 'PO Number'),
            ('department', 'Department'),
            ('cost_center', 'Cost Center'),
        ]:
            value = None
            for txn in invoice_transactions:
                if is_valid_value(txn.get(field_name)):
                    value = txn[field_name]
                    break
            if value:
                shared_fields.append((label, value))

        if shared_fields:
            parts.append("Invoice-Level Context:")
            for label, value in shared_fields:
                parts.append(f"  {label}: {value}")
            parts.append("")

        # Aggregate amount
        total_amount = 0
        has_amount = False
        for txn in invoice_transactions:
            if is_valid_value(txn.get('amount')):
                try:
                    amount_val = float(str(txn['amount']).replace(',', ''))
                    total_amount += amount_val
                    has_amount = True
                except (ValueError, TypeError):
                    pass

        if has_amount:
            amount_str = f"${total_amount:,.2f}" if total_amount >= 1 else f"${total_amount:.2f}"
            parts.append(f"Total Invoice Amount: {amount_str}")
            parts.append("")

        # Line items (show descriptions and GL info)
        # Limit to MAX_ROWS_PER_BATCH (same as batch size)
        display_transactions = invoice_transactions[:self.MAX_ROWS_PER_BATCH]

        parts.append("Line Items:")
        for idx, txn in enumerate(display_transactions, 1):
            line_parts = [f"  Line {idx}:"]

            # Line description
            if is_valid_value(txn.get('line_description')):
                desc = str(txn['line_description'])
                if len(desc) > 150:
                    desc = desc[:147] + "..."
                line_parts.append(f"    Description: {desc}")

            # GL info
            if is_valid_value(txn.get('gl_description')):
                gl_desc = str(txn['gl_description'])
                if len(gl_desc) > 100:
                    gl_desc = gl_desc[:97] + "..."
                line_parts.append(f"    GL: {gl_desc}")

            if is_valid_value(txn.get('gl_code')):
                line_parts.append(f"    GL Code: {txn['gl_code']}")

            # Amount
            if is_valid_value(txn.get('amount')):
                try:
                    amt = float(str(txn['amount']).replace(',', ''))
                    amt_str = f"${amt:,.2f}" if amt >= 1 else f"${amt:.2f}"
                    line_parts.append(f"    Amount: {amt_str}")
                except (ValueError, TypeError):
                    pass

            parts.append("\n".join(line_parts))

        # Note if invoice was truncated (batch has more rows than display limit)
        if len(invoice_transactions) > self.MAX_ROWS_PER_BATCH:
            parts.append(f"  ... and {len(invoice_transactions) - self.MAX_ROWS_PER_BATCH} more line items")
            parts.append(f"\nNOTE: Invoice has {len(invoice_transactions)} total line items. "
                        f"Showing first {self.MAX_ROWS_PER_BATCH} for classification context. "
                        f"All {len(invoice_transactions)} items will be classified.")

        parts.append("")
        parts.append("(All line items will be classified individually based on shared invoice context)")

        return "\n".join(parts)

    def _get_relevant_taxonomy_paths(
        self, 
        transaction_data: Dict, 
        supplier_profile: Dict, 
        taxonomy_list: List[str],
        descriptions: Optional[Dict[str, str]] = None
    ) -> Tuple[Dict[str, List[str]], Dict[str, float]]:
        """
        Use RAG component (FAISS + hybrid search) to find relevant taxonomy paths.
        
        Uses the TaxonomyRetriever with:
        - Keyword similarity (fast, exact matches)
        - Semantic similarity via FAISS (flexible, contextual matches)
        - Includes all transaction fields (including GL/Line descriptions)
        - Increased sample size for better context
        
        Args:
            transaction_data: Transaction data dictionary
            supplier_profile: Supplier profile dictionary
            taxonomy_list: List of taxonomy paths
            descriptions: Optional dictionary mapping taxonomy paths to descriptions
            
        Returns:
            Tuple of:
            - Dictionary mapping L1 category to list of paths within that L1
            - Dictionary mapping path to similarity score (0-1)
        """
        # Use the new RAG component for hybrid search with increased sample size
        grouped_paths = self._taxonomy_retriever.retrieve_grouped_by_l1(
            transaction_data=transaction_data,
            supplier_profile=supplier_profile,
            taxonomy_list=taxonomy_list,
            max_l1_categories=6,      # Increased from 5
            max_paths_per_l1=10,      # Increased from 8
            max_total_paths=60,        # Increased from 35 to 50-60 range
            descriptions=descriptions
        )
        
        # Get individual path scores for all retrieved paths
        all_results = self._taxonomy_retriever.retrieve_with_scores(
            transaction_data=transaction_data,
            supplier_profile=supplier_profile,
            taxonomy_list=taxonomy_list,
            top_k=60,  # Get more for score extraction (increased from 50)
            min_score=0.05,  # Lower threshold to get more results
            descriptions=descriptions
        )
        
        # Build scores dictionary
        scores_dict = {r.path: r.combined_score for r in all_results}
        
        return grouped_paths, scores_dict
    
    def _format_taxonomy_sample_by_l1(
        self, 
        l1_grouped_paths: Dict[str, List[str]],
        similarity_scores: Optional[Dict[str, float]] = None,
        descriptions: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Format taxonomy paths sorted by depth (deepest first) to encourage bottom-up matching.
        Optionally includes similarity scores from RAG retrieval (contextual signal, not hardcoded).
        Optionally includes descriptions for richer context.
        
        Args:
            l1_grouped_paths: Dictionary mapping L1 category to list of paths
            similarity_scores: Optional dictionary mapping path to similarity score (0-1)
            descriptions: Optional dictionary mapping taxonomy paths to descriptions
            
        Returns:
            Formatted string with paths sorted by depth (deepest first)
        """
        if not l1_grouped_paths:
            return "No relevant paths found."
        
        # Flatten the grouped paths into a simple list
        flat_paths = []
        for paths in l1_grouped_paths.values():
            flat_paths.extend(paths)
        
        # Sort by depth descending (most specific/deepest paths first) for bottom-up matching
        # If scores available, also sort by score (higher first)
        if similarity_scores:
            flat_paths.sort(key=lambda p: (
                -len(p.split("|")),  # Depth first (deeper = more specific)
                -similarity_scores.get(p, 0.0),  # Then by similarity score
                p  # Then alphabetically
            ))
        else:
            flat_paths.sort(key=lambda p: (-len(p.split("|")), p))
        
        # Format paths with scores if available, and descriptions if provided
        formatted_lines = ["Relevant taxonomy paths (deepest/most specific paths first - match these end nodes first):"]
        for path in flat_paths:
            depth = len(path.split("|"))
            line_parts = []
            
            # Add score if available
            if similarity_scores and path in similarity_scores:
                score = similarity_scores[path]
                line_parts.append(f"L{depth} [{score:.2f}]: {path}")
            else:
                line_parts.append(f"L{depth}: {path}")
            
            # Add description if available (truncated for readability)
            if descriptions and path in descriptions:
                desc = descriptions[path].strip()
                # Truncate long descriptions
                if len(desc) > 200:
                    desc = desc[:197] + "..."
                line_parts.append(f"  Description: {desc}")
            
            formatted_lines.append("\n".join(line_parts))
        
        if similarity_scores:
            formatted_lines.append("\n(Similarity scores indicate RAG retrieval confidence - use as one signal among many when making your classification decision.)")
        
        return "\n".join(formatted_lines)
    
    def _extract_domain_context(
        self, 
        taxonomy_path: str, 
        dataset_name: Optional[str] = None
    ) -> str:
        """
        Extract company domain context from taxonomy YAML file.
        Reads company_context field from taxonomy if available, otherwise falls back to company name.
        """
        cache_key = f"{taxonomy_path}|{dataset_name}"
        if cache_key in self._company_context_cache:
            return self._company_context_cache[cache_key]
        
        context_parts = []
        
        # Try to load company context from taxonomy YAML file
        try:
            taxonomy_data = self.load_taxonomy(taxonomy_path)
            
            # Check for company_context field in taxonomy
            company_context = taxonomy_data.get('company_context')
            if company_context:
                # Support both string and dict formats
                if isinstance(company_context, str):
                    context_parts.append(company_context)
                elif isinstance(company_context, dict):
                    # Format dict fields into readable context
                    if company_context.get('industry'):
                        context_parts.append(f"Company Industry: {company_context['industry']}")
                    if company_context.get('description'):
                        desc = str(company_context['description'])
                        context_parts.append(f"Company Description: {desc[:300]}")
                    if company_context.get('sector'):
                        context_parts.append(f"Company Sector: {company_context['sector']}")
                    if company_context.get('business_focus'):
                        context_parts.append(f"Business Focus: {company_context['business_focus']}")
            
            # Also include client_name from taxonomy if available
            client_name = taxonomy_data.get('client_name')
            if client_name and not company_context:
                context_parts.append(f"Company Name: {client_name}")
        except Exception as e:
            logger.debug(f"Could not load company context from taxonomy: {e}")
        
        # Fallback: Extract company name from taxonomy filename if no context found
        if not context_parts:
            taxonomy_filename = str(taxonomy_path).split('/')[-1] if '/' in str(taxonomy_path) else str(taxonomy_path)
            company_name = taxonomy_filename.split('_')[0] if '_' in taxonomy_filename else taxonomy_filename.replace('.yaml', '').replace('.YAML', '')
            if company_name and company_name.lower() not in ['taxonomy', 'taxonomies']:
                context_parts.append(f"Company Name: {company_name}")
        
        # Add dataset name if provided
        if dataset_name:
            context_parts.append(f"Dataset: {dataset_name}")
        
        result = " | ".join(context_parts) if context_parts else "General business context"
        
        # Cache result
        self._company_context_cache[cache_key] = result
        return result
    
    def classify_transaction(
        self,
        supplier_profile: Dict,
        transaction_data: Dict,
        taxonomy_yaml: Optional[str] = None,
        prioritization_decision: Optional[PrioritizationDecision] = None,
        dataset_name: Optional[str] = None,
        taxonomy_constraint_paths: Optional[List[str]] = None,
    ) -> ClassificationResult:
        """Classify a transaction using ChainOfThought (single-shot) with semantic pre-search."""
        taxonomy_source = taxonomy_yaml or self.taxonomy_path
        if taxonomy_source is None:
            raise ValueError("Taxonomy path must be provided")

        taxonomy_data = self.load_taxonomy(taxonomy_source)
        taxonomy_list = taxonomy_data.get('taxonomy', [])
        descriptions = taxonomy_data.get('taxonomy_descriptions', {})  # Extract descriptions
        self._current_taxonomy = taxonomy_list

        supplier_info = self._format_supplier_info(supplier_profile)
        transaction_info = self._format_transaction_info(transaction_data)
        
        # Use taxonomy constraint if provided, otherwise use RAG
        if taxonomy_constraint_paths:
            # Use constraint paths instead of RAG
            logger.debug(f"Using taxonomy constraint: {len(taxonomy_constraint_paths)} paths")
            # Group constraint paths by L1
            l1_grouped_paths = {}
            for path in taxonomy_constraint_paths:
                l1 = path.split('|')[0] if '|' in path else path
                if l1 not in l1_grouped_paths:
                    l1_grouped_paths[l1] = []
                if path not in l1_grouped_paths[l1]:
                    l1_grouped_paths[l1].append(path)
            # No similarity scores for constraint paths (all equally valid)
            similarity_scores = {}
        else:
            # Use semantic search to find top relevant paths, grouped by L1, with similarity scores
            l1_grouped_paths, similarity_scores = self._get_relevant_taxonomy_paths(
                transaction_data, 
                supplier_profile, 
                taxonomy_list,
                descriptions=descriptions
            )
        
        # Format taxonomy paths organized by L1 for better LLM reasoning, with similarity scores
        taxonomy_sample = self._format_taxonomy_sample_by_l1(
            l1_grouped_paths, 
            similarity_scores,
            descriptions=descriptions
        )
        
        # Also create flat list for pre-search tracking
        flat_paths = []
        for paths in l1_grouped_paths.values():
            flat_paths.extend(paths)
        
        prioritization = prioritization_decision.prioritization_strategy if prioritization_decision else "balanced"
        domain_context = self._extract_domain_context(
            taxonomy_yaml or self.taxonomy_path, 
            dataset_name
        )

        # Use ChainOfThought for single-shot classification (reduces API calls and avoids rate limits)
        if self._classifier is None:
            self._classifier = dspy.ChainOfThought(SpendClassificationSignature)

        try:
            result = self._classifier(
                supplier_info=supplier_info,
                transaction_info=transaction_info,
                taxonomy_sample=taxonomy_sample,
                prioritization=prioritization,
                domain_context=domain_context,
            )
            classification_path = str(result.classification_path or '').strip()
            confidence = str(getattr(result, 'confidence', 'medium') or 'medium').lower()
            reasoning = str(getattr(result, 'reasoning', '') or '')
            
            # Track pre-search performance: log if classification path was NOT in pre-searched paths
            # This helps us understand if pre-search is missing correct paths
            if classification_path and classification_path != "Unknown":
                path_normalized = classification_path.strip().lower()
                preselected_normalized = [p.strip().lower() for p in flat_paths]
                if path_normalized not in preselected_normalized:
                    logger.debug(
                        f"Pre-search miss: Final path '{classification_path}' was NOT in pre-searched paths "
                        f"(found {len(flat_paths)} pre-searched paths)"
                    )
                else:
                    logger.debug(
                        f"Pre-search hit: Final path '{classification_path}' was in pre-searched paths"
                    )
        except Exception as e:
            logger.error(f"Classification failed: {e}", exc_info=True)
            classification_path = "Unknown"
            confidence = "low"
            reasoning = f"Classification failed: {e}"

        # Post-validate the classification path
        validation_result = validate_path(classification_path, taxonomy_list)
        
        if not validation_result.get('valid', False):
            # Path doesn't exist, try to find similar paths
            similar_paths = validation_result.get('similar_paths', [])
            if similar_paths:
                # Use the most similar valid path
                classification_path = similar_paths[0]
                reasoning += f" [Corrected to valid path: {classification_path}]"
                logger.debug(f"Invalid path corrected: {classification_path}")
            else:
                # Fallback: use semantic search with strong signals first
                query_parts = []
                if is_valid_value(transaction_data.get('department')):
                    query_parts.append(str(transaction_data['department']))
                if is_valid_value(transaction_data.get('gl_code')):
                    query_parts.append(str(transaction_data['gl_code']))
                if supplier_profile:
                    if supplier_profile.get('products_services'):
                        query_parts.append(str(supplier_profile['products_services']))
                    if supplier_profile.get('service_type'):
                        query_parts.append(str(supplier_profile['service_type']))
                # Weak signals last
                if not query_parts:
                    if is_valid_value(transaction_data.get('line_description')):
                        query_parts.append(str(transaction_data['line_description']))
                    if is_valid_value(transaction_data.get('gl_description')):
                        query_parts.append(str(transaction_data['gl_description']))
                
                if query_parts:
                    query = " ".join(query_parts[:2])  # Use top 2 parts
                    matches = lookup_paths(str(query), taxonomy_list)
                    if matches:
                        classification_path = matches[0]
                        reasoning += f" [Found via semantic search: {classification_path}]"
                        logger.debug(f"Path found via semantic search: {classification_path}")

        # Validate minimum depth - if only L1 returned, try to find a deeper path
        if classification_path and "|" not in classification_path and classification_path != "Unknown":
            logger.warning(f"Only L1 returned: {classification_path}. Attempting to find deeper path.")
            # Search for paths starting with this L1
            l1_paths = [p for p in taxonomy_list if p.lower().startswith(classification_path.lower() + "|")]
            if l1_paths:
                # Try to find most relevant deeper path using semantic search with strong signals
                query_parts = []
                if is_valid_value(transaction_data.get('department')):
                    query_parts.append(str(transaction_data['department']))
                if is_valid_value(transaction_data.get('gl_code')):
                    query_parts.append(str(transaction_data['gl_code']))
                if supplier_profile:
                    if supplier_profile.get('products_services'):
                        query_parts.append(str(supplier_profile['products_services']))
                # Weak signals as fallback
                if not query_parts:
                    if is_valid_value(transaction_data.get('line_description')):
                        query_parts.append(str(transaction_data['line_description']))
                    if is_valid_value(transaction_data.get('gl_description')):
                        query_parts.append(str(transaction_data['gl_description']))
                
                if query_parts:
                    query = " ".join(query_parts[:2])
                    matches = lookup_paths(str(query), l1_paths)
                    if matches:
                        classification_path = matches[0]
                        reasoning += f" [Auto-expanded from L1 to: {classification_path}]"
                    else:
                        # Fallback to first deeper path
                        classification_path = l1_paths[0]
                        reasoning += f" [Auto-expanded from L1 to: {classification_path}]"
                else:
                    # Fallback to first deeper path if no query available
                    classification_path = l1_paths[0]
                    reasoning += f" [Auto-expanded from L1 to: {classification_path}]"

        return self._path_to_result(classification_path, confidence, reasoning)

    def _path_to_result(self, path: str, confidence: str, reasoning: str) -> ClassificationResult:
        """Convert pipe-separated path to ClassificationResult."""
        parts = [p.strip() for p in path.split("|") if p.strip()]
        while len(parts) < 5:
            parts.append(None)
        
        return ClassificationResult(
            L1=parts[0] or "Unknown",
            L2=parts[1] if len(parts) > 1 else None,
            L3=parts[2] if len(parts) > 2 else None,
            L4=parts[3] if len(parts) > 3 else None,
            L5=parts[4] if len(parts) > 4 else None,
            override_rule_applied=None,
            reasoning=f"[{confidence}] {reasoning}",
        )

    def _parse_multi_classification_response(
        self,
        response: str,
        expected_count: int,
        already_classified: List[str] = None
    ) -> Tuple[List[str], List[Dict]]:
        """
        Parse JSON list response from LLM for multi-row classification.

        Args:
            response: LLM response (expected to be JSON list)
            expected_count: Number of classifications expected
            already_classified: List of successfully classified paths so far (for fallback)

        Returns:
            Tuple of (classification_paths, errors)
            - classification_paths: List of classification paths (one per row)
            - errors: List of error dictionaries with details

        Two-Tier Fallback Strategy:
        1. First fallback: Use majority classification from already_classified rows
        2. Second fallback: Use "Unknown" if no already_classified or no majority
        """
        import json
        from collections import Counter

        errors = []
        fallback = self._get_fallback_classification(already_classified)

        # Check if response is a single path (not JSON list)
        single_path_result = self._parse_single_path_response(response, expected_count, fallback)
        if single_path_result:
            paths, parse_errors = single_path_result
            errors.extend(parse_errors)
            return paths, errors

        # Try to parse as JSON list
        json_result = self._parse_json_list_response(response, expected_count, fallback, already_classified)
        if json_result:
            paths, parse_errors = json_result
            errors.extend(parse_errors)
            return paths, errors

        # Complete failure - use fallback
        errors.append({
            'error_type': 'PARSE_FAILED',
            'message': 'Failed to parse response as single path or JSON list',
            'fallback_used': fallback,
            'raw_response': response[:500]
        })
        return [fallback] * expected_count, errors
    
    def _parse_single_path_response(
        self,
        response: str,
        expected_count: int,
        fallback: str
    ) -> Optional[Tuple[List[str], List[Dict]]]:
        """
        Parse response as single classification path (not JSON).

        Args:
            response: LLM response
            expected_count: Expected number of classifications
            fallback: Fallback path to use

        Returns:
            Tuple of (paths, errors) if parsed as single path, None otherwise
        """
        if not response or response.strip().startswith('['):
            return None
        
        # Looks like a single classification path
        if '|' in response:  # Valid taxonomy path format
            logger.debug(f"LLM returned single path for {expected_count} rows: {response[:100]}")
            return [response.strip()] * expected_count, []
        
        # Invalid single path
        return (
            [fallback] * expected_count,
            [{
                'error_type': 'INVALID_SINGLE_PATH',
                'message': f'Response is not a valid taxonomy path: {response[:100]}',
                'fallback_used': fallback,
                'raw_response': response[:500]
            }]
        )
    
    def _parse_json_list_response(
        self,
        response: str,
        expected_count: int,
        fallback: str,
        already_classified: List[str] = None
    ) -> Optional[Tuple[List[str], List[Dict]]]:
        """
        Parse response as JSON list.

        Args:
            response: LLM response
            expected_count: Expected number of classifications
            fallback: Fallback path to use
            already_classified: Already classified paths for recursive parsing

        Returns:
            Tuple of (paths, errors) if parsed as JSON, None otherwise
        """
        import json
        import re

        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract list from response using regex
            list_pattern = r'\[([^\]]+)\]'
            match = re.search(list_pattern, response)
            if match:
                try:
                    list_str = match.group(0)
                    parsed = json.loads(list_str)
                except:
                    return None
            else:
                return None

        if not isinstance(parsed, list):
            return (
                [fallback] * expected_count,
                [{
                    'error_type': 'JSON_PARSE_FAILED',
                    'message': f'Expected JSON list, got {type(parsed).__name__}',
                    'fallback_used': fallback,
                    'raw_response': response[:500]
                }]
            )

        # Valid list - check length
        if len(parsed) == expected_count:
            return [str(p) for p in parsed], []
        elif len(parsed) < expected_count:
            missing_count = expected_count - len(parsed)
            result = [str(p) for p in parsed] + [fallback] * missing_count
            return (
                result,
                [{
                    'error_type': 'PARTIAL_RESPONSE',
                    'message': f'Expected {expected_count} classifications, got {len(parsed)}',
                    'missing_count': missing_count,
                    'fallback_used': fallback,
                    'missing_indices': list(range(len(parsed), expected_count))
                }]
            )
        else:
            # Too many - truncate
            result = [str(p) for p in parsed[:expected_count]]
            return (
                result,
                [{
                    'error_type': 'RESPONSE_TOO_LONG',
                    'message': f'Expected {expected_count} classifications, got {len(parsed)}. Truncated.',
                    'extra_count': len(parsed) - expected_count
                }]
            )

    def classify_with_tools(self, *args, **kwargs) -> ClassificationResult:
        """Alias for classify_transaction (backward compat)."""
        return self.classify_transaction(*args, **kwargs)

    def classify_invoice(
        self,
        supplier_profile: Dict,
        invoice_transactions: List[Dict],
        taxonomy_yaml: Optional[str] = None,
        prioritization_decision: Optional[PrioritizationDecision] = None,
        dataset_name: Optional[str] = None,
        taxonomy_constraint_paths: Optional[List[str]] = None,
    ) -> List[ClassificationResult]:
        """
        Classify all transactions in an invoice together using batch processing.

        For multi-row invoices, sends ALL rows to LLM in ONE call (or batches of MAX_ROWS_PER_BATCH).
        Returns one classification per transaction row.

        Args:
            supplier_profile: Supplier profile dictionary
            invoice_transactions: List of transaction data dictionaries (all rows in invoice)
            taxonomy_yaml: Path to taxonomy YAML file
            prioritization_decision: Pre-computed prioritization decision
            dataset_name: Optional dataset name

        Returns:
            List of ClassificationResult objects (one per transaction row)
        """
        if not invoice_transactions:
            return []

        # For single-row invoices, use existing logic
        if len(invoice_transactions) == 1:
            result = self.classify_transaction(
                supplier_profile=supplier_profile,
                transaction_data=invoice_transactions[0],
                taxonomy_yaml=taxonomy_yaml,
                prioritization_decision=prioritization_decision,
                dataset_name=dataset_name,
                taxonomy_constraint_paths=taxonomy_constraint_paths,
            )
            return [result]

        # Multi-row invoice: batch processing
        taxonomy_source = taxonomy_yaml or self.taxonomy_path
        if taxonomy_source is None:
            raise ValueError("Taxonomy path must be provided")

        taxonomy_data = self.load_taxonomy(taxonomy_source)
        taxonomy_list = taxonomy_data.get('taxonomy', [])
        descriptions = taxonomy_data.get('taxonomy_descriptions', {})
        self._current_taxonomy = taxonomy_list

        supplier_info = self._format_supplier_info(supplier_profile)

        # Aggregate transaction data for RAG search from ALL rows
        aggregated_data = {}

        # Structured fields: First valid value
        for field in ['department', 'gl_code', 'cost_center', 'po_number']:
            for txn in invoice_transactions:
                if is_valid_value(txn.get(field)):
                    aggregated_data[field] = txn[field]
                    break

        # Line descriptions: Deduplicate and take up to configured limit
        line_descriptions = []
        for txn in invoice_transactions:
            if is_valid_value(txn.get('line_description')):
                desc = str(txn['line_description']).strip()
                if desc and desc not in line_descriptions:
                    line_descriptions.append(desc)
                    if len(line_descriptions) >= self.invoice_config.max_line_descriptions:
                        break
        if line_descriptions:
            aggregated_data['line_description'] = ' | '.join(line_descriptions)

        # GL descriptions: Deduplicate and take up to configured limit
        gl_descriptions = []
        for txn in invoice_transactions:
            if is_valid_value(txn.get('gl_description')):
                gl_desc = str(txn['gl_description']).strip()
                if gl_desc and gl_desc not in gl_descriptions:
                    gl_descriptions.append(gl_desc)
                    if len(gl_descriptions) >= self.invoice_config.max_gl_descriptions:
                        break
        if gl_descriptions:
            aggregated_data['gl_description'] = ' | '.join(gl_descriptions)

        # Get invoice-level taxonomy paths using constraint or RAG
        if taxonomy_constraint_paths:
            # Use constraint paths instead of RAG
            logger.debug(f"Using taxonomy constraint for invoice: {len(taxonomy_constraint_paths)} paths")
            # Group constraint paths by L1
            l1_grouped_paths = {}
            for path in taxonomy_constraint_paths:
                l1 = path.split('|')[0] if '|' in path else path
                if l1 not in l1_grouped_paths:
                    l1_grouped_paths[l1] = []
                if path not in l1_grouped_paths[l1]:
                    l1_grouped_paths[l1].append(path)
            # No similarity scores for constraint paths
            similarity_scores = {}
        else:
            # Get invoice-level taxonomy paths using aggregated data
            l1_grouped_paths, similarity_scores = self._get_relevant_taxonomy_paths(
                aggregated_data,
                supplier_profile,
                taxonomy_list,
                descriptions=descriptions
            )

        taxonomy_sample = self._format_taxonomy_sample_by_l1(
            l1_grouped_paths,
            similarity_scores,
            descriptions=descriptions
        )

        prioritization = prioritization_decision.prioritization_strategy if prioritization_decision else "balanced"
        domain_context = self._extract_domain_context(
            taxonomy_yaml or self.taxonomy_path,
            dataset_name
        )

        # Split into batches for processing
        results = []
        all_classification_paths = []  # Track all successful classifications for fallback

        for batch_idx in range(0, len(invoice_transactions), self.MAX_ROWS_PER_BATCH):
            batch_transactions = invoice_transactions[batch_idx:batch_idx + self.MAX_ROWS_PER_BATCH]
            batch_size = len(batch_transactions)

            # Format all rows in batch using _format_invoice_info
            invoice_info = self._format_invoice_info(batch_transactions)

            # Use ChainOfThought for classification
            if self._classifier is None:
                self._classifier = dspy.ChainOfThought(SpendClassificationSignature)

            try:
                # Call LLM ONCE for entire batch with retry logic
                result = self._classify_batch_with_retry(
                    supplier_info=supplier_info,
                    transaction_info=invoice_info,
                    taxonomy_sample=taxonomy_sample,
                    prioritization=prioritization,
                    domain_context=domain_context,
                )

                # Get the classification response
                classification_response = str(result.classification_path or '').strip()
                confidence = str(getattr(result, 'confidence', 'medium') or 'medium').lower()
                reasoning_base = str(getattr(result, 'reasoning', '') or '')

                # Parse JSON list response
                classification_paths, parse_errors = self._parse_multi_classification_response(
                    classification_response,
                    expected_count=batch_size,
                    already_classified=all_classification_paths
                )

                # Log any parsing errors with raw response
                for error in parse_errors:
                    error_msg = f"Batch {batch_idx//self.MAX_ROWS_PER_BATCH + 1} - {error['error_type']}: {error['message']}"
                    if 'raw_response' in error:
                        error_msg += f"\nRaw response (first 200 chars): {error['raw_response'][:200]}"
                    logger.warning(error_msg)

            except Exception as e:
                # LLM call failed - use fallback for all rows in batch
                logger.error(f"Classification failed for batch {batch_idx//self.MAX_ROWS_PER_BATCH + 1}: {e}", exc_info=True)

                # Apply two-tier fallback
                fallback_path = self._get_fallback_classification(all_classification_paths)
                classification_paths = [fallback_path] * batch_size
                confidence = "low"
                reasoning_base = f"LLM call failed: {e}"

                logger.error(
                    f"Batch {batch_idx//self.MAX_ROWS_PER_BATCH + 1} - LLM_CALL_FAILED: Using fallback '{fallback_path}' for {batch_size} rows"
                )

            # Process each classification in the batch
            for transaction_data, classification_path in zip(batch_transactions, classification_paths):
                reasoning = reasoning_base + " [Invoice-level batch processing]"

                # Post-validate and correct classification path
                classification_path, reasoning = self._validate_and_correct_path(
                    classification_path,
                    taxonomy_list,
                    l1_grouped_paths,
                    similarity_scores,
                    transaction_data,
                    reasoning
                )

                # Track successful classification for future fallback
                if classification_path != "Unknown":
                    all_classification_paths.append(classification_path)

                result_obj = self._path_to_result(classification_path, confidence, reasoning)
                results.append(result_obj)

        return results

    def _get_fallback_classification(self, already_classified: List[str]) -> str:
        """
        Get fallback classification using two-tier strategy.

        Args:
            already_classified: List of successfully classified paths

        Returns:
            Fallback classification path
        """
        from collections import Counter

        if already_classified:
            # Find majority classification
            counter = Counter(already_classified)
            majority = counter.most_common(1)[0]
            if majority[1] > 1 or len(counter) == 1:  # Clear majority or only one unique value
                return majority[0]
        # Second fallback
        return "Unknown"
    
    def _validate_and_correct_path(
        self,
        classification_path: str,
        taxonomy_list: List[str],
        l1_grouped_paths: Optional[Dict[str, List[str]]],
        similarity_scores: Optional[Dict[str, float]],
        transaction_data: Dict,
        reasoning: str
    ) -> Tuple[str, str]:
        """
        Validate and correct classification path.

        Args:
            classification_path: Original classification path
            taxonomy_list: List of valid taxonomy paths
            l1_grouped_paths: Optional grouped paths from pre-search
            similarity_scores: Optional similarity scores
            transaction_data: Transaction data for expansion
            reasoning: Current reasoning string

        Returns:
            Tuple of (corrected_path, updated_reasoning)
        """
        # Post-validate the classification path
        validation_result = validate_path(classification_path, taxonomy_list)

        if not validation_result.get('valid', False):
            similar_paths = validation_result.get('similar_paths', [])
            if similar_paths:
                classification_path = similar_paths[0]
                reasoning += f" [Corrected to valid path: {classification_path}]"
            else:
                # Fallback to most similar path from pre-search
                classification_path, reasoning = self._fallback_to_presearched(
                    classification_path,
                    l1_grouped_paths,
                    similarity_scores,
                    reasoning
                )

        # Validate minimum depth (expand L1-only results)
        if classification_path and "|" not in classification_path and classification_path != "Unknown":
            classification_path, reasoning = self._expand_l1_path(
                classification_path,
                taxonomy_list,
                transaction_data,
                reasoning
            )

        return classification_path, reasoning
    
    def _fallback_to_presearched(
        self,
        classification_path: str,
        l1_grouped_paths: Optional[Dict[str, List[str]]],
        similarity_scores: Optional[Dict[str, float]],
        reasoning: str
    ) -> Tuple[str, str]:
        """
        Fallback to pre-searched paths when validation fails.

        Args:
            classification_path: Original path
            l1_grouped_paths: Grouped paths from pre-search
            similarity_scores: Similarity scores
            reasoning: Current reasoning

        Returns:
            Tuple of (fallback_path, updated_reasoning)
        """
        if l1_grouped_paths:
            all_presearched = []
            for paths in l1_grouped_paths.values():
                all_presearched.extend(paths)

            if all_presearched:
                best_path = max(all_presearched, key=lambda p: similarity_scores.get(p, 0) if similarity_scores else 0)
                classification_path = best_path
                reasoning += f" [Invalid path corrected using pre-search results: {classification_path}]"
            else:
                classification_path = "Unknown"
                reasoning += " [Invalid path, no similar paths found]"
        else:
            classification_path = "Unknown"
            reasoning += " [Invalid path, no similar paths found]"
        
        return classification_path, reasoning
    
    def _expand_l1_path(
        self,
        classification_path: str,
        taxonomy_list: List[str],
        transaction_data: Dict,
        reasoning: str
    ) -> Tuple[str, str]:
        """
        Expand L1-only classification to deeper path.

        Args:
            classification_path: L1-only path
            taxonomy_list: List of valid taxonomy paths
            transaction_data: Transaction data for semantic search
            reasoning: Current reasoning

        Returns:
            Tuple of (expanded_path, updated_reasoning)
        """
        l1_category = classification_path
        l1_paths = [p for p in taxonomy_list if p.startswith(l1_category + "|")]

        if l1_paths:
            query_parts = []
            if is_valid_value(transaction_data.get('line_description')):
                query_parts.append(str(transaction_data['line_description']))
            if is_valid_value(transaction_data.get('gl_description')):
                query_parts.append(str(transaction_data['gl_description']))

            if query_parts:
                query = " ".join(query_parts[:2])
                matches = lookup_paths(str(query), l1_paths)
                if matches:
                    classification_path = matches[0]
                    reasoning += f" [Auto-expanded from L1 to: {classification_path}]"
                else:
                    classification_path = l1_paths[0]
                    reasoning += f" [Auto-expanded from L1 to: {classification_path}]"
            else:
                classification_path = l1_paths[0]
                reasoning += f" [Auto-expanded from L1 to: {classification_path}]"
        
        return classification_path, reasoning
    
    @retry_with_backoff(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
    def _classify_batch_with_retry(
        self,
        supplier_info: str,
        transaction_info: str,
        taxonomy_sample: str,
        prioritization: str,
        domain_context: str,
    ):
        """
        Classify batch with retry logic.

        Args:
            supplier_info: Formatted supplier information
            transaction_info: Formatted transaction information
            taxonomy_sample: Formatted taxonomy sample
            prioritization: Prioritization strategy
            domain_context: Domain context

        Returns:
            Classification result from LLM
        """
        if self._classifier is None:
            self._classifier = dspy.ChainOfThought(SpendClassificationSignature)
        
        return self._classifier(
            supplier_info=supplier_info,
            transaction_info=transaction_info,
            taxonomy_sample=taxonomy_sample,
            prioritization=prioritization,
            domain_context=domain_context,
        )
