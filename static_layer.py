"""Static Layer - Entity, Concept, and Term-Definition Knowledge.

Implements the static knowledge layer from the RAG Compliance Checking
Framework (COLING 2025). This layer provides:
- Entity knowledge extraction (organizations, persons, regulatory bodies)
- Concept knowledge graph (hierarchical relationships from frameworks)
- Term-definition extraction from regulatory documents

The static layer feeds background knowledge into the computational layer
for compliance reasoning.
"""

import re
from typing import Optional

import networkx as nx
import spacy

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _SBERT_MODEL = None

    def _get_sbert():
        global _SBERT_MODEL
        if _SBERT_MODEL is None:
            _SBERT_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        return _SBERT_MODEL
except ImportError:
    def _get_sbert():
        return None

try:
    _nlp = spacy.load("en_core_web_sm")
except OSError:
    _nlp = None


# ---------------------------------------------------------------------------
# Term-Definition Extraction
# ---------------------------------------------------------------------------

_DEFINITION_PATTERNS = [
    # 'Term' means definition
    re.compile(
        r"['\u2018\u201C\"]+(.+?)['\u2019\u201D\"]+\s+(?:means?|is\s+defined\s+as|refers?\s+to)\s+(.+?)(?:\.|$)",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Term means definition (no quotes)
    re.compile(
        r"^([A-Z][A-Za-z\s]+?)\s+(?:means?|is\s+defined\s+as|refers?\s+to)\s+(.+?)(?:\.|$)",
        re.IGNORECASE | re.MULTILINE,
    ),
    # (num) "term" means ...
    re.compile(
        r"\(\d+\)\s*['\"\u2018\u201C](.+?)['\"\u2019\u201D]\s+(?:means?|refers?\s+to)\s+(.+?)(?:\.|$)",
        re.IGNORECASE | re.MULTILINE,
    ),
]


def extract_term_definitions(text: str) -> list[dict]:
    """Extract term-definition pairs from regulatory text.

    Uses pattern matching to find definitions of the form:
    - 'Term' means definition.
    - "Term" refers to definition.
    - Term is defined as definition.
    """
    definitions = []
    seen_terms = set()

    for pattern in _DEFINITION_PATTERNS:
        for match in pattern.finditer(text):
            term = match.group(1).strip()
            definition = match.group(2).strip()

            # Clean up
            term = term.strip("'\"'\u2018\u2019\u201C\u201D ")
            definition = definition.rstrip(".")

            term_key = term.lower()
            if term_key in seen_terms:
                continue
            if len(term) < 2 or len(definition) < 5:
                continue

            seen_terms.add(term_key)
            definitions.append({
                "term": term,
                "definition": definition,
            })

    return definitions


# ---------------------------------------------------------------------------
# Entity Knowledge Extraction
# ---------------------------------------------------------------------------

_REGULATORY_ENTITY_TYPES = {
    "ORG": "organization",
    "PERSON": "person",
    "GPE": "jurisdiction",
    "LAW": "regulatory_document",
    "NORP": "category",
}


def extract_entities(text: str) -> list[dict]:
    """Extract named entities from regulatory text using spaCy NER."""
    if _nlp is None:
        return _extract_entities_regex(text)

    doc = _nlp(text)
    entities = []
    seen = set()

    for ent in doc.ents:
        if ent.label_ in _REGULATORY_ENTITY_TYPES:
            key = (ent.text.lower(), ent.label_)
            if key in seen:
                continue
            seen.add(key)
            entities.append({
                "text": ent.text,
                "type": _REGULATORY_ENTITY_TYPES[ent.label_],
            })

    return entities


def _extract_entities_regex(text: str) -> list[dict]:
    """Fallback entity extraction using common regulatory patterns."""
    entities = []

    org_patterns = [
        r"(?:the\s+)?([\w\s]+ Authority)",
        r"(?:the\s+)?([\w\s]+ Commission)",
        r"(?:the\s+)?([\w\s]+ Board)",
    ]

    for pattern in org_patterns:
        for match in re.finditer(pattern, text):
            entities.append({
                "text": match.group(1).strip(),
                "type": "organization",
            })

    return entities


# ---------------------------------------------------------------------------
# Concept Knowledge Graph
# ---------------------------------------------------------------------------

def build_concept_hierarchy(concepts: list[dict]) -> nx.DiGraph:
    """Build a directed graph representing concept hierarchy.

    Each concept dict has: id, text, parent_id (None for root nodes).
    """
    graph = nx.DiGraph()

    for concept in concepts:
        graph.add_node(concept["id"], text=concept["text"])

    for concept in concepts:
        if concept["parent_id"] is not None:
            graph.add_edge(concept["parent_id"], concept["id"], relation="has_subconcept")

    return graph


def get_related_concepts(graph: nx.DiGraph, node_id: int, depth: int = 2) -> list[int]:
    """Get concepts related to a given node within a certain depth."""
    related = set()

    # Get descendants (subconcepts)
    try:
        for successor in nx.bfs_tree(graph, node_id, depth_limit=depth):
            if successor != node_id:
                related.add(successor)
    except nx.NetworkXError:
        pass

    # Get ancestors (parent concepts)
    try:
        for predecessor in nx.ancestors(graph, node_id):
            related.add(predecessor)
    except nx.NetworkXError:
        pass

    return list(related)


# ---------------------------------------------------------------------------
# Static Layer Retrieval
# ---------------------------------------------------------------------------

def retrieve_definitions(
    definitions: list[dict],
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """Retrieve the most relevant term definitions for a query.

    Uses SBERT embeddings for semantic matching, with a word-overlap fallback.
    """
    if not definitions:
        return []

    model = _get_sbert()
    if model is not None:
        return _retrieve_with_sbert(definitions, query, top_k, model)
    return _retrieve_with_overlap(definitions, query, top_k)


def _retrieve_with_sbert(
    definitions: list[dict],
    query: str,
    top_k: int,
    model,
) -> list[dict]:
    """Retrieve definitions using SBERT similarity."""
    texts = [f"{d['term']}: {d['definition']}" for d in definitions]
    all_texts = [query] + texts
    embeddings = model.encode(all_texts, convert_to_numpy=True)

    query_emb = embeddings[0]
    doc_embs = embeddings[1:]

    similarities = np.dot(doc_embs, query_emb) / (
        np.linalg.norm(doc_embs, axis=1) * np.linalg.norm(query_emb)
    )

    ranked_indices = np.argsort(-similarities)[:top_k]
    results = []
    for idx in ranked_indices:
        results.append({
            **definitions[idx],
            "score": float(similarities[idx]),
        })

    return results


def _retrieve_with_overlap(
    definitions: list[dict],
    query: str,
    top_k: int,
) -> list[dict]:
    """Fallback retrieval using word overlap."""
    query_words = set(query.lower().split())
    scored = []

    for defn in definitions:
        def_words = set(f"{defn['term']} {defn['definition']}".lower().split())
        overlap = len(query_words & def_words)
        score = overlap / max(len(query_words | def_words), 1)
        scored.append({**defn, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
