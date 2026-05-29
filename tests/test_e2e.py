"""End-to-end validation tests (Phase 6).

Tests the full pipeline from regulation text input through tuple extraction,
eventic graph construction, and compliance checking with real GDPR text samples.
Validates against known compliance violations and benchmarks accuracy.
"""

import pytest


# ---------------------------------------------------------------------------
# GDPR text samples from Paper 2's examples (Figure 4)
# ---------------------------------------------------------------------------

GDPR_SAMPLE = """
The processing of personal data requires lawful basis.
A user's explicit consent is the only lawful basis for sharing the user's data.
User data must not be shared with third parties unless explicit permission from the user is obtained.
Appropriate technical and organizational measures must be used to protect personal data from unauthorized or unlawful processing and against accidental loss, destruction, or damage.
The data subject shall have the right to withdraw his or her consent at any time.
The data subject shall have the right to obtain from the controller confirmation as to whether or not personal data concerning him or her are being processed.
Every data subject shall have the right to lodge a complaint with a supervisory authority.
'Personal data' means any information relating to an identified or identifiable natural person.
'Processing' means any operation or set of operations which is performed on personal data.
'Controller' means the natural or legal person which determines the purposes and means of the processing of personal data.
'Consent' of the data subject means any freely given, specific, informed and unambiguous indication of the data subject's wishes.
"""

# Business process from Paper 2's example (privacy policy of a health app)
COMPLIANT_BUSINESS_PROCESS = """
We only collect basic health data that you provide (for example: steps, heart rate) and necessary registration information (for example: name, email address).
We use industry-standard security measures to protect your data from unauthorized access, disclosure, or tampering.
You can withdraw your consent and request deletion of your data at any time through your account settings.
We do not share your personal data with any third parties without your explicit consent.
"""

NON_COMPLIANT_BUSINESS_PROCESS = """
We collect basic health data that you provide (for example: steps, heart rate) and necessary registration information (for example: name, email address).
We may share your location information with partners to help us provide services, which you have agreed to during registration.
We use industry-standard security measures to protect your data from unauthorized access, disclosure, or tampering.
"""

# CCPA regulation sample for cross-regulation comparison
CCPA_SAMPLE = """
A business that collects a consumer's personal information shall, at or before the point of collection, inform consumers as to the categories of personal information to be collected and the purposes for which the categories of personal information shall be used.
A consumer shall have the right to request that a business that has collected the consumer's personal information delete that consumer's personal information.
A business shall not sell the personal information of consumers under 16 years of age.
'Personal information' means information that identifies, relates to, describes, is reasonably capable of being associated with, or could reasonably be linked with a particular consumer or household.
"""


class TestEndToEndTupleExtraction:
    """E2E: Full pipeline from GDPR text to structured ARC tuples."""

    def test_gdpr_produces_data_flow_tuples(self):
        from arc_pipeline import process_regulation
        tuples = process_regulation(GDPR_SAMPLE)
        df_tuples = [t for t in tuples if t["tuple_type"] == "data_flow"]
        assert len(df_tuples) >= 2, f"Expected >=2 data flow tuples, got {len(df_tuples)}"

    def test_gdpr_produces_definition_tuples(self):
        from arc_pipeline import process_regulation
        tuples = process_regulation(GDPR_SAMPLE)
        def_tuples = [t for t in tuples if t["tuple_type"] == "definition"]
        assert len(def_tuples) >= 3, f"Expected >=3 definition tuples, got {len(def_tuples)}"

    def test_gdpr_produces_right_tuples(self):
        from arc_pipeline import process_regulation
        tuples = process_regulation(GDPR_SAMPLE)
        right_tuples = [t for t in tuples if t["tuple_type"] == "right"]
        assert len(right_tuples) >= 2, f"Expected >=2 right tuples, got {len(right_tuples)}"

    def test_gdpr_total_tuple_coverage(self):
        """The ARC paper reports high recall on GDPR - we should extract tuples from most statements."""
        from arc_pipeline import process_regulation
        tuples = process_regulation(GDPR_SAMPLE)
        # GDPR sample has ~11 meaningful statements; we should extract from most
        assert len(tuples) >= 8, f"Expected >=8 total tuples, got {len(tuples)}"

    def test_deontic_modal_accuracy(self):
        """Verify deontic modal detection on known samples."""
        from arc_pipeline import process_regulation
        tuples = process_regulation(GDPR_SAMPLE)

        obligation_tuples = [t for t in tuples if t.get("deontic_modal") == "obligation"]
        prohibition_tuples = [t for t in tuples if t.get("deontic_modal") == "prohibition"]

        assert len(obligation_tuples) >= 2, "Should detect obligations (shall/must)"
        assert len(prohibition_tuples) >= 1, "Should detect prohibition (must not)"

    def test_definition_extraction_accuracy(self):
        """Verify definitions are correctly extracted (term -> definition)."""
        from arc_pipeline import process_regulation
        tuples = process_regulation(GDPR_SAMPLE)
        def_tuples = [t for t in tuples if t["tuple_type"] == "definition"]

        terms_found = [t["definiendum"].lower() for t in def_tuples]
        assert any("personal data" in t for t in terms_found), "Should extract 'Personal data' definition"
        assert any("processing" in t for t in terms_found), "Should extract 'Processing' definition"


