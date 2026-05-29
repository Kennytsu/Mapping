"""Dynamic Layer - Eventic Graph and Chunk Vectors.

Implements the dynamic knowledge layer from the RAG Compliance Checking
Framework (COLING 2025). This layer handles:
- Algorithm 1: Unsupervised deontic proposition extraction
- Eventic graph construction (agents, deontic words, actions, states)
- Business process text chunking with SBERT embeddings

The eventic graph captures regulatory obligations as a knowledge graph,
while chunk vectors enable semantic retrieval of business process content.
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
    np = None

try:
    _nlp = spacy.load("en_core_web_sm")
except OSError:
    _nlp = None


# ---------------------------------------------------------------------------
# Deontic words and patterns
# ---------------------------------------------------------------------------

OBLIGATION_WORDS = {"shall", "must", "should", "ought to", "is required to", "has to"}
PROHIBITION_WORDS = {"shall not", "must not", "should not", "may not", "cannot", "is prohibited from"}
PERMISSION_WORDS = {"may", "can", "could", "is permitted to", "is allowed to"}


# ---------------------------------------------------------------------------
# Algorithm 1: Unsupervised Deontic Proposition Extraction
# ---------------------------------------------------------------------------

def extract_deontic_propositions(text: str) -> list[dict]:
    """Extract deontic propositions from regulatory text (Algorithm 1).

    For each sentence containing a deontic word, extracts:
    - agent: the subject performing or constrained by the action
    - deontic_word: the modal/deontic operator (shall, must, may, etc.)
    - action: what must/may/must-not be done
    - state: obligation | prohibition | permission

    Based on Algorithm 1 from Paper 2 (COLING 2025).
    """
    sentences = _split_sentences(text)
    propositions = []

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 10:
            continue

        props = _extract_from_sentence(sentence)
        propositions.extend(props)

    return propositions


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in sentences if s.strip()]


def _extract_from_sentence(sentence: str) -> list[dict]:
    """Extract deontic propositions from a single sentence."""
    propositions = []
    sentence_lower = sentence.lower()

    # Check for prohibition first (multi-word patterns)
    for word in sorted(PROHIBITION_WORDS, key=len, reverse=True):
        if word in sentence_lower:
            prop = _parse_deontic_sentence(sentence, word, "prohibition")
            if prop:
                propositions.append(prop)
            return propositions

    # Check obligations
    for word in OBLIGATION_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", sentence_lower):
            prop = _parse_deontic_sentence(sentence, word, "obligation")
            if prop:
                propositions.append(prop)
            return propositions

    # Check permissions
    for word in PERMISSION_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", sentence_lower):
            prop = _parse_deontic_sentence(sentence, word, "permission")
            if prop:
                propositions.append(prop)
            return propositions

    return propositions


def _parse_deontic_sentence(sentence: str, deontic_word: str, state: str) -> Optional[dict]:
    """Parse agent and action from a sentence given the deontic word."""
    if _nlp is not None:
        return _parse_with_spacy(sentence, deontic_word, state)
    return _parse_with_regex(sentence, deontic_word, state)


def _parse_with_spacy(sentence: str, deontic_word: str, state: str) -> Optional[dict]:
    """Use spaCy dependency parsing to extract agent and action."""
    doc = _nlp(sentence)

    agent = ""
    action = ""

    # Find the main verb after the deontic word
    deontic_idx = sentence.lower().find(deontic_word)
    if deontic_idx == -1:
        return None

    after_deontic = sentence[deontic_idx + len(deontic_word):].strip()

    # Agent is the subject before the deontic word
    before_deontic = sentence[:deontic_idx].strip()
    agent = before_deontic

    # Clean agent
    agent = re.sub(r"^\s*(the|a|an)\s+", "", agent, flags=re.IGNORECASE).strip()
    if agent.endswith(","):
        agent = agent[:-1].strip()

    # Action is everything after deontic word (simplified)
    action = after_deontic.rstrip(".")

    # Try to use spaCy for better extraction
    for token in doc:
        if token.dep_ in ("nsubj", "nsubjpass") and token.idx < deontic_idx:
            subtree = " ".join(t.text for t in token.subtree)
            # Remove determiners at start
            subtree = re.sub(r"^(the|a|an)\s+", "", subtree, flags=re.IGNORECASE)
            if subtree:
                agent = subtree

    if not agent or not action:
        return None

    return {
        "agent": agent,
        "deontic_word": deontic_word,
        "action": action,
        "state": state,
    }


def _parse_with_regex(sentence: str, deontic_word: str, state: str) -> Optional[dict]:
    """Regex fallback for deontic sentence parsing."""
    pattern = re.compile(
        rf"(.+?)\s+{re.escape(deontic_word)}\s+(.+)",
        re.IGNORECASE,
    )
    match = pattern.match(sentence)
    if not match:
        return None

    agent = match.group(1).strip()
    action = match.group(2).strip().rstrip(".")

    agent = re.sub(r"^(the|a|an)\s+", "", agent, flags=re.IGNORECASE).strip()

    if not agent or not action:
        return None

    return {
        "agent": agent,
        "deontic_word": deontic_word,
        "action": action,
        "state": state,
    }


# ---------------------------------------------------------------------------
# Eventic Graph Construction
# ---------------------------------------------------------------------------

def build_eventic_graph(propositions: list[dict]) -> nx.DiGraph:
    """Build an eventic graph from deontic propositions.

    Graph structure (from Paper 2):
    - Agent nodes (organizations, persons)
    - Action nodes (what is being done)
    - Deontic edges: duty, prohibited, right (between agent and action)
    """
    graph = nx.DiGraph()
    node_counter = 0

    agent_nodes = {}
    action_nodes = {}

    for prop in propositions:
        agent_text = prop["agent"].lower().strip()
        action_text = prop["action"].lower().strip()
        state = prop["state"]

        # Get or create agent node
        if agent_text not in agent_nodes:
            node_counter += 1
            agent_nodes[agent_text] = node_counter
            graph.add_node(node_counter, text=prop["agent"], node_type="person")

        # Get or create action node
        if action_text not in action_nodes:
            node_counter += 1
            action_nodes[action_text] = node_counter
            graph.add_node(node_counter, text=prop["action"], node_type="action")

        agent_id = agent_nodes[agent_text]
        action_id = action_nodes[action_text]

        # Map state to relation type
        relation_map = {
            "obligation": "duty",
            "prohibition": "prohibited",
            "permission": "right",
        }
        relation = relation_map.get(state, "duty")

        graph.add_edge(agent_id, action_id, relation=relation, deontic_word=prop["deontic_word"])

    return graph


def serialize_graph(graph: nx.DiGraph) -> dict:
    """Serialize a NetworkX graph for storage/transmission."""
    nodes = []
    for node_id, data in graph.nodes(data=True):
        nodes.append({
            "id": node_id,
            "text": data.get("text", ""),
            "node_type": data.get("node_type", ""),
        })

    edges = []
    for src, tgt, data in graph.edges(data=True):
        edges.append({
            "source": src,
            "target": tgt,
            "relation": data.get("relation", ""),
            "deontic_word": data.get("deontic_word", ""),
        })

    return {"nodes": nodes, "edges": edges}


def deserialize_graph(data: dict) -> nx.DiGraph:
    """Reconstruct a NetworkX graph from serialized form."""
    graph = nx.DiGraph()

    for node in data.get("nodes", []):
        graph.add_node(node["id"], text=node.get("text", ""), node_type=node.get("node_type", ""))

    for edge in data.get("edges", []):
        graph.add_edge(
            edge["source"], edge["target"],
            relation=edge.get("relation", ""),
            deontic_word=edge.get("deontic_word", ""),
        )

    return graph


# ---------------------------------------------------------------------------
# Text Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, max_chunk_size: int = 300, overlap: int = 0) -> list[str]:
    """Chunk business process text into manageable segments.

    Tries to split at sentence boundaries while respecting max_chunk_size.
    """
    sentences = _split_sentences(text)
    chunks = []
    current_chunk = []
    current_size = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sent_len = len(sentence)

        if current_size + sent_len > max_chunk_size and current_chunk:
            chunk_text_str = " ".join(current_chunk)
            chunks.append(chunk_text_str)

            if overlap > 0:
                # Keep some overlap from previous chunk
                overlap_text = chunk_text_str[-overlap:] if len(chunk_text_str) > overlap else chunk_text_str
                current_chunk = [overlap_text]
                current_size = len(overlap_text)
            else:
                current_chunk = []
                current_size = 0

        current_chunk.append(sentence)
        current_size += sent_len + 1  # +1 for space

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


# ---------------------------------------------------------------------------
# Chunk Embedding
# ---------------------------------------------------------------------------

def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed text chunks using SBERT for vector search."""
    model = _get_sbert()
    if model is not None:
        embeddings = model.encode(chunks, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    # Fallback: simple word-frequency vectors
    return [_simple_embed(chunk) for chunk in chunks]


def _simple_embed(text: str) -> list[float]:
    """Fallback embedding using bag-of-words."""
    words = set(text.lower().split())
    vocab = ["data", "personal", "user", "collect", "share", "process",
             "consent", "security", "access", "store", "protect",
             "information", "controller", "subject", "authority",
             "transfer", "health", "location", "service", "measure"]
    return [1.0 if w in words else 0.0 for w in vocab]
