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
        self.research_agent = None  # Will be set by pipeline for company domain research
        self._company_context_cache: Dict[str, str] = {}  # Cache company domain context
        self._classifier = None  # ChainOfThought classifier instance
        self.db_manager = None  # Will be set by pipeline for BootstrapFewShot examples
        self._max_examples = 2  # Maximum number of examples to include (conservative to minimize tokens)
        self._enable_examples = True  # Enabled - improves accuracy


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
        """Format transaction data, emphasizing line_description as PRIMARY signal.
        
        Includes all available transaction fields, prioritizing canonical fields
        but also including any unmapped columns that might contain useful information.
        """
        parts = []
        
        # PRIMARY signal - format prominently
        if is_valid_value(transaction_data.get('line_description')):
            parts.append(f"Line Description (PRIMARY): {transaction_data['line_description']}")
        
        # SECONDARY but important canonical fields
        if is_valid_value(transaction_data.get('gl_description')):
            parts.append(f"GL Description (SECONDARY): {transaction_data['gl_description']}")
        
        # Other canonical fields that might be useful
        for field in ['department', 'gl_code', 'invoice_number', 'po_number', 'invoice_date', 'amount']:
            if is_valid_value(transaction_data.get(field)):
                parts.append(f"{field.replace('_', ' ').title()}: {transaction_data[field]}")
        
        # Include any other unmapped fields that might contain useful information
        # (exclude supplier_name as it's handled separately, and classification result fields)
        excluded_fields = {'supplier_name', 'L1', 'L2', 'L3', 'L4', 'L5', 'classification_path', 
                          'pipeline_output', 'expected_output', 'error', 'reasoning'}
        other_fields = []
        for key, value in sorted(transaction_data.items()):
            if key not in excluded_fields and is_valid_value(value):
                # Skip if already included above
                if key not in ['line_description', 'gl_description', 'department', 'gl_code', 
                              'invoice_number', 'po_number', 'invoice_date', 'amount']:
                    other_fields.append(f"{key}: {value}")
        
        if other_fields:
            parts.append("\nAdditional Transaction Fields:")
            parts.extend(other_fields)
        
        # Supplier name (for reference, not primary classification signal)
        if is_valid_value(transaction_data.get('supplier_name')):
            parts.append(f"\nSupplier Name: {transaction_data['supplier_name']}")
        
        return "\n".join(parts) if parts else "No transaction details available"

    def _get_relevant_taxonomy_paths(self, transaction_data: Dict, supplier_profile: Dict, taxonomy_list: List[str]) -> Dict[str, List[str]]:
        """
        Use semantic search to find relevant taxonomy paths based on transaction and supplier data.
        Groups paths by L1 category for better hierarchical organization.
        
        Returns:
            Dictionary mapping L1 category to list of paths within that L1
        """
        search_queries = []
        
        # Extract search terms from transaction data (what was purchased)
        if is_valid_value(transaction_data.get('line_description')):
            search_queries.append(str(transaction_data['line_description']))
        if is_valid_value(transaction_data.get('gl_description')):
            search_queries.append(str(transaction_data['gl_description']))
        if is_valid_value(transaction_data.get('department')):
            search_queries.append(str(transaction_data['department']))
        
        # Extract search terms from supplier profile (who it was purchased from)
        if supplier_profile:
            if supplier_profile.get('products_services'):
                search_queries.append(str(supplier_profile['products_services']))
            if supplier_profile.get('service_type'):
                search_queries.append(str(supplier_profile['service_type']))
            if supplier_profile.get('industry'):
                search_queries.append(str(supplier_profile['industry']))
        
        # Use semantic search to find relevant paths for each query
        # Collect all matches with their scores
        all_paths_with_scores: Dict[str, float] = {}  # path -> max_score
        
        for query in search_queries[:3]:  # Use top 3 queries for better coverage
            matches = lookup_paths(query, taxonomy_list)
            # Store paths, assigning higher scores to earlier matches (they're already sorted by relevance)
            for idx, path in enumerate(matches[:8]):  # Top 8 matches per query
                score = 10.0 - idx  # Higher score for better matches
                if path not in all_paths_with_scores or score > all_paths_with_scores[path]:
                    all_paths_with_scores[path] = score
        
        # Group paths by L1 category
        l1_groups: Dict[str, List[Tuple[float, str]]] = {}  # l1 -> [(score, path), ...]
        
        for path, score in all_paths_with_scores.items():
            l1 = path.split("|")[0] if "|" in path else path
            if l1 not in l1_groups:
                l1_groups[l1] = []
            # Boost score for deeper paths (more specific)
            depth = len(path.split("|"))
            adjusted_score = score + (depth * 0.5)
            l1_groups[l1].append((adjusted_score, path))
        
        # Sort paths within each L1 by score (descending), then by depth
        for l1 in l1_groups:
            l1_groups[l1].sort(key=lambda x: (-x[0], -len(x[1].split("|"))))
        
        # Select top 3-4 L1 categories (by number of matches and highest scores)
        l1_scores = []
        for l1, paths in l1_groups.items():
            # Score L1 by: max individual path score + number of paths
            max_path_score = max(score for score, _ in paths) if paths else 0
            num_paths = len(paths)
            l1_score = max_path_score + (num_paths * 0.3)
            l1_scores.append((l1_score, l1))
        
        l1_scores.sort(key=lambda x: -x[0])  # Sort descending by score
        top_l1s = [l1 for _, l1 in l1_scores[:4]]  # Top 4 L1 categories
        
        # Build result: top L1s with their top paths
        result: Dict[str, List[str]] = {}
        total_paths = 0
        
        for l1 in top_l1s:
            paths_with_scores = l1_groups[l1]
            # Take top 3-5 paths per L1, but limit total to 20
            paths_to_take = min(5, 20 - total_paths) if total_paths < 20 else 0
            if paths_to_take > 0:
                result[l1] = [path for _, path in paths_with_scores[:paths_to_take]]
                total_paths += len(result[l1])
        
        # If we have space, add paths from other L1s
        if total_paths < 20:
            for l1, paths_with_scores in l1_groups.items():
                if l1 not in result:
                    remaining = 20 - total_paths
                    if remaining > 0:
                        result[l1] = [path for _, path in paths_with_scores[:min(3, remaining)]]
                        total_paths += len(result[l1])
                        if total_paths >= 20:
                            break
        
        return result
    
    def _format_taxonomy_sample_by_l1(self, l1_grouped_paths: Dict[str, List[str]]) -> str:
        """
        Format taxonomy paths as a flat list (same format as before).
        The L1-grouping logic in selection improves which paths are chosen,
        but we don't need to show the grouping to the LLM.
        
        Args:
            l1_grouped_paths: Dictionary mapping L1 category to list of paths
            
        Returns:
            Formatted string with paths in flat list format (same as old method)
        """
        if not l1_grouped_paths:
            return "No relevant paths found."
        
        # Flatten the grouped paths into a simple list (same format as before)
        flat_paths = []
        for paths in l1_grouped_paths.values():
            flat_paths.extend(paths)
        
        # Format same as old method: just paths, one per line
        return "Relevant taxonomy paths (semantically matched):\n" + "\n".join(flat_paths)
    
    def _extract_domain_context(
        self, 
        taxonomy_path: str, 
        dataset_name: Optional[str] = None
    ) -> str:
        """
        Extract company domain context using web search.
        Always attempts to search for company information to provide domain context.
        """
        cache_key = f"{taxonomy_path}|{dataset_name}"
        if cache_key in self._company_context_cache:
            return self._company_context_cache[cache_key]
        
        context_parts = []
        
        # Extract company name from taxonomy filename
        taxonomy_filename = str(taxonomy_path).split('/')[-1] if '/' in str(taxonomy_path) else str(taxonomy_path)
        company_name = taxonomy_filename.split('_')[0] if '_' in taxonomy_filename else taxonomy_filename.replace('.yaml', '').replace('.YAML', '')
        
        # Use web search to get company domain context if research agent is available
        # NOTE: This adds latency (Exa API call ~1-3s per company). 
        # DISABLED for performance - using company name/dataset only for now
        # Can be re-enabled if needed, but it significantly slows down benchmarks
        # if self.research_agent and company_name and company_name.lower() not in ['taxonomy', 'taxonomies']:
        #     try:
        #         company_profile = self.research_agent.research_supplier(company_name)
        #         if company_profile and company_profile.industry:
        #             context_parts.append(f"Company Industry: {company_profile.industry}")
        #             if company_profile.description:
        #                 desc = company_profile.description[:200]
        #                 context_parts.append(f"Company Description: {desc}")
        #     except Exception as e:
        #         logger.debug(f"Company domain research failed for {company_name}: {e}")
        
        # Always include company name and dataset for context
        if company_name and company_name.lower() not in ['taxonomy', 'taxonomies']:
            context_parts.append(f"Company Name: {company_name}")
        
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
            
            # Build query text from current transaction
            query_parts = []
            if is_valid_value(transaction_data.get('line_description')):
                query_parts.append(str(transaction_data['line_description']))
            if is_valid_value(transaction_data.get('gl_description')):
                query_parts.append(str(transaction_data['gl_description']))
            if is_valid_value(transaction_data.get('department')):
                query_parts.append(str(transaction_data['department']))
            
            if supplier_profile:
                if supplier_profile.get('products_services'):
                    query_parts.append(str(supplier_profile['products_services']))
                if supplier_profile.get('service_type'):
                    query_parts.append(str(supplier_profile['service_type']))
            
            if not query_parts:
                return []
            
            query_text = " ".join(query_parts[:3])  # Use top 3 parts
            
            # Build texts from example transactions for semantic search
            example_texts = []
            for example in successful_examples:
                example_parts = []
                ex_trans = example.get('transaction_data', {})
                ex_supplier = example.get('supplier_profile', {})
                
                if is_valid_value(ex_trans.get('line_description')):
                    example_parts.append(str(ex_trans['line_description']))
                if is_valid_value(ex_trans.get('gl_description')):
                    example_parts.append(str(ex_trans['gl_description']))
                if is_valid_value(ex_trans.get('department')):
                    example_parts.append(str(ex_trans['department']))
                
                if ex_supplier:
                    if ex_supplier.get('products_services'):
                        example_parts.append(str(ex_supplier['products_services']))
                    if ex_supplier.get('service_type'):
                        example_parts.append(str(ex_supplier['service_type']))
                
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
            
            # Use only most important fields, truncate to keep tokens low
            desc = ""
            if is_valid_value(ex_trans.get('line_description')):
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
        self._current_taxonomy = taxonomy_list

        supplier_info = self._format_supplier_info(supplier_profile)
        transaction_info = self._format_transaction_info(transaction_data)
        
        # Use semantic search to find top relevant paths, grouped by L1
        l1_grouped_paths = self._get_relevant_taxonomy_paths(transaction_data, supplier_profile, taxonomy_list)
        
        # Format taxonomy paths organized by L1 for better LLM reasoning
        taxonomy_sample = self._format_taxonomy_sample_by_l1(l1_grouped_paths)
        
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
                # Fallback: use semantic search to find best match
                query = transaction_data.get('line_description') or transaction_data.get('gl_description') or ''
                if query:
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
                # Try to find most relevant deeper path using semantic search
                query = transaction_data.get('line_description') or transaction_data.get('gl_description') or ''
                if query:
                    matches = lookup_paths(str(query), l1_paths)
                    if matches:
                        classification_path = matches[0]
                        reasoning += f" [Auto-expanded from L1 to: {classification_path}]"
                    else:
                        # Fallback to first deeper path
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
