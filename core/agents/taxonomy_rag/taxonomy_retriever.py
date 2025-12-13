"""Taxonomy Retriever using FAISS vector database for hybrid search (keyword + semantic)."""

import hashlib
import logging
import re
import threading
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None

try:
    from sentence_transformers import SentenceTransformer
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    SentenceTransformer = None

from core.utils.data.transaction_utils import is_valid_value

logger = logging.getLogger(__name__)


class RetrievalResult:
    """Result of taxonomy retrieval with similarity scores."""
    
    def __init__(self, path: str, combined_score: float, metadata: Dict):
        self.path = path
        self.combined_score = combined_score  # 0-1 normalized score
        self.metadata = metadata  # {'keyword_score': float, 'semantic_score': float, ...}
    
    def __repr__(self):
        return f"RetrievalResult(path='{self.path}', score={self.combined_score:.3f})"


class TaxonomyRetriever:
    """
    RAG component for retrieving relevant taxonomy paths using hybrid search.
    
    Combines:
    1. Keyword similarity (fast, exact matches)
    2. Semantic similarity (flexible, contextual matches via FAISS)
    
    Uses FAISS vector database for efficient semantic search on taxonomy embeddings.
    Supports multi-query RAG for better coverage.
    """
    
    def __init__(
        self, 
        embedding_model_name: str = "all-MiniLM-L6-v2"
    ):
        """
        Initialize the taxonomy retriever.
        
        Uses open-source SentenceTransformer models (runs locally, no API keys needed).
        Default: 'all-MiniLM-L6-v2' - fast, lightweight (80MB), good accuracy
        
        Alternative open-source models you can use:
        - 'all-mpnet-base-v2' - Better accuracy, larger (420MB), slower
        - 'paraphrase-multilingual-mpnet-base-v2' - Multilingual support
        - 'sentence-transformers/all-MiniLM-L12-v2' - Slightly better than L6, larger
        - 'ms-marco-MiniLM-L-12-v2' - Optimized for search/retrieval tasks
        
        Args:
            embedding_model_name: Name of the SentenceTransformer model to use for embeddings
        """
        if not FAISS_AVAILABLE:
            logger.warning("FAISS not available. Falling back to in-memory search only.")
        
        if not SEMANTIC_AVAILABLE:
            logger.warning("SentenceTransformers not available. Semantic search will be disabled.")
        
        self.embedding_model_name = embedding_model_name
        
        self._embedding_model: Optional[SentenceTransformer] = None
        self._lock = threading.Lock()
        
        # Cache for taxonomy indices (FAISS index + metadata)
        self._index_cache: Dict[str, Tuple[faiss.Index, List[str]]] = {}
        self._embeddings_cache: Dict[str, np.ndarray] = {}
        self._taxonomy_cache: Dict[str, List[str]] = {}
    
    def _get_embedding_model(self) -> Optional[SentenceTransformer]:
        """Get or initialize the embedding model (thread-safe)."""
        if not SEMANTIC_AVAILABLE:
            return None
        
        if self._embedding_model is None:
            with self._lock:
                if self._embedding_model is None:
                    try:
                        self._embedding_model = SentenceTransformer(self.embedding_model_name)
                        logger.info(f"Initialized embedding model: {self.embedding_model_name}")
                    except Exception as e:
                        logger.error(f"Failed to load embedding model: {e}")
                        return None
        
        return self._embedding_model
    
    def _get_taxonomy_cache_key(self, taxonomy_list: List[str], descriptions: Optional[Dict[str, str]] = None) -> str:
        """Generate cache key for taxonomy list and descriptions."""
        # Use sorted taxonomy to create stable hash
        taxonomy_str = "|".join(sorted(taxonomy_list))
        # Include descriptions in cache key if provided
        if descriptions:
            desc_str = "|".join(sorted(f"{k}:{v}" for k, v in descriptions.items()))
            cache_input = f"{taxonomy_str}||{desc_str}"
        else:
            cache_input = taxonomy_str
        return hashlib.md5(cache_input.encode()).hexdigest()
    
    def _build_faiss_index(
        self, 
        taxonomy_list: List[str],
        descriptions: Optional[Dict[str, str]] = None
    ) -> Tuple[faiss.Index, np.ndarray]:
        """
        Build FAISS index for taxonomy embeddings.
        
        Args:
            taxonomy_list: List of taxonomy paths
            descriptions: Optional dictionary mapping paths to descriptions
            
        Returns:
            Tuple of (FAISS index, embeddings array)
        """
        model = self._get_embedding_model()
        if model is None or not FAISS_AVAILABLE:
            # Fallback: return None indices
            return None, None
        
        try:
            # Build enriched text for embedding: combine path with description if available
            texts_to_embed = []
            for path in taxonomy_list:
                if descriptions and path in descriptions:
                    # Combine path with description for richer semantic meaning
                    description = descriptions[path].strip()
                    enriched = f"{path} - {description}"
                else:
                    # Fallback to path only if no description available
                    enriched = path
                texts_to_embed.append(enriched)
            
            # Generate embeddings from enriched text
            embeddings = model.encode(texts_to_embed, convert_to_numpy=True, show_progress_bar=False)
            embeddings = embeddings.astype('float32')
            
            # Normalize embeddings for cosine similarity
            faiss.normalize_L2(embeddings)
            
            # Create FAISS index (using inner product since embeddings are normalized)
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatIP(dimension)  # Inner Product = Cosine similarity for normalized vectors
            
            # Add embeddings to index
            index.add(embeddings)
            
            logger.debug(f"Built FAISS index for {len(taxonomy_list)} taxonomy paths (with descriptions: {descriptions is not None})")
            return index, embeddings
        
        except Exception as e:
            logger.error(f"Failed to build FAISS index: {e}")
            return None, None
    
    def _get_or_build_index(
        self, 
        taxonomy_list: List[str],
        descriptions: Optional[Dict[str, str]] = None
    ) -> Tuple[Optional[faiss.Index], Optional[np.ndarray]]:
        """Get or build FAISS index for taxonomy (cached)."""
        cache_key = self._get_taxonomy_cache_key(taxonomy_list, descriptions)
        
        if cache_key in self._index_cache:
            return self._index_cache[cache_key]
        
        # Build new index
        index, embeddings = self._build_faiss_index(taxonomy_list, descriptions)
        
        if index is not None:
            self._index_cache[cache_key] = (index, embeddings)
            self._taxonomy_cache[cache_key] = taxonomy_list
        
        return index, embeddings
    
    def _tokenize(self, text: str) -> Set[str]:
        """Tokenize text into lowercase words, removing common stopwords."""
        stopwords = {'and', 'or', 'the', 'a', 'an', 'of', 'for', 'to', 'in', 'on', 'at', '&'}
        words = re.split(r'[^a-zA-Z0-9]+', text.lower())
        return {w for w in words if w and len(w) > 1 and w not in stopwords}
    
    def _keyword_similarity(self, query: str, path: str) -> float:
        """
        Calculate keyword-based similarity score between query and path.
        
        Returns:
            Score between 0.0 and 1.0
        """
        query_tokens = self._tokenize(query)
        path_tokens = self._tokenize(path)
        
        if not query_tokens or not path_tokens:
            return 0.0
        
        # Exact matches
        exact_matches = len(query_tokens & path_tokens)
        
        # Partial matches (one contains the other)
        partial_matches = 0
        for qt in query_tokens:
            for pt in path_tokens:
                if qt != pt and (qt in pt or pt in qt) and len(min(qt, pt, key=len)) >= 3:
                    partial_matches += 0.5
        
        # Score based on proportion of query matched
        score = (exact_matches + partial_matches) / len(query_tokens)
        
        # Boost for deeper paths (more specific)
        depth = len(path.split("|"))
        depth_bonus = min(depth * 0.05, 0.2)  # Cap at 0.2
        
        return min(score + depth_bonus, 1.0)
    
    def _semantic_search_faiss(
        self,
        query: str,
        taxonomy_list: List[str],
        top_k: int = 20,
        descriptions: Optional[Dict[str, str]] = None
    ) -> List[Tuple[float, str]]:
        """
        Perform semantic search using FAISS vector database.
        
        Args:
            query: Search query text
            taxonomy_list: List of taxonomy paths to search
            top_k: Number of top results to return
            descriptions: Optional dictionary mapping paths to descriptions
            
        Returns:
            List of (similarity_score, path) tuples sorted by similarity
        """
        model = self._get_embedding_model()
        if model is None or not FAISS_AVAILABLE:
            return []
        
        try:
            # Get or build FAISS index
            index, embeddings = self._get_or_build_index(taxonomy_list, descriptions)
            if index is None:
                return []
            
            # Encode query
            query_embedding = model.encode([query], convert_to_numpy=True, show_progress_bar=False)[0]
            query_embedding = query_embedding.astype('float32')
            
            # Normalize for cosine similarity
            query_norm = np.linalg.norm(query_embedding)
            if query_norm > 0:
                query_embedding = query_embedding / query_norm
            
            # Reshape for FAISS (1 x dimension)
            query_embedding = query_embedding.reshape(1, -1)
            
            # Search
            scores, indices = index.search(query_embedding, min(top_k, len(taxonomy_list)))
            
            # Convert to list of (score, path) tuples
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < len(taxonomy_list) and score > 0.1:  # Threshold for relevance
                    results.append((float(score), taxonomy_list[idx]))
            
            return results
        
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
    
    def _build_search_query(
        self,
        transaction_data: Dict,
        supplier_profile: Optional[Dict],
        multi_query: bool = True
    ) -> List[str]:
        """
        Build search queries from transaction data and supplier profile.
        
        Supports multi-query RAG: generates multiple query variations for better coverage.
        
        Args:
            transaction_data: Transaction data dictionary
            supplier_profile: Optional supplier profile dictionary
            multi_query: If True, generates multiple query variations
            
        Returns:
            List of search query strings (multiple variations if multi_query=True)
        """
        queries = []
        
        # Supplier profile signals (strong)
        if supplier_profile:
            if is_valid_value(supplier_profile.get('products_services')):
                queries.append(str(supplier_profile['products_services']))
            if is_valid_value(supplier_profile.get('service_type')):
                queries.append(str(supplier_profile['service_type']))
            if is_valid_value(supplier_profile.get('industry')):
                queries.append(str(supplier_profile['industry']))
        
        # Structured transaction signals
        if is_valid_value(transaction_data.get('department')):
            queries.append(str(transaction_data['department']))
        
        if is_valid_value(transaction_data.get('gl_code')):
            queries.append(str(transaction_data['gl_code']))
        
        if is_valid_value(transaction_data.get('cost_center')):
            queries.append(str(transaction_data['cost_center']))
        
        # Description fields (GL/Line descriptions as requested)
        if is_valid_value(transaction_data.get('line_description')):
            queries.append(str(transaction_data['line_description']))
        
        if is_valid_value(transaction_data.get('gl_description')):
            queries.append(str(transaction_data['gl_description']))
        
        # Other potentially useful fields
        if is_valid_value(transaction_data.get('po_number')):
            queries.append(str(transaction_data['po_number']))
        
        # Multi-query: Generate query variations for better coverage
        if multi_query and queries:
            query_variations = self._generate_query_variations(transaction_data, supplier_profile, queries)
            return query_variations
        
        return queries
    
    def _generate_query_variations(
        self,
        transaction_data: Dict,
        supplier_profile: Optional[Dict],
        base_queries: List[str]
    ) -> List[str]:
        """
        Generate multiple query variations for multi-query RAG.
        
        Creates variations by combining different fields in different ways:
        - Supplier-focused queries
        - Transaction-focused queries
        - Combined queries
        - Field-specific queries
        
        Args:
            transaction_data: Transaction data dictionary
            supplier_profile: Optional supplier profile dictionary
            base_queries: List of base query strings
            
        Returns:
            List of query variation strings
        """
        variations = []
        
        # Variation 1: Supplier-focused (if available)
        if supplier_profile:
            supplier_parts = []
            if is_valid_value(supplier_profile.get('products_services')):
                supplier_parts.append(str(supplier_profile['products_services']))
            if is_valid_value(supplier_profile.get('service_type')):
                supplier_parts.append(str(supplier_profile['service_type']))
            if supplier_parts:
                variations.append(" ".join(supplier_parts))
        
        # Variation 2: Transaction structured fields
        structured_parts = []
        if is_valid_value(transaction_data.get('department')):
            structured_parts.append(str(transaction_data['department']))
        if is_valid_value(transaction_data.get('gl_code')):
            structured_parts.append(str(transaction_data['gl_code']))
        if structured_parts:
            variations.append(" ".join(structured_parts))
        
        # Variation 3: Description-focused
        desc_parts = []
        if is_valid_value(transaction_data.get('line_description')):
            line_desc = str(transaction_data['line_description'])
            # Take first 50 words to avoid too long queries
            words = line_desc.split()[:50]
            desc_parts.append(" ".join(words))
        if is_valid_value(transaction_data.get('gl_description')):
            desc_parts.append(str(transaction_data['gl_description']))
        if desc_parts:
            variations.append(" ".join(desc_parts))
        
        # Variation 4: Combined (supplier + structured)
        combined_parts = []
        if supplier_profile and is_valid_value(supplier_profile.get('products_services')):
            combined_parts.append(str(supplier_profile['products_services']))
        if is_valid_value(transaction_data.get('department')):
            combined_parts.append(str(transaction_data['department']))
        if combined_parts:
            variations.append(" ".join(combined_parts))
        
        # Variation 5: All fields combined (comprehensive query)
        if base_queries:
            # Use top 5 queries to avoid too long
            all_combined = " ".join(base_queries[:5])
            if len(all_combined.strip()) > 0:
                variations.append(all_combined)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for var in variations:
            var_lower = var.lower().strip()
            if var_lower and var_lower not in seen:
                seen.add(var_lower)
                unique_variations.append(var)
        
        # Return variations (at least the base queries if no variations generated)
        return unique_variations if unique_variations else base_queries
    
    def retrieve_with_scores(
        self,
        transaction_data: Dict,
        supplier_profile: Optional[Dict],
        taxonomy_list: List[str],
        top_k: int = 20,
        keyword_weight: float = 0.4,
        semantic_weight: float = 0.6,
        min_score: float = 0.05,  # Lower threshold to get more results
        descriptions: Optional[Dict[str, str]] = None
    ) -> List[RetrievalResult]:
        """
        Retrieve taxonomy paths with similarity scores using hybrid search with multi-query RAG.
        
        Args:
            transaction_data: Transaction data dictionary
            supplier_profile: Optional supplier profile dictionary
            taxonomy_list: List of all taxonomy paths to search
            top_k: Maximum number of results to return
            keyword_weight: Weight for keyword similarity (0-1)
            semantic_weight: Weight for semantic similarity (0-1)
            min_score: Minimum combined score threshold (lowered to get more results)
            descriptions: Optional dictionary mapping taxonomy paths to descriptions
            
        Returns:
            List of RetrievalResult objects sorted by combined_score (descending)
        """
        if not taxonomy_list:
            return []
        
        # Ensure weights sum to 1.0
        total_weight = keyword_weight + semantic_weight
        if total_weight > 0:
            keyword_weight = keyword_weight / total_weight
            semantic_weight = semantic_weight / total_weight
        
        # Build search queries (multi-query variations)
        query_variations = self._build_search_query(transaction_data, supplier_profile, multi_query=True)
        
        if not query_variations:
            return []
        
        # Retrieve more candidates to ensure good coverage
        initial_top_k = top_k * 2
        
        # MULTI-QUERY RAG: Search with each query variation and aggregate results
        all_semantic_results: Dict[str, List[float]] = {}  # path -> list of scores from different queries
        
        for query_var in query_variations[:5]:  # Limit to 5 variations to avoid too many searches
            # Get semantic search results for this query variation
            var_results = self._semantic_search_faiss(
                query_var,
                taxonomy_list,
                top_k=initial_top_k,
                descriptions=descriptions
            )
            
            # Aggregate scores: if path appears in multiple queries, keep max score
            for score, path in var_results:
                if path not in all_semantic_results:
                    all_semantic_results[path] = []
                all_semantic_results[path].append(score)
        
        # Aggregate semantic scores: use max score across all query variations
        semantic_results = []
        for path, scores in all_semantic_results.items():
            max_score = max(scores)
            # Boost paths that appear in multiple queries (indicates stronger match)
            if len(scores) > 1:
                # Small boost for multi-query matches
                boost = min(0.1 * (len(scores) - 1), 0.2)
                max_score = min(max_score + boost, 1.0)
            semantic_results.append((max_score, path))
        
        # Sort by score
        semantic_results.sort(key=lambda x: x[0], reverse=True)
        # Take top initial_top_k after aggregation
        semantic_results = semantic_results[:initial_top_k]
        
        # Build keyword scores for all paths (using multi-query variations)
        keyword_scores: Dict[str, float] = {}
        for path in taxonomy_list:
            # Get max keyword score across all query variations
            max_kw_score = 0.0
            query_matches = 0
            for query_var in query_variations:
                kw_score = self._keyword_similarity(query_var, path)
                if kw_score > 0:
                    query_matches += 1
                max_kw_score = max(max_kw_score, kw_score)
            
            # Boost if path matches multiple query variations
            if query_matches > 1:
                boost = min(0.1 * (query_matches - 1), 0.15)
                max_kw_score = min(max_kw_score + boost, 1.0)
            
            if max_kw_score > 0:
                keyword_scores[path] = max_kw_score
        
        # Combine results from first step
        combined_scores: Dict[str, Tuple[float, float, float]] = {}  # path -> (kw, sem, combined)
        
        # Add semantic results
        for sem_score, path in semantic_results:
            kw_score = keyword_scores.get(path, 0.0)
            combined = (keyword_weight * kw_score) + (semantic_weight * sem_score)
            combined_scores[path] = (kw_score, sem_score, combined)
        
        # Also include high keyword matches that semantic search might have missed
        for path, kw_score in keyword_scores.items():
            if path not in combined_scores and kw_score > 0.3:
                combined = keyword_weight * kw_score  # No semantic score for these
                combined_scores[path] = (kw_score, 0.0, combined)
        
        # Filter by min_score and get candidate paths
        candidate_results = []
        for path, (kw_score, sem_score, combined) in combined_scores.items():
            if combined >= min_score:
                candidate_results.append(RetrievalResult(
                    path=path,
                    combined_score=combined,
                    metadata={
                        'keyword_score': kw_score,
                        'semantic_score': sem_score,
                        'depth': len(path.split("|"))
                    }
                ))
        
        # Sort by combined score (descending)
        candidate_results.sort(key=lambda x: x.combined_score, reverse=True)
        
        # Return top_k results (no reranking)
        return candidate_results[:top_k]
    
    def get_confidence_score(
        self,
        transaction_data: Dict,
        supplier_profile: Optional[Dict],
        taxonomy_list: List[str],
        top_n: int = 3,
        descriptions: Optional[Dict[str, str]] = None
    ) -> float:
        """
        Get overall confidence score (0-1) for how well transaction matches taxonomy.
        
        Used for research decisions. Higher score = better match = research less needed.
        
        Args:
            transaction_data: Transaction data dictionary
            supplier_profile: Optional supplier profile dictionary
            taxonomy_list: List of taxonomy paths
            top_n: Number of top results to consider for confidence
            descriptions: Optional dictionary mapping taxonomy paths to descriptions
            
        Returns:
            Float 0-1: Higher = better match
        """
        results = self.retrieve_with_scores(
            transaction_data,
            supplier_profile,
            taxonomy_list,
            top_k=top_n,
            min_score=0.0,
            descriptions=descriptions
        )
        
        if not results:
            return 0.0
        
        # Use max score or average of top N
        if len(results) == 1:
            return results[0].combined_score
        
        # Average of top N scores (but weighted towards max)
        top_score = results[0].combined_score
        avg_score = sum(r.combined_score for r in results[:top_n]) / min(top_n, len(results))
        
        # Weighted combination: 70% max, 30% average
        return (0.7 * top_score) + (0.3 * avg_score)
    
    def retrieve_grouped_by_l1(
        self,
        transaction_data: Dict,
        supplier_profile: Optional[Dict],
        taxonomy_list: List[str],
        max_l1_categories: int = 6,
        max_paths_per_l1: int = 10,
        max_total_paths: int = 60,
        descriptions: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[str]]:
        """
        Retrieve taxonomy paths grouped by L1 category.
        
        Useful for organizing results hierarchically for LLM classification.
        
        Args:
            transaction_data: Transaction data dictionary
            supplier_profile: Optional supplier profile dictionary
            taxonomy_list: List of taxonomy paths
            max_l1_categories: Maximum number of L1 categories to return
            max_paths_per_l1: Maximum paths per L1 category
            max_total_paths: Maximum total paths across all L1s
            descriptions: Optional dictionary mapping taxonomy paths to descriptions
            
        Returns:
            Dictionary mapping L1 category to list of paths
        """
        results = self.retrieve_with_scores(
            transaction_data,
            supplier_profile,
            taxonomy_list,
            top_k=max_total_paths * 2,  # Get more for filtering
            min_score=0.05,  # Lower threshold to get more results
            descriptions=descriptions
        )
        
        # Group by L1
        l1_groups: Dict[str, List[Tuple[float, str]]] = {}
        
        for result in results:
            path = result.path
            l1 = path.split("|")[0] if "|" in path else path
            
            if l1 not in l1_groups:
                l1_groups[l1] = []
            
            l1_groups[l1].append((result.combined_score, path))
        
        # Sort paths within each L1 by score
        for l1 in l1_groups:
            l1_groups[l1].sort(key=lambda x: x[0], reverse=True)
        
        # Select top L1 categories by max score
        l1_scores = []
        for l1, paths in l1_groups.items():
            max_path_score = paths[0][0] if paths else 0.0
            num_paths = len(paths)
            # Score L1 by: max path score + bonus for multiple paths
            l1_score = max_path_score + (min(num_paths, 5) * 0.05)
            l1_scores.append((l1_score, l1))
        
        l1_scores.sort(key=lambda x: x[0], reverse=True)
        top_l1s = [l1 for _, l1 in l1_scores[:max_l1_categories]]
        
        # Build result dictionary
        result_dict: Dict[str, List[str]] = {}
        total_paths = 0
        
        for l1 in top_l1s:
            paths_with_scores = l1_groups[l1]
            paths_to_take = min(max_paths_per_l1, max_total_paths - total_paths)
            
            if paths_to_take > 0:
                result_dict[l1] = [path for _, path in paths_with_scores[:paths_to_take]]
                total_paths += len(result_dict[l1])
        
        # Add paths from other L1s if space remains
        if total_paths < max_total_paths:
            for l1, paths_with_scores in l1_groups.items():
                if l1 not in result_dict:
                    remaining = max_total_paths - total_paths
                    if remaining > 0:
                        result_dict[l1] = [path for _, path in paths_with_scores[:min(max_paths_per_l1, remaining)]]
                        total_paths += len(result_dict[l1])
                        if total_paths >= max_total_paths:
                            break
        
        return result_dict