class TestEndToEndDeonticExtraction:
    """E2E: Algorithm 1 deontic proposition extraction on full GDPR text."""

    def test_extract_multiple_propositions(self):
        from dynamic_layer import extract_deontic_propositions
        props = extract_deontic_propositions(GDPR_SAMPLE)
        assert len(props) >= 5, f"Expected >=5 propositions, got {len(props)}"

    def test_propositions_have_agents(self):
        from dynamic_layer import extract_deontic_propositions
        props = extract_deontic_propositions(GDPR_SAMPLE)
        agents = [p["agent"].lower() for p in props]
        # Should identify key agents
        has_data_subject = any("data subject" in a or "subject" in a for a in agents)
        has_controller_or_org = any("controller" in a or "user" in a or "measures" in a for a in agents)
        assert has_data_subject or has_controller_or_org, f"Should find regulatory agents, got: {agents}"

    def test_eventic_graph_structure(self):
        from dynamic_layer import extract_deontic_propositions, build_eventic_graph
        props = extract_deontic_propositions(GDPR_SAMPLE)
        graph = build_eventic_graph(props)
        assert len(graph.nodes) >= 5, "Graph should have multiple nodes"
        assert len(graph.edges) >= 5, "Graph should have multiple edges"

    def test_graph_has_diverse_relations(self):
        from dynamic_layer import extract_deontic_propositions, build_eventic_graph
        props = extract_deontic_propositions(GDPR_SAMPLE)
        graph = build_eventic_graph(props)
        relations = {d.get("relation") for _, _, d in graph.edges(data=True)}
        assert "duty" in relations, "Should have duty relations"
        # Should have at least prohibition or right as well
        assert len(relations) >= 2, f"Should have diverse relations, got: {relations}"


class TestEndToEndComplianceCheck:
    """E2E: Full compliance checking pipeline with known outcomes."""

    def test_compliant_process_detected(self):
        """A privacy policy that respects all GDPR requirements should be compliant."""
        from compliance_checker import check_compliance
        results = check_compliance(
            business_text=COMPLIANT_BUSINESS_PROCESS,
            regulation_text=GDPR_SAMPLE,
        )
        assert len(results) >= 1
        # Compliant process should have mostly compliant/undetermined results
        non_compliant_count = sum(1 for r in results if r["result"] == "non_compliant")
        compliant_count = sum(1 for r in results if r["result"] == "compliant")
        # At least some chunks should be marked compliant, few non-compliant
        assert compliant_count >= non_compliant_count, (
            f"Compliant process should have more compliant ({compliant_count}) "
            f"than non_compliant ({non_compliant_count}) results"
        )

    def test_non_compliant_process_flagged(self):
        """A privacy policy that shares data without proper consent should be flagged."""
        from compliance_checker import check_compliance
        results = check_compliance(
            business_text=NON_COMPLIANT_BUSINESS_PROCESS,
            regulation_text=GDPR_SAMPLE,
        )
        assert len(results) >= 1
        # Should flag the sharing statement as problematic
        non_compliant_or_undetermined = sum(
            1 for r in results if r["result"] in ("non_compliant", "undetermined")
        )
        assert non_compliant_or_undetermined >= 1, (
            "Non-compliant sharing practice should be flagged"
        )

    def test_results_have_explanations(self):
        from compliance_checker import check_compliance
        results = check_compliance(
            business_text=NON_COMPLIANT_BUSINESS_PROCESS,
            regulation_text=GDPR_SAMPLE,
        )
        for r in results:
            assert r["explanation"] != "", "Each result should have an explanation"

    def test_sharing_violation_specifically_detected(self):
        """The specific violation: sharing location data with partners."""
        from compliance_checker import check_compliance
        regulation = "User data must not be shared with third parties unless explicit permission from the user is obtained."
        business = "We may share your location information with partners to help us provide services."
        results = check_compliance(business_text=business, regulation_text=regulation)
        assert len(results) >= 1
        assert any(
            r["result"] == "non_compliant" for r in results
        ), "Sharing without explicit consent should be non_compliant"


