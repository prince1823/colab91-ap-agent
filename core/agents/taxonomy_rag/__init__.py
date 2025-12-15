"""Taxonomy RAG (Retrieval-Augmented Generation) module for efficient taxonomy path retrieval.

Uses FAISS vector database for fast semantic search combined with keyword matching
for hybrid retrieval of relevant taxonomy paths.
"""

from core.agents.taxonomy_rag.taxonomy_retriever import TaxonomyRetriever, RetrievalResult

__all__ = ["TaxonomyRetriever", "RetrievalResult"]

