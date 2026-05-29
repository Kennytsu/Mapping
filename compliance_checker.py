"""Computational Layer - Compliance Reasoning via RAG.

Implements the computational layer from the RAG Compliance Checking Framework
(COLING 2025). This layer orchestrates:
- Semantic matching between business process chunks and eventic graph nodes
- Knowledge fusion: combining static (definitions) and dynamic (obligations) knowledge
- LLM prompt construction for compliance reasoning
- Compliance result generation

When no LLM is available, uses a rule-based heuristic for compliance judgment.
"""

import re
from typing import Optional

import networkx as nx

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
    np = None

    def _get_sbert():
        return None

from dynamic_layer import extract_deontic_propositions, build_eventic_graph, chunk_text
from static_layer import extract_term_definitions


# ---------------------------------------------------------------------------
# Semantic Matching
# ---------------------------------------------------------------------------

def match_chunk_to_graph(
    chunk: str,
    graph: nx.DiGraph,
    threshold: float = 0.3,
) -> list[dict]:
    """Match a business process chunk to eventic graph nodes by semantic similarity.

    Returns nodes above the similarity threshold, ranked by score.
    """
    model = _get_sbert()
    action_nodes = [(nid, data) for nid, data in graph.nodes(data=True)
                    if data.get("node_type") == "action"]

    if not action_nodes:
        return []

    if model is not None:
        return _match_with_sbert(chunk, action_nodes, graph, threshold, model)
    return _match_with_overlap(chunk, action_nodes, graph, threshold)


