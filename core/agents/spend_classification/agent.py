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
from core.agents.spend_classification.tools import validate_path, lookup_paths, get_l1_categories
from core.agents.taxonomy_rag import TaxonomyRetriever
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.utils.transaction_utils import is_valid_value

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
        self.research_agent = None  # Research agent (for supplier research, not company domain context)
        self._company_context_cache: Dict[str, str] = {}  # Cache company domain context
        self._classifier = None  # ChainOfThought classifier instance
        self.db_manager = None  # Will be set by pipeline for BootstrapFewShot examples
        self._max_examples = 2  # Maximum number of examples to include (conservative to minimize tokens)
        self._enable_examples = True  # Enabled - improves accuracy
        self._taxonomy_retriever = TaxonomyRetriever()  # RAG component for taxonomy retrieval


    def load_taxonomy(self, taxonomy_path: Union[str, Path]) -> Dict:
        """Load taxonomy from YAML with caching."""
        path_str = str(taxonomy_path)
        with self._cache_lock:
            if path_str not in self._taxonomy_cache:
                with open(path_str, 'r') as f:
                    self._taxonomy_cache[path_str] = yaml.safe_load(f)
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
        
        # Other fields
        excluded_fields = {'supplier_name', 'L1', 'L2', 'L3', 'L4', 'L5', 'classification_path', 
                          'pipeline_output', 'expected_output', 'error', 'reasoning',
                          'line_description', 'gl_description', 'department', 'gl_code', 
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
    
    def _find_similar_successful_examples(
        self, 
        transaction_data: Dict, 
        supplier_profile: Dict,
        taxonomy_path: Optional[str] = None,
        dataset_name: Optional[str] = None,
        limit: int = 3
    ) -> List[Dict]:
        """
        Find similar successful classification examples using semantic search.
        
        Args:
            transaction_data: Current transaction data
            supplier_profile: Current supplier profile
            taxonomy_path: Optional taxonomy path (for filtering)
            dataset_name: Optional dataset name (for filtering)
            limit: Maximum number of examples to return
            
        Returns:
            List of similar successful examples with their classification paths
        """
        # Need db_manager to get successful examples
        # This will be set by the pipeline
        if not hasattr(self, 'db_manager') or self.db_manager is None:
            return []
        
        try:
            # Get all successful examples from database
            successful_examples = self.db_manager.get_successful_examples(
                taxonomy_path=taxonomy_path,
                dataset_name=dataset_name,
                min_confidence='high',
                min_usage_count=2,
                limit=100  # Get more candidates, then filter by similarity
            )
            
            if not successful_examples:
                return []
            
            # Build query text from current transaction - prioritize STRONG signals
            query_parts = []
            
            # STRONG SIGNALS FIRST
            if supplier_profile:
                if supplier_profile.get('products_services'):
                    query_parts.append(str(supplier_profile['products_services']))
                if supplier_profile.get('service_type'):
                    query_parts.append(str(supplier_profile['service_type']))
            
            if is_valid_value(transaction_data.get('department')):
                query_parts.append(str(transaction_data['department']))
            
            if is_valid_value(transaction_data.get('gl_code')):
                query_parts.append(str(transaction_data['gl_code']))
            
            # WEAK SIGNALS LAST (only if needed)
            if len(query_parts) < 2:
                if is_valid_value(transaction_data.get('line_description')):
                    query_parts.append(str(transaction_data['line_description']))
                if is_valid_value(transaction_data.get('gl_description')):
                    query_parts.append(str(transaction_data['gl_description']))
            
            if not query_parts:
                return []
            
            query_text = " ".join(query_parts[:3])  # Use top 3 parts
            
            # Build texts from example transactions for semantic search
            example_texts = []
            for example in successful_examples:
                example_parts = []
                ex_trans = example.get('transaction_data', {})
                ex_supplier = example.get('supplier_profile', {})
                
                # STRONG SIGNALS FIRST
                if ex_supplier:
                    if ex_supplier.get('products_services'):
                        example_parts.append(str(ex_supplier['products_services']))
                    if ex_supplier.get('service_type'):
                        example_parts.append(str(ex_supplier['service_type']))
                
                if is_valid_value(ex_trans.get('department')):
                    example_parts.append(str(ex_trans['department']))
                
                if is_valid_value(ex_trans.get('gl_code')):
                    example_parts.append(str(ex_trans['gl_code']))
                
                # WEAK SIGNALS LAST
                if is_valid_value(ex_trans.get('line_description')):
                    example_parts.append(str(ex_trans['line_description']))
                if is_valid_value(ex_trans.get('gl_description')):
                    example_parts.append(str(ex_trans['gl_description']))
                
                if example_parts:
                    example_texts.append(" ".join(example_parts[:3]))
                else:
                    example_texts.append("")
            
            # Use semantic search to find similar examples
            try:
                from sentence_transformers import SentenceTransformer
                import numpy as np
                
                model = SentenceTransformer('all-MiniLM-L6-v2')
                
                # Encode query and examples
                query_embedding = model.encode([query_text], convert_to_numpy=True)[0]
                example_embeddings = model.encode(example_texts, convert_to_numpy=True)
                
                # Calculate cosine similarities
                similarities = np.dot(example_embeddings, query_embedding) / (
                    np.linalg.norm(example_embeddings, axis=1) * np.linalg.norm(query_embedding)
                )
                
                # Get top N most similar examples
                top_indices = np.argsort(similarities)[::-1][:limit]
                
                similar_examples = []
                for idx in top_indices:
                    if similarities[idx] > 0.4:  # Higher threshold (0.4) to ensure quality matches only
                        similar_examples.append(successful_examples[idx])
                
                return similar_examples
                
            except ImportError:
                # Fallback to simple word matching if semantic search not available
                logger.warning("Semantic search not available, using simple word matching for examples")
                query_words = set(query_text.lower().split())
                
                scored_examples = []
                for idx, example_text in enumerate(example_texts):
                    if example_text:
                        example_words = set(example_text.lower().split())
                        overlap = len(query_words & example_words) / max(len(query_words), 1)
                        if overlap > 0.2:  # At least 20% word overlap
                            scored_examples.append((overlap, successful_examples[idx]))
                
                scored_examples.sort(key=lambda x: -x[0])
                return [ex for _, ex in scored_examples[:limit]]
                
        except Exception as e:
            logger.warning(f"Error finding similar examples: {e}", exc_info=True)
            return []
    
    def _format_examples_for_prompt(self, examples: List[Dict]) -> str:
        """
        Format successful examples for inclusion in the prompt.
        Keeps examples concise to minimize token usage.
        
        Args:
            examples: List of example dictionaries from _find_similar_successful_examples
            
        Returns:
            Formatted string with examples (concise format)
        """
        if not examples:
            return ""
        
        lines = ["\nSimilar examples:", ""]
        
        for idx, example in enumerate(examples[:self._max_examples], 1):
            ex_trans = example.get('transaction_data', {})
            classification_path = example.get('classification_path', '')
            
            # Use strong signals first for example description
            desc = ""
            if is_valid_value(ex_trans.get('department')):
                desc = f"Dept: {str(ex_trans['department'])[:60]}"
            elif is_valid_value(ex_trans.get('gl_code')):
                desc = f"GL: {str(ex_trans['gl_code'])[:60]}"
            elif is_valid_value(ex_trans.get('line_description')):
                desc = str(ex_trans['line_description'])[:80]  # Truncate to 80 chars
            elif is_valid_value(ex_trans.get('gl_description')):
                desc = str(ex_trans['gl_description'])[:80]
            
            if desc and classification_path:
                lines.append(f"{idx}. \"{desc}\" → {classification_path}")
        
        if len(lines) > 2:  # Has examples
            return "\n".join(lines)
        return ""

    def classify_transaction(
        self,
        supplier_profile: Dict,
        transaction_data: Dict,
        taxonomy_yaml: Optional[str] = None,
        prioritization_decision: Optional[PrioritizationDecision] = None,
        dataset_name: Optional[str] = None,
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
        
        # Find similar successful examples for BootstrapFewShot (optional, can be disabled for rate limits)
        similar_examples = []
        if (self._enable_examples and hasattr(self, 'db_manager') and self.db_manager):
            try:
                similar_examples = self._find_similar_successful_examples(
                    transaction_data=transaction_data,
                    supplier_profile=supplier_profile,
                    taxonomy_path=taxonomy_source,
                    dataset_name=dataset_name,
                    limit=self._max_examples
                )
                # Only include examples if we have high-quality matches (similarity > threshold)
                # This prevents adding noise and unnecessary tokens
                if similar_examples:
                    examples_text = self._format_examples_for_prompt(similar_examples)
                    if examples_text:  # Only add if we have valid examples
                        taxonomy_sample += "\n" + examples_text
            except Exception as e:
                logger.debug(f"Could not retrieve similar examples: {e}")
        
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

    def classify_with_tools(self, *args, **kwargs) -> ClassificationResult:
        """Alias for classify_transaction (backward compat)."""
        return self.classify_transaction(*args, **kwargs)
