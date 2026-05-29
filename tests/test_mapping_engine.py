"""Tests for the regulation-to-regulation mapping pipeline.

This is the core functionality: automatically finding mappings between
two regulatory frameworks by comparing their extracted tuples semantically.
"""

import pytest


class TestBulkMapping:
    """Test automatic mapping generation between two regulations."""

    def test_generate_mappings_returns_pairs(self):
        from mapping_engine import generate_mappings
        reg_a_text = "The controller shall implement appropriate technical measures to protect personal data."
        reg_b_text = "Organizations must use security controls to safeguard information assets."
        mappings = generate_mappings(reg_a_text, reg_b_text, threshold=0.4)
        assert isinstance(mappings, list)
        assert len(mappings) >= 1

    def test_mapping_has_required_fields(self):
        from mapping_engine import generate_mappings
        reg_a_text = "Personal data must not be shared without consent."
        reg_b_text = "Information shall not be disclosed to unauthorized parties."
        mappings = generate_mappings(reg_a_text, reg_b_text)
        if mappings:
            m = mappings[0]
            assert "source_statement" in m
            assert "target_statement" in m
            assert "similarity" in m
            assert "source_tuple_type" in m
            assert "target_tuple_type" in m

    def test_similar_statements_get_high_score(self):
        from mapping_engine import generate_mappings
        reg_a_text = "The organization shall protect personal data with encryption."
        reg_b_text = "The entity must safeguard personal information using cryptographic measures."
        mappings = generate_mappings(reg_a_text, reg_b_text)
        assert len(mappings) >= 1
        assert mappings[0]["similarity"] > 0.5

    def test_unrelated_regulations_low_mappings(self):
        from mapping_engine import generate_mappings
        reg_a_text = "The controller shall inform data subjects about processing purposes."
        reg_b_text = "The fiscal year budget must be approved by the board of directors."
        mappings = generate_mappings(reg_a_text, reg_b_text, threshold=0.7)
        assert len(mappings) == 0

    def test_threshold_filters_results(self):
        from mapping_engine import generate_mappings
        reg_a_text = "Data subjects have the right to access their personal data. The controller must respond within 30 days."
        reg_b_text = "Individuals may request access to information held about them. Responses must be timely."
        high_threshold = generate_mappings(reg_a_text, reg_b_text, threshold=0.9)
        low_threshold = generate_mappings(reg_a_text, reg_b_text, threshold=0.3)
        assert len(low_threshold) >= len(high_threshold)

    def test_gdpr_iso_mapping(self):
        """Real-world test: GDPR requirements should map to ISO 27001 controls."""
        from mapping_engine import generate_mappings
        gdpr = """
        The controller shall implement appropriate technical and organizational measures to ensure a level of security appropriate to the risk.
        The controller shall ensure that any natural person acting under the authority of the controller who has access to personal data does not process them except on instructions from the controller.
        """
        iso27001 = """
        The organization shall implement information security controls appropriate to the risk.
        Access to information and information processing facilities shall be restricted in accordance with the access control policy.
        """
        mappings = generate_mappings(gdpr, iso27001, threshold=0.4)
        assert len(mappings) >= 1
        assert any(m["similarity"] > 0.4 for m in mappings)

    def test_mapping_ranked_by_similarity(self):
        from mapping_engine import generate_mappings
        reg_a = "Data must be encrypted. Users must give consent. Records must be kept."
        reg_b = "Information shall be encrypted using strong algorithms. Consent is required."
        mappings = generate_mappings(reg_a, reg_b, threshold=0.3)
        if len(mappings) > 1:
            for i in range(len(mappings) - 1):
                assert mappings[i]["similarity"] >= mappings[i+1]["similarity"]


class TestMappingSuggestions:
    """Test converting mapping results into persistable suggestions."""

    def test_format_as_suggestions(self):
        from mapping_engine import generate_mappings, format_as_suggestions
        reg_a = "The controller shall protect personal data."
        reg_b = "The organization must safeguard information."
        mappings = generate_mappings(reg_a, reg_b)
        suggestions = format_as_suggestions(mappings, source_reg_name="GDPR", target_reg_name="ISO 27001")
        assert isinstance(suggestions, list)
        if suggestions:
            s = suggestions[0]
            assert s["source_type"] == "ai_suggested"
            assert "confidence" in s
            assert s["confidence"] >= 0.0 and s["confidence"] <= 1.0
            assert "GDPR" in s["source_document"] or "ISO" in s["source_document"]

    def test_confidence_maps_from_similarity(self):
        from mapping_engine import generate_mappings, format_as_suggestions
        reg_a = "Personal data means any information relating to a natural person."
        reg_b = "Personal information means data that identifies an individual."
        mappings = generate_mappings(reg_a, reg_b)
        suggestions = format_as_suggestions(mappings, source_reg_name="GDPR", target_reg_name="CCPA")
        if suggestions:
            assert suggestions[0]["confidence"] == suggestions[0]["similarity"]
