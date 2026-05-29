"""Tests for the Dynamic Layer (Phase 3 - RAG framework).

The dynamic layer handles:
- Algorithm 1: Unsupervised deontic proposition extraction (from Paper 2)
- Eventic graph construction from extracted propositions
- Business process text chunking and SBERT embedding
"""

import pytest


class TestDeonticPropositionExtraction:
    """Test Algorithm 1 from the RAG Compliance Checking paper.

    The algorithm extracts (Agent, Deontic Word, Action) triples
    from regulatory text without supervision.
    """

    def test_extract_deontic_propositions_basic(self):
        from dynamic_layer import extract_deontic_propositions
        text = "The controller shall implement appropriate technical measures."
        props = extract_deontic_propositions(text)
        assert len(props) >= 1
        prop = props[0]
        assert "agent" in prop
        assert "deontic_word" in prop
        assert "action" in prop

    def test_obligation_extraction(self):
        from dynamic_layer import extract_deontic_propositions
        text = "The data processor must ensure the security of personal data."
        props = extract_deontic_propositions(text)
        assert len(props) >= 1
        assert any("must" in p["deontic_word"].lower() for p in props)

    def test_prohibition_extraction(self):
        from dynamic_layer import extract_deontic_propositions
        text = "The organization shall not transfer personal data to third countries."
        props = extract_deontic_propositions(text)
        assert len(props) >= 1
        assert any("not" in p["deontic_word"].lower() for p in props)

    def test_permission_extraction(self):
        from dynamic_layer import extract_deontic_propositions
        text = "The data subject may withdraw consent at any time."
        props = extract_deontic_propositions(text)
        assert len(props) >= 1
        assert any("may" in p["deontic_word"].lower() for p in props)

    def test_multiple_propositions(self, gdpr_text):
        from dynamic_layer import extract_deontic_propositions
        props = extract_deontic_propositions(gdpr_text)
        assert len(props) >= 2

    def test_proposition_has_state(self):
        from dynamic_layer import extract_deontic_propositions
        text = "The controller shall maintain records of processing activities."
        props = extract_deontic_propositions(text)
        if props:
            assert "state" in props[0]


class TestEventicGraphConstruction:
    """Test eventic graph building from deontic propositions."""

    def test_build_graph_from_propositions(self):
        from dynamic_layer import build_eventic_graph
        propositions = [
            {"agent": "controller", "deontic_word": "shall", "action": "implement measures", "state": "obligation"},
            {"agent": "processor", "deontic_word": "must", "action": "ensure security", "state": "obligation"},
        ]
        graph = build_eventic_graph(propositions)
        assert graph is not None
        assert len(graph.nodes) >= 4  # at least agents + actions

    def test_graph_has_deontic_edges(self):
        from dynamic_layer import build_eventic_graph
        propositions = [
            {"agent": "controller", "deontic_word": "shall", "action": "protect data", "state": "obligation"},
        ]
        graph = build_eventic_graph(propositions)
        edges = list(graph.edges(data=True))
        deontic_edges = [e for e in edges if e[2].get("relation") in ("duty", "prohibited", "right")]
        assert len(deontic_edges) >= 1

    def test_graph_nodes_have_types(self):
        from dynamic_layer import build_eventic_graph
        propositions = [
            {"agent": "data subject", "deontic_word": "may", "action": "withdraw consent", "state": "permission"},
        ]
        graph = build_eventic_graph(propositions)
        for _, data in graph.nodes(data=True):
            assert "node_type" in data

    def test_graph_serialization(self):
        from dynamic_layer import build_eventic_graph, serialize_graph
        propositions = [
            {"agent": "controller", "deontic_word": "shall", "action": "notify authority", "state": "obligation"},
        ]
        graph = build_eventic_graph(propositions)
        serialized = serialize_graph(graph)
        assert "nodes" in serialized
        assert "edges" in serialized
        assert len(serialized["nodes"]) >= 2


class TestTextChunking:
    """Test business process text chunking."""

    def test_chunk_text_returns_list(self, sample_business_process):
        from dynamic_layer import chunk_text
        chunks = chunk_text(sample_business_process)
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    def test_chunk_text_preserves_content(self, sample_business_process):
        from dynamic_layer import chunk_text
        chunks = chunk_text(sample_business_process)
        combined = " ".join(chunks)
        assert "health data" in combined or "collect" in combined

    def test_chunk_text_respects_max_size(self):
        from dynamic_layer import chunk_text
        long_text = "This is a test sentence. " * 200
        chunks = chunk_text(long_text, max_chunk_size=100)
        for chunk in chunks:
            assert len(chunk) <= 150  # some tolerance for sentence boundaries

    def test_chunk_text_with_overlap(self, sample_business_process):
        from dynamic_layer import chunk_text
        chunks = chunk_text(sample_business_process, overlap=20)
        assert isinstance(chunks, list)


class TestChunkEmbedding:
    """Test SBERT embedding of business process chunks."""

    def test_embed_chunks_returns_vectors(self):
        from dynamic_layer import embed_chunks
        chunks = ["We collect user data for analytics.", "Data is stored securely."]
        embeddings = embed_chunks(chunks)
        assert len(embeddings) == 2
        assert len(embeddings[0]) > 0

    def test_embed_single_chunk(self):
        from dynamic_layer import embed_chunks
        chunks = ["The organization processes health data."]
        embeddings = embed_chunks(chunks)
        assert len(embeddings) == 1

    def test_similar_chunks_closer_embedding(self):
        from dynamic_layer import embed_chunks
        import numpy as np
        chunks = [
            "We collect personal health data from users.",
            "User health information is gathered by our service.",
            "The fiscal year budget has been approved.",
        ]
        embeddings = embed_chunks(chunks)
        # First two should be more similar to each other than to the third
        sim_01 = np.dot(embeddings[0], embeddings[1]) / (
            np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]))
        sim_02 = np.dot(embeddings[0], embeddings[2]) / (
            np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[2]))
        assert sim_01 > sim_02