class TestEndToEndCrossRegulationComparison:
    """E2E: Cross-regulation comparison using ARCBert similarity."""

    def test_gdpr_ccpa_have_overlap(self):
        """GDPR and CCPA regulate similar domains - should show similarity."""
        from arc_pipeline import process_regulation, phrase_similarity

        gdpr_tuples = process_regulation(GDPR_SAMPLE)
        ccpa_tuples = process_regulation(CCPA_SAMPLE)

        assert len(gdpr_tuples) >= 3
        assert len(ccpa_tuples) >= 2

        # Find best matching pair between the two regulations
        best_sim = 0.0
        for t1 in gdpr_tuples:
            s1 = t1.get("source_statement", "")
            if not s1:
                continue
            for t2 in ccpa_tuples:
                s2 = t2.get("source_statement", "")
                if not s2:
                    continue
                sim = phrase_similarity(s1, s2)
                best_sim = max(best_sim, sim)

        assert best_sim > 0.4, (
            f"GDPR and CCPA should have some similar provisions, best similarity: {best_sim:.3f}"
        )

    def test_definition_overlap(self):
        """Both regulations define 'personal data/information' - should be similar."""
        from arc_pipeline import phrase_similarity

        gdpr_def = "any information relating to an identified or identifiable natural person"
        ccpa_def = "information that identifies, relates to, describes, is reasonably capable of being associated with a particular consumer"

        sim = phrase_similarity(gdpr_def, ccpa_def)
        assert sim > 0.4, f"Personal data definitions should be similar, got {sim:.3f}"

    def test_unique_provisions_have_low_similarity(self):
        """Provisions unique to one regulation should have low similarity to the other."""
        from arc_pipeline import phrase_similarity

        gdpr_specific = "The data subject shall have the right to lodge a complaint with a supervisory authority"
        ccpa_specific = "A business shall not sell the personal information of consumers under 16 years of age"

        sim = phrase_similarity(gdpr_specific, ccpa_specific)
        assert sim < 0.8, f"Unique provisions should not be too similar, got {sim:.3f}"


class TestEndToEndStaticLayer:
    """E2E: Static layer term-definition extraction on full GDPR sample."""

    def test_extract_gdpr_definitions(self):
        from static_layer import extract_term_definitions
        defs = extract_term_definitions(GDPR_SAMPLE)
        assert len(defs) >= 3, f"Expected >=3 definitions, got {len(defs)}"
        terms = [d["term"].lower() for d in defs]
        assert any("personal data" in t for t in terms)

    def test_definition_retrieval_relevance(self):
        """Retrieving definitions for 'data processing' should return relevant results."""
        from static_layer import extract_term_definitions, retrieve_definitions
        defs = extract_term_definitions(GDPR_SAMPLE)
        results = retrieve_definitions(defs, "processing of personal data")
        assert len(results) >= 1
        # Top result should be about personal data or processing
        top = results[0]
        assert "personal data" in top["term"].lower() or "processing" in top["term"].lower()


class TestAccuracyBenchmark:
    """Benchmark accuracy metrics against paper-reported results.

    Paper 1 (ARC) reports:
    - ~85% precision for tuple extraction on GDPR/CCPA
    - ~80% recall for tuple extraction

    Paper 2 (RAG) reports:
    - ~78% accuracy on compliance judgments

    We test against realistic but achievable thresholds for our implementation.
    """

    def test_tuple_extraction_coverage(self):
        """Measure tuple extraction coverage on GDPR sample."""
        from arc_pipeline import process_regulation

        tuples = process_regulation(GDPR_SAMPLE)
        # GDPR sample has 11 regulatory statements
        # Each should produce at least one tuple for good coverage
        total_statements = 11
        coverage = len(tuples) / total_statements
        assert coverage >= 0.7, (
            f"Tuple extraction coverage should be >=70%, got {coverage*100:.1f}% "
            f"({len(tuples)}/{total_statements})"
        )

    def test_deontic_detection_precision(self):
        """Measure precision of deontic modal detection."""
        from arc_pipeline import detect_deontic_modal

        test_cases = [
            ("The controller shall implement measures.", "obligation"),
            ("User data must not be shared.", "prohibition"),
            ("The data subject may withdraw consent.", "permission"),
            ("Personal data means any information.", None),
            ("The organization shall inform users.", "obligation"),
            ("A business must not sell data.", "prohibition"),
        ]

        correct = 0
        for statement, expected in test_cases:
            result = detect_deontic_modal(statement)
            if result == expected:
                correct += 1

        precision = correct / len(test_cases)
        assert precision >= 0.8, (
            f"Deontic detection precision should be >=80%, got {precision*100:.1f}%"
        )

    def test_compliance_judgment_accuracy(self):
        """Measure accuracy of compliance judgments on known cases."""
        from compliance_checker import check_compliance

        test_cases = [
            # (business_text, regulation_text, expected_has_non_compliant)
            (
                "We share your data with partners without asking.",
                "User data must not be shared with third parties without consent.",
                True,  # should detect non-compliance
            ),
            (
                "We use encryption to protect all personal data.",
                "Appropriate technical measures must be used to protect personal data.",
                False,  # should be compliant
            ),
        ]

        correct = 0
        for business, regulation, expect_violation in test_cases:
            results = check_compliance(business_text=business, regulation_text=regulation)
            has_violation = any(r["result"] == "non_compliant" for r in results)
            if has_violation == expect_violation:
                correct += 1

        accuracy = correct / len(test_cases)
        assert accuracy >= 0.5, (
            f"Compliance judgment accuracy should be >=50% without LLM, got {accuracy*100:.1f}%"
        )
