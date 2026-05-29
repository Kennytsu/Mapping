"""Tests for the Computational Layer (Phase 3 - RAG framework).

The computational layer handles:
- Semantic matching between business chunks and regulatory knowledge
- Knowledge fusion from static + dynamic layers
- LLM prompt template construction for compliance reasoning
- Compliance result generation
"""

import pytest


class TestSemanticMatching:
    """Test semantic matching between chunks and graph nodes."""

    def test_match_chunk_to_graph(self):
        from compliance_checker import match_chunk_to_graph
        import networkx as nx

        graph = nx.DiGraph()
        graph.add_node(1, text="collect personal data", node_type="action")
        graph.add_node(2, text="controller", node_type="person")
        graph.add_edge(2, 1, relation="duty")

        chunk = "We collect basic health data that you provide."
        matches = match_chunk_to_graph(chunk, graph)
        assert isinstance(matches, list)
        assert len(matches) >= 1

    def test_match_returns_scored_results(self):
        from compliance_checker import match_chunk_to_graph
        import networkx as nx

        graph = nx.DiGraph()
        graph.add_node(1, text="share data with third parties", node_type="action")
        graph.add_node(2, text="encrypt personal data", node_type="action")
        graph.add_node(3, text="organization", node_type="person")
        graph.add_edge(3, 1, relation="prohibited")
        graph.add_edge(3, 2, relation="duty")

        chunk = "We may share your location information with partners."
        matches = match_chunk_to_graph(chunk, graph)
        for m in matches:
            assert "node_id" in m
            assert "score" in m
            assert "text" in m

    def test_threshold_filtering(self):
        from compliance_checker import match_chunk_to_graph
        import networkx as nx

        graph = nx.DiGraph()
        graph.add_node(1, text="delete all records after termination", node_type="action")
        graph.add_node(2, text="processor", node_type="person")
        graph.add_edge(2, 1, relation="duty")

        chunk = "The fiscal year budget has been approved by the board."
        matches = match_chunk_to_graph(chunk, graph, threshold=0.7)
        # Unrelated chunk should have few/no matches above threshold
        assert len(matches) == 0 or all(m["score"] < 0.9 for m in matches)


class TestKnowledgeFusion:
    """Test knowledge fusion from static and dynamic layers."""

    def test_fuse_knowledge(self):
        from compliance_checker import fuse_knowledge
        static_knowledge = [
            {"term": "personal data", "definition": "any information relating to an identified natural person", "score": 0.9},
        ]
        dynamic_knowledge = [
            {"node_id": 1, "text": "collect personal data", "score": 0.85, "relation": "duty", "agent": "controller"},
        ]
        fused = fuse_knowledge(static_knowledge, dynamic_knowledge)
        assert isinstance(fused, dict)
        assert "definitions" in fused
        assert "obligations" in fused

    def test_fuse_empty_knowledge(self):
        from compliance_checker import fuse_knowledge
        fused = fuse_knowledge([], [])
        assert isinstance(fused, dict)
        assert fused["definitions"] == []
        assert fused["obligations"] == []


class TestPromptTemplate:
    """Test LLM prompt template construction for compliance reasoning."""

    def test_build_prompt_has_required_sections(self):
        from compliance_checker import build_compliance_prompt
        chunk = "We collect user health data for analytics purposes."
        knowledge = {
            "definitions": [{"term": "personal data", "definition": "info about a person"}],
            "obligations": [{"text": "collect personal data", "relation": "duty", "agent": "controller"}],
            "prohibitions": [],
            "permissions": [],
        }
        prompt = build_compliance_prompt(chunk, knowledge)
        assert "Regulation Knowledge" in prompt or "regulation" in prompt.lower()
        assert chunk in prompt
        assert "personal data" in prompt

    def test_prompt_includes_judgment_instruction(self):
        from compliance_checker import build_compliance_prompt
        chunk = "We share user data with partners."
        knowledge = {
            "definitions": [],
            "obligations": [{"text": "protect data", "relation": "duty", "agent": "controller"}],
            "prohibitions": [{"text": "share data with third parties", "relation": "prohibited", "agent": "organization"}],
            "permissions": [],
        }
        prompt = build_compliance_prompt(chunk, knowledge)
        assert "compliant" in prompt.lower() or "compliance" in prompt.lower()

    def test_prompt_format(self):
        from compliance_checker import build_compliance_prompt
        chunk = "Test chunk."
        knowledge = {"definitions": [], "obligations": [], "prohibitions": [], "permissions": []}
        prompt = build_compliance_prompt(chunk, knowledge)
        assert isinstance(prompt, str)
        assert len(prompt) > 50


class TestComplianceReasoning:
    """Test the full compliance reasoning pipeline."""

    def test_check_compliance_returns_result(self, gdpr_text, sample_business_process):
        from compliance_checker import check_compliance
        result = check_compliance(
            business_text=sample_business_process,
            regulation_text=gdpr_text,
        )
        assert isinstance(result, list)
        for r in result:
            assert "chunk" in r
            assert "result" in r
            assert r["result"] in ("compliant", "non_compliant", "undetermined")
            assert "explanation" in r

    def test_compliant_chunk_detected(self):
        from compliance_checker import check_compliance
        regulation = "Organizations must use security measures to protect personal data."
        business = "We use industry-standard security measures to protect your data from unauthorized access."
        results = check_compliance(business_text=business, regulation_text=regulation)
        assert len(results) >= 1
        # This should be largely compliant
        assert any(r["result"] in ("compliant", "undetermined") for r in results)

    def test_non_compliant_chunk_detected(self):
        from compliance_checker import check_compliance
        regulation = "User data must not be shared with third parties without explicit consent."
        business = "We share your location information with partners to help us provide services."
        results = check_compliance(business_text=business, regulation_text=regulation)
        assert len(results) >= 1
        # Sharing without explicit consent mention should flag concern
        assert any(r["result"] in ("non_compliant", "undetermined") for r in results)

    def test_empty_business_text(self, gdpr_text):
        from compliance_checker import check_compliance
        results = check_compliance(business_text="", regulation_text=gdpr_text)
        assert results == []
