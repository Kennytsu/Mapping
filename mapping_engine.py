"""Mapping Engine - Automatic Regulation-to-Regulation Mapping.

Core functionality that connects the ARC tuple extraction and SBERT
similarity to the existing mapping database. Takes two regulatory texts,
extracts structured tuples from both, and finds semantically matching
pairs above a configurable threshold.

This is the bridge between the NLP pipeline and the mapping tool's
existing control-mapping infrastructure.
"""

from arc_pipeline import process_regulation, phrase_similarity


def generate_mappings(
    source_text: str,
    target_text: str,
    threshold: float = 0.5,
    top_k_per_source: int = 3,
) -> list[dict]:
    """Generate automatic mapping suggestions between two regulation texts.

    1. Extracts ARC tuples from both regulations
    2. Falls back to sentence-level comparison if tuple extraction is sparse
    3. Computes pairwise similarity between all source-target statement pairs
    4. Returns pairs above threshold, ranked by similarity

    Args:
        source_text: Full text of the source regulation
        target_text: Full text of the target regulation
        threshold: Minimum similarity score to include (0.0 - 1.0)
        top_k_per_source: Max matches to keep per source statement

    Returns:
        List of mapping dicts sorted by similarity (highest first)
    """
    source_tuples = process_regulation(source_text)
    target_tuples = process_regulation(target_text)

    # Get statements from tuples, or fall back to sentence splitting
    source_statements = _deduplicate_statements(source_tuples)
    target_statements = _deduplicate_statements(target_tuples)

    # Fallback: if tuple extraction didn't capture enough, use raw sentences
    if not source_statements:
        source_statements = _split_to_statements(source_text)
    if not target_statements:
        target_statements = _split_to_statements(target_text)

    if not source_statements or not target_statements:
        return []

    # Compute pairwise similarities
    all_pairs = []
    for s_stmt, s_type in source_statements:
        best_matches = []
        for t_stmt, t_type in target_statements:
            sim = phrase_similarity(s_stmt, t_stmt)
            if sim >= threshold:
                best_matches.append({
                    "source_statement": s_stmt,
                    "target_statement": t_stmt,
                    "similarity": round(sim, 4),
                    "source_tuple_type": s_type,
                    "target_tuple_type": t_type,
                })

        # Keep only top-k per source
        best_matches.sort(key=lambda x: x["similarity"], reverse=True)
        all_pairs.extend(best_matches[:top_k_per_source])

    # Deduplicate and sort globally
    seen = set()
    unique_pairs = []
    for pair in all_pairs:
        key = (pair["source_statement"], pair["target_statement"])
        if key not in seen:
            seen.add(key)
            unique_pairs.append(pair)

    unique_pairs.sort(key=lambda x: x["similarity"], reverse=True)
    return unique_pairs


def format_as_suggestions(
    mappings: list[dict],
    source_reg_name: str = "",
    target_reg_name: str = "",
) -> list[dict]:
    """Format mapping results as persistable suggestions for the mapping DB.

    Converts similarity-based mapping pairs into the format expected by
    the existing Mapping table (confidence, source_type, notes).
    """
    suggestions = []
    for m in mappings:
        suggestions.append({
            "source_statement": m["source_statement"],
            "target_statement": m["target_statement"],
            "confidence": m["similarity"],
            "similarity": m["similarity"],
            "source_type": "ai_suggested",
            "source_document": f"AI mapping: {source_reg_name} -> {target_reg_name}",
            "notes": (
                f"Auto-generated mapping ({m['source_tuple_type']} -> {m['target_tuple_type']}). "
                f"Similarity: {m['similarity']:.2f}"
            ),
        })
    return suggestions


def _deduplicate_statements(tuples: list[dict]) -> list[tuple[str, str]]:
    """Get unique (statement, type) pairs from extracted tuples."""
    seen = set()
    results = []
    for t in tuples:
        stmt = t.get("source_statement", "").strip()
        if stmt and stmt not in seen:
            seen.add(stmt)
            results.append((stmt, t.get("tuple_type", "")))
    return results


def _split_to_statements(text: str) -> list[tuple[str, str]]:
    """Split raw text into statements as a fallback when tuple extraction is sparse."""
    import re
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    results = []
    seen = set()
    for s in sentences:
        s = s.strip()
        if len(s) >= 15 and s not in seen:
            seen.add(s)
            results.append((s, "statement"))
    return results
