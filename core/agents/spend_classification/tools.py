"""Classification tools for spend classification.

Uses word-level tokenization, fuzzy matching, and semantic search for robust taxonomy search.
These tools are used for pre-searching taxonomy paths and validation.
"""

import re
from typing import List, Dict, Set, Tuple, Optional

# Optional semantic search imports
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    SentenceTransformer = None


def _tokenize(text: str) -> Set[str]:
    """Tokenize text into lowercase words, removing common stopwords."""
    stopwords = {'and', 'or', 'the', 'a', 'an', 'of', 'for', 'to', 'in', 'on', 'at', '&'}
    # Split on non-alphanumeric characters
    words = re.split(r'[^a-zA-Z0-9]+', text.lower())
    return {w for w in words if w and len(w) > 1 and w not in stopwords}


def _word_overlap_score(query_tokens: Set[str], path_tokens: Set[str]) -> float:
    """Calculate overlap score between query and path tokens."""
    if not query_tokens or not path_tokens:
        return 0.0
    
    # Count exact matches
    exact_matches = len(query_tokens & path_tokens)
    
    # Count partial matches (one contains the other)
    partial_matches = 0
    for qt in query_tokens:
        for pt in path_tokens:
            if qt != pt and (qt in pt or pt in qt) and len(min(qt, pt, key=len)) >= 3:
                partial_matches += 0.5
    
    # Score based on proportion of query matched
    return (exact_matches + partial_matches) / len(query_tokens)


def validate_path(path: str, taxonomy: List[str]) -> dict:
    """Check if a classification path exists in the taxonomy.
    
    Args:
        path: Pipe-separated path like "Technology|Software|Enterprise Software"
        taxonomy: List of valid taxonomy paths
        
    Returns:
        Dict with 'valid' (bool) and 'similar_paths' (list) if invalid
    """
    if not path:
        return {"valid": False, "hint": "Empty path provided"}
    
    path_normalized = str(path).strip().lower()
    
    for tax_path in taxonomy:
        if tax_path and tax_path.strip().lower() == path_normalized:
            return {"valid": True, "exact_match": tax_path}
    
    # Find similar paths - check each level
    path_parts = path_normalized.split("|")
    similar = []
    scores = []
    
    for tax_path in taxonomy:
        tax_parts = tax_path.lower().split("|")
        # Calculate match score
        score = 0
        for i, (p, t) in enumerate(zip(path_parts, tax_parts)):
            if p == t:
                score += 3  # Exact match at level
            elif p in t or t in p:
                score += 1  # Partial match
        
        if score > 0:
            scores.append((score, tax_path))
    
    # Sort by score descending and take top matches
    scores.sort(key=lambda x: -x[0])
    similar = [s[1] for s in scores[:10]]
    
    return {
        "valid": False,
        "similar_paths": similar[:5],
        "hint": f"Path '{path}' not found. Consider: {similar[:3]}" if similar else f"Path '{path}' not found."
    }


def lookup_paths(query: str, taxonomy: List[str]) -> List[str]:
    """Search taxonomy for paths matching a query using word-level matching.
    
    This tool searches the taxonomy using:
    1. Word tokenization (splits on non-alphanumeric)
    2. Partial word matching (e.g., "telecom" matches "telecommunications")
    3. Scored ranking by relevance
    
    Args:
        query: Search term like "telecom", "security", "medical supplies"
        taxonomy: List of valid taxonomy paths
        
    Returns:
        List of matching taxonomy paths (up to 15)
    """
    query_tokens = _tokenize(query)
    
    if not query_tokens:
        return []
    
    scored_matches: List[Tuple[float, int, str]] = []
    
    for path in taxonomy:
        path_tokens = _tokenize(path)
        score = _word_overlap_score(query_tokens, path_tokens)
        
        # Boost score for deeper paths (more specific)
        depth = len(path.split("|"))
        depth_bonus = depth * 0.1
        
        if score > 0:
            scored_matches.append((score + depth_bonus, -depth, path))
    
    # Sort by score descending, then by depth descending (deeper = more specific)
    scored_matches.sort(key=lambda x: (-x[0], x[1]))
    return [m[2] for m in scored_matches[:15]]