def _match_with_sbert(
    chunk: str,
    action_nodes: list,
    graph: nx.DiGraph,
    threshold: float,
    model,
) -> list[dict]:
    """Match using SBERT embeddings."""
    node_texts = [data["text"] for _, data in action_nodes]
    all_texts = [chunk] + node_texts
    embeddings = model.encode(all_texts, convert_to_numpy=True)

    chunk_emb = embeddings[0]
    node_embs = embeddings[1:]

    norms = np.linalg.norm(node_embs, axis=1) * np.linalg.norm(chunk_emb)
    norms[norms == 0] = 1e-10
    similarities = np.dot(node_embs, chunk_emb) / norms

    results = []
    for i, (node_id, data) in enumerate(action_nodes):
        score = float(similarities[i])
        if score >= threshold:
            # Find what relation this action has
            in_edges = list(graph.in_edges(node_id, data=True))
            relation = in_edges[0][2].get("relation", "") if in_edges else ""
            agent_id = in_edges[0][0] if in_edges else None
            agent_text = graph.nodes[agent_id].get("text", "") if agent_id else ""

            results.append({
                "node_id": node_id,
                "text": data["text"],
                "score": score,
                "relation": relation,
                "agent": agent_text,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _match_with_overlap(
    chunk: str,
    action_nodes: list,
    graph: nx.DiGraph,
    threshold: float,
) -> list[dict]:
    """Fallback matching using word overlap."""
    chunk_words = set(chunk.lower().split())
    results = []

    for node_id, data in action_nodes:
        node_words = set(data["text"].lower().split())
        overlap = len(chunk_words & node_words)
        union = len(chunk_words | node_words)
        score = overlap / max(union, 1)

        if score >= threshold:
            in_edges = list(graph.in_edges(node_id, data=True))
            relation = in_edges[0][2].get("relation", "") if in_edges else ""
            agent_id = in_edges[0][0] if in_edges else None
            agent_text = graph.nodes[agent_id].get("text", "") if agent_id else ""

            results.append({
                "node_id": node_id,
                "text": data["text"],
                "score": score,
                "relation": relation,
                "agent": agent_text,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Knowledge Fusion
# ---------------------------------------------------------------------------

def fuse_knowledge(
    static_knowledge: list[dict],
    dynamic_knowledge: list[dict],
) -> dict:
    """Fuse static (definitions) and dynamic (obligations/prohibitions) knowledge.

    Returns a unified knowledge dict for prompt construction.
    """
    definitions = []
    obligations = []
    prohibitions = []
    permissions = []

    for item in static_knowledge:
        definitions.append({
            "term": item.get("term", ""),
            "definition": item.get("definition", ""),
        })

    for item in dynamic_knowledge:
        relation = item.get("relation", "")
        entry = {
            "text": item.get("text", ""),
            "relation": relation,
            "agent": item.get("agent", ""),
        }
        if relation == "duty":
            obligations.append(entry)
        elif relation == "prohibited":
            prohibitions.append(entry)
        elif relation == "right":
            permissions.append(entry)
        else:
            obligations.append(entry)

    return {
        "definitions": definitions,
        "obligations": obligations,
        "prohibitions": prohibitions,
        "permissions": permissions,
    }


# ---------------------------------------------------------------------------
# LLM Prompt Template
# ---------------------------------------------------------------------------

_COMPLIANCE_PROMPT_TEMPLATE = """You are a compliance analysis expert. Analyze whether the following business process statement complies with the relevant regulatory requirements.

## Business Process Statement
{chunk}

## Regulation Knowledge

### Relevant Definitions
{definitions_section}

### Obligations (MUST do)
{obligations_section}

### Prohibitions (MUST NOT do)
{prohibitions_section}

### Permissions (MAY do)
{permissions_section}

## Task
Based on the regulation knowledge above, determine if the business process statement is:
- **compliant**: The statement aligns with regulatory requirements
- **non_compliant**: The statement violates one or more regulatory requirements
- **undetermined**: Insufficient information to make a clear judgment

Provide your judgment and a brief explanation.

## Response Format
Judgment: [compliant/non_compliant/undetermined]
Explanation: [Your reasoning]"""


def build_compliance_prompt(chunk: str, knowledge: dict) -> str:
    """Build a compliance reasoning prompt for an LLM.

    Follows the prompt structure from Paper 2 (COLING 2025).
    """
    # Format definitions
    defs = knowledge.get("definitions", [])
    if defs:
        definitions_section = "\n".join(
            f"- **{d['term']}**: {d['definition']}" for d in defs
        )
    else:
        definitions_section = "No specific definitions available."

    # Format obligations
    obligations = knowledge.get("obligations", [])
    if obligations:
        obligations_section = "\n".join(
            f"- {o.get('agent', 'Entity')} must: {o['text']}" for o in obligations
        )
    else:
        obligations_section = "No specific obligations identified."

    # Format prohibitions
    prohibitions = knowledge.get("prohibitions", [])
    if prohibitions:
        prohibitions_section = "\n".join(
            f"- {p.get('agent', 'Entity')} must not: {p['text']}" for p in prohibitions
        )
    else:
        prohibitions_section = "No specific prohibitions identified."

    # Format permissions
    permissions = knowledge.get("permissions", [])
    if permissions:
        permissions_section = "\n".join(
            f"- {p.get('agent', 'Entity')} may: {p['text']}" for p in permissions
        )
    else:
        permissions_section = "No specific permissions identified."

    return _COMPLIANCE_PROMPT_TEMPLATE.format(
        chunk=chunk,
        definitions_section=definitions_section,
        obligations_section=obligations_section,
        prohibitions_section=prohibitions_section,
        permissions_section=permissions_section,
    )


# ---------------------------------------------------------------------------
# Compliance Reasoning (Rule-based fallback when no LLM available)
# ---------------------------------------------------------------------------

def check_compliance(
    business_text: str,
    regulation_text: str,
    llm_client=None,
) -> list[dict]:
    """Run full compliance check pipeline.

    1. Extract deontic propositions from regulation
    2. Build eventic graph
    3. Extract definitions from regulation
    4. Chunk business text
    5. Match each chunk against graph
    6. Fuse knowledge and reason about compliance

    If llm_client is provided, uses LLM for reasoning.
    Otherwise, uses rule-based heuristics.
    """
    if not business_text.strip():
        return []

    # Step 1-2: Dynamic layer
    propositions = extract_deontic_propositions(regulation_text)
    graph = build_eventic_graph(propositions)

    # Step 3: Static layer
    definitions = extract_term_definitions(regulation_text)

    # Step 4: Chunk business text
    chunks = chunk_text(business_text)

    results = []
    for chunk in chunks:
        if len(chunk.strip()) < 10:
            continue

        # Step 5: Match chunk to graph
        matches = match_chunk_to_graph(chunk, graph, threshold=0.2)

        # Step 6: Fuse knowledge
        static_results = _match_definitions(chunk, definitions)
        knowledge = fuse_knowledge(static_results, matches)

        # Step 7: Reason about compliance
        if llm_client is not None:
            prompt = build_compliance_prompt(chunk, knowledge)
            result = _reason_with_llm(prompt, llm_client)
        else:
            result = _reason_rule_based(chunk, knowledge, matches)

        results.append({
            "chunk": chunk,
            "result": result["judgment"],
            "explanation": result["explanation"],
            "matched_obligations": [m["text"] for m in matches if m.get("relation") == "duty"],
            "matched_prohibitions": [m["text"] for m in matches if m.get("relation") == "prohibited"],
        })

    return results


def _match_definitions(chunk: str, definitions: list[dict]) -> list[dict]:
    """Find definitions relevant to a chunk."""
    if not definitions:
        return []

    model = _get_sbert()
    if model is not None:
        texts = [f"{d['term']}: {d['definition']}" for d in definitions]
        all_texts = [chunk] + texts
        embeddings = model.encode(all_texts, convert_to_numpy=True)
        query_emb = embeddings[0]
        doc_embs = embeddings[1:]
        norms = np.linalg.norm(doc_embs, axis=1) * np.linalg.norm(query_emb)
        norms[norms == 0] = 1e-10
        similarities = np.dot(doc_embs, query_emb) / norms
        results = []
        for i, score in enumerate(similarities):
            if score > 0.3:
                results.append({**definitions[i], "score": float(score)})
        return sorted(results, key=lambda x: x["score"], reverse=True)[:3]

    # Fallback
    chunk_words = set(chunk.lower().split())
    results = []
    for d in definitions:
        term_words = set(d["term"].lower().split())
        if term_words & chunk_words:
            results.append({**d, "score": 0.5})
    return results


def _reason_with_llm(prompt: str, llm_client) -> dict:
    """Use LLM for compliance reasoning."""
    try:
        response = llm_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.choices[0].message.content

        judgment = "undetermined"
        explanation = content

        judgment_match = re.search(
            r"Judgment:\s*(compliant|non_compliant|undetermined)",
            content, re.IGNORECASE,
        )
        if judgment_match:
            judgment = judgment_match.group(1).lower()

        explanation_match = re.search(
            r"Explanation:\s*(.+)",
            content, re.IGNORECASE | re.DOTALL,
        )
        if explanation_match:
            explanation = explanation_match.group(1).strip()

        return {"judgment": judgment, "explanation": explanation}
    except Exception as e:
        return {"judgment": "undetermined", "explanation": f"LLM error: {str(e)}"}


def _reason_rule_based(chunk: str, knowledge: dict, matches: list[dict]) -> dict:
    """Rule-based compliance reasoning when no LLM is available.

    Heuristic approach:
    - If chunk matches a prohibition with high score -> non_compliant
    - If chunk matches an obligation and seems aligned -> compliant
    - Otherwise -> undetermined
    """
    chunk_lower = chunk.lower()
    prohibitions = knowledge.get("prohibitions", [])
    obligations = knowledge.get("obligations", [])

    # Check for prohibition violations
    for match in matches:
        if match.get("relation") == "prohibited" and match.get("score", 0) > 0.5:
            action_words = set(match["text"].lower().split())
            chunk_words = set(chunk_lower.split())
            overlap = action_words & chunk_words
            if len(overlap) >= 2:
                return {
                    "judgment": "non_compliant",
                    "explanation": (
                        f"Business process appears to violate prohibition: "
                        f"'{match['text']}'. The chunk mentions similar actions."
                    ),
                }

    # Check for obligation alignment
    for match in matches:
        if match.get("relation") == "duty" and match.get("score", 0) > 0.5:
            action_words = set(match["text"].lower().split())
            chunk_words = set(chunk_lower.split())
            overlap = action_words & chunk_words

            # Check if the chunk actually fulfills the obligation
            positive_indicators = {"use", "implement", "ensure", "protect", "provide", "maintain"}
            if overlap and (chunk_words & positive_indicators):
                return {
                    "judgment": "compliant",
                    "explanation": (
                        f"Business process appears to fulfill obligation: "
                        f"'{match['text']}'. Positive alignment detected."
                    ),
                }

    # Check for sharing/collecting without consent mention
    sharing_words = {"share", "shares", "sharing", "shared", "disclose", "transfer"}
    consent_words = {"consent", "permission", "agree", "agreed", "authorize", "authorized"}
    if chunk_words := set(chunk_lower.split()):
        if chunk_words & sharing_words and not (chunk_words & consent_words):
            if prohibitions:
                return {
                    "judgment": "non_compliant",
                    "explanation": (
                        "Business process involves data sharing without explicit "
                        "mention of consent, which may conflict with regulations."
                    ),
                }

    return {
        "judgment": "undetermined",
        "explanation": "Insufficient information for a definitive compliance judgment.",
    }
