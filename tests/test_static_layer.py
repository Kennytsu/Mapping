"""Tests for the Static Layer (Phase 3 - RAG framework).

The static layer handles:
- Entity knowledge extraction
- Concept knowledge graph (existing framework hierarchies)
- Term-definition extraction and storage
"""

import pytest


class TestTermDefinitionExtraction:
    """Test term-definition extraction from regulatory text."""

    def test_extract_definitions_from_gdpr(self, gdpr_definitions):
        from static_layer import extract_term_definitions
        defs = extract_term_definitions(gdpr_definitions)
        assert len(defs) >= 3
        terms = [d["term"].lower() for d in defs]
        assert any("personal data" in t for t in terms)
        assert any("processing" in t for t in terms)
        assert any("controller" in t for t in terms)

    def test_definition_has_required_fields(self, gdpr_definitions):
        from static_layer import extract_term_definitions
        defs = extract_term_definitions(gdpr_definitions)
        for d in defs:
            assert "term" in d
            assert "definition" in d
            assert d["term"] != ""
            assert d["definition"] != ""

    def test_extract_quoted_term_definitions(self):
        from static_layer import extract_term_definitions
        text = "'Data subject' means an identified or identifiable natural person."
        defs = extract_term_definitions(text)
        assert len(defs) >= 1
        assert "data subject" in defs[0]["term"].lower()

    def test_extract_definition_with_means(self):
        from static_layer import extract_term_definitions
        text = "Processing means any operation performed on personal data."
        defs = extract_term_definitions(text)
        assert len(defs) >= 1
        assert "processing" in defs[0]["term"].lower()
        assert "operation" in defs[0]["definition"].lower()


class TestEntityKnowledge:
    """Test entity knowledge extraction and storage."""

    def test_extract_entities_from_text(self):
        from static_layer import extract_entities
        text = "The data controller must inform the Data Protection Authority within 72 hours."
        entities = extract_entities(text)
        assert isinstance(entities, list)
        assert len(entities) >= 1

    def test_entity_has_type_and_text(self):
        from static_layer import extract_entities
        text = "The European Commission shall publish a list of adequacy decisions."
        entities = extract_entities(text)
        for e in entities:
            assert "text" in e
            assert "type" in e


class TestConceptKnowledge:
    """Test concept knowledge graph construction."""

    def test_build_concept_hierarchy(self):
        from static_layer import build_concept_hierarchy
        concepts = [
            {"id": 1, "text": "Data Protection", "parent_id": None},
            {"id": 2, "text": "Access Control", "parent_id": 1},
            {"id": 3, "text": "Encryption", "parent_id": 1},
        ]
        graph = build_concept_hierarchy(concepts)
        assert graph is not None
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

    def test_get_related_concepts(self):
        from static_layer import build_concept_hierarchy, get_related_concepts
        concepts = [
            {"id": 1, "text": "Data Protection", "parent_id": None},
            {"id": 2, "text": "Access Control", "parent_id": 1},
            {"id": 3, "text": "Encryption", "parent_id": 1},
        ]
        graph = build_concept_hierarchy(concepts)
        related = get_related_concepts(graph, 1)
        assert 2 in related or "Access Control" in str(related)


class TestStaticLayerRetrieval:
    """Test retrieval from static knowledge."""

    def test_retrieve_relevant_definitions(self, gdpr_definitions):
        from static_layer import extract_term_definitions, retrieve_definitions
        defs = extract_term_definitions(gdpr_definitions)
        results = retrieve_definitions(defs, "personal data processing")
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_retrieve_returns_ranked(self, gdpr_definitions):
        from static_layer import extract_term_definitions, retrieve_definitions
        defs = extract_term_definitions(gdpr_definitions)
        results = retrieve_definitions(defs, "consent of the data subject")
        if len(results) > 1:
            assert results[0]["score"] >= results[1]["score"]