# Global cache for semantic search model and embeddings
_semantic_model: Optional[SentenceTransformer] = None
_taxonomy_embeddings_cache: Dict[str, np.ndarray] = {}
_taxonomy_list_cache: Dict[str, List[str]] = {}


def _get_semantic_model():
    """Get or initialize semantic model for embeddings."""
    global _semantic_model
    if _semantic_model is None and SEMANTIC_AVAILABLE:
        try:
            # Use a lightweight model for fast semantic search
            _semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception:
            # Fallback if model fails to load
            pass
    return _semantic_model


def _get_taxonomy_embeddings(taxonomy: List[str]) -> Optional[np.ndarray]:
    """Get embeddings for taxonomy paths (cached)."""
    model = _get_semantic_model()
    if model is None:
        return None
    
    # Use taxonomy list as cache key
    taxonomy_key = str(sorted(taxonomy))
    
    if taxonomy_key not in _taxonomy_embeddings_cache:
        try:
            embeddings = model.encode(taxonomy, convert_to_numpy=True)
            _taxonomy_embeddings_cache[taxonomy_key] = embeddings
            _taxonomy_list_cache[taxonomy_key] = taxonomy
        except Exception:
            return None
    
    return _taxonomy_embeddings_cache.get(taxonomy_key)


def _semantic_search(query: str, taxonomy: List[str], top_k: int = 15) -> List[Tuple[float, str]]:
    """Perform semantic search using embeddings.
    
    Returns list of (similarity_score, path) tuples sorted by similarity.
    """
    model = _get_semantic_model()
    embeddings = _get_taxonomy_embeddings(taxonomy)
    
    if model is None or embeddings is None:
        return []
    
    try:
        # Encode query
        query_embedding = model.encode([query], convert_to_numpy=True)[0]
        
        # Calculate cosine similarity
        similarities = np.dot(embeddings, query_embedding) / (
            np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # Get top_k most similar
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        return [(float(similarities[i]), taxonomy[i]) for i in top_indices if similarities[i] > 0.1]
    except Exception:
        return []


def lookup_paths(query: str, taxonomy: List[str]) -> List[str]:
    """Search taxonomy for paths matching a query using word-level matching and semantic search.
    
    This tool searches the taxonomy using:
    1. Word tokenization (splits on non-alphanumeric)
    2. Partial word matching (e.g., "telecom" matches "telecommunications")
    3. Semantic matching using embeddings (e.g., "restaurant" matches "meals", "dining" matches "meals")
    4. Scored ranking by relevance
    
    Args:
        query: Search term like "telecom", "restaurant", "medical supplies"
        taxonomy: List of valid taxonomy paths
        
    Returns:
        List of matching taxonomy paths (up to 15)
    """
    # First try word-level matching
    query_tokens = _tokenize(query)
    
    if not query_tokens:
        return []
    
    scored_matches: List[Tuple[float, int, str]] = []
    
    for path in taxonomy:
        path_tokens = _tokenize(path)
        score = _word_overlap_score(query_tokens, path_tokens)
        
        # Boost score for deeper paths (more specific)
        depth = len(path.split("|"))
        depth_bonus = depth * 0.1
        
        if score > 0:
            scored_matches.append((score + depth_bonus, -depth, path))
    
    # Also try semantic search for synonyms
    semantic_results = _semantic_search(query, taxonomy, top_k=10)
    
    # Combine results: word-level matches get higher priority
    # But semantic matches can add synonyms that word-level misses
    word_match_paths = {path for _, _, path in scored_matches}
    
    # Add semantic matches that word-level didn't catch (with lower weight)
    for sem_score, path in semantic_results:
        if path not in word_match_paths:
            # Semantic matches get lower weight than word matches but still included
            depth = len(path.split("|"))
            depth_bonus = depth * 0.05
            # Scale semantic score to be comparable but lower priority
            combined_score = sem_score * 0.5 + depth_bonus
            scored_matches.append((combined_score, -depth, path))
    
    # Sort by score descending, then by depth descending (deeper = more specific)
    scored_matches.sort(key=lambda x: (-x[0], x[1]))
    return [m[2] for m in scored_matches[:15]]


