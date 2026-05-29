"""Tests for the ARC pipeline module (Phases 2-4).

Tests SRL-based semantic parsing, clause extraction, tuple generation,
deontic modal detection, and phrase similarity.
"""

import pytest


# ---------------------------------------------------------------------------
# Phase 2: SRL + Deontic Modal Detection
# ---------------------------------------------------------------------------

class TestVerbCategorization:
    """Test verb identification and categorization per Table I of the ARC paper."""

    def test_data_flow_verbs_recognized(self):
        from arc_pipeline import DATA_FLOW_VERBS
        expected = {"collect", "share", "disclose", "sell", "provide",
                    "retain", "store", "process", "use", "delete",
                    "inform", "obtain", "access", "receive", "gather",
                    "transfer", "give", "send", "distribute", "report",
                    "transmit", "return", "trade", "rent", "solicit",
                    "save", "remove", "rescind", "operate", "check", "know"}
        assert expected.issubset(DATA_FLOW_VERBS)

    def test_definition_verbs_recognized(self):
        from arc_pipeline import DEFINITION_VERBS
        expected = {"mean", "define", "refer", "include", "exclude"}
        assert expected.issubset(DEFINITION_VERBS)

    def test_rights_verbs_recognized(self):
        from arc_pipeline import RIGHTS_VERBS
        expected = {"entitle", "have", "invoke", "exercise"}
        assert expected.issubset(RIGHTS_VERBS)

    def test_categorize_verb_data_flow(self):
        from arc_pipeline import categorize_verb
        assert categorize_verb("collect") == "data_flow"
        assert categorize_verb("share") == "data_flow"
        assert categorize_verb("inform") == "data_flow"

    def test_categorize_verb_definition(self):
        from arc_pipeline import categorize_verb
        assert categorize_verb("mean") == "definition"
        assert categorize_verb("define") == "definition"

    def test_categorize_verb_rights(self):
        from arc_pipeline import categorize_verb
        assert categorize_verb("entitle") == "right"
        assert categorize_verb("exercise") == "right"

    def test_categorize_verb_unknown(self):
        from arc_pipeline import categorize_verb
        assert categorize_verb("run") is None


class TestDeonticModalDetection:
    """Test detection of obligation, permission, and prohibition modals."""

    def test_obligation_modals(self):
        from arc_pipeline import OBLIGATION_MODALS
        assert "must" in OBLIGATION_MODALS
        assert "shall" in OBLIGATION_MODALS
        assert "should" in OBLIGATION_MODALS

    def test_permission_modals(self):
        from arc_pipeline import PERMISSION_MODALS
        assert "may" in PERMISSION_MODALS
        assert "can" in PERMISSION_MODALS
        assert "could" in PERMISSION_MODALS

    def test_prohibition_modals(self):
        from arc_pipeline import PROHIBITION_PATTERNS
        assert any("must not" in p for p in PROHIBITION_PATTERNS)
        assert any("shall not" in p for p in PROHIBITION_PATTERNS)

    def test_detect_obligation(self):
        from arc_pipeline import detect_deontic_modal
        result = detect_deontic_modal("A business shall inform consumers")
        assert result == "obligation"

    def test_detect_permission(self):
        from arc_pipeline import detect_deontic_modal
        result = detect_deontic_modal("The organization may collect personal information")
        assert result == "permission"

    def test_detect_prohibition(self):
        from arc_pipeline import detect_deontic_modal
        result = detect_deontic_modal("User data must not be shared with third parties")
        assert result == "prohibition"

    def test_detect_none(self):
        from arc_pipeline import detect_deontic_modal
        result = detect_deontic_modal("This is a normal statement")
        assert result is None


class TestSemanticParsing:
    """Test SRL-based semantic parsing of regulatory statements."""

    def test_extract_verbs_from_statement(self):
        from arc_pipeline import extract_verbs
        statement = "A business shall inform consumers about personal information to be collected."
        verbs = extract_verbs(statement)
        assert "inform" in verbs or "collect" in verbs

    def test_extract_verbs_from_definition(self):
        from arc_pipeline import extract_verbs
        statement = "Personal data means any information relating to an identified natural person."
        verbs = extract_verbs(statement)
        assert "mean" in verbs or "means" in verbs or "relate" in verbs

    def test_srl_parse_returns_structured_output(self):
        from arc_pipeline import parse_statement
        statement = "A business shall inform consumers about the categories of personal information."
        result = parse_statement(statement)
        assert isinstance(result, list)
        if result:
            frame = result[0]
            assert "verb" in frame
            assert "args" in frame


# ---------------------------------------------------------------------------
# Phase 2 (continued): Clause Extraction
# ---------------------------------------------------------------------------

class TestClauseExtraction:
    """Test clause extraction from complex regulatory phrases."""

    def test_extract_subordinate_clause(self):
        from arc_pipeline import extract_clause
        phrase = "A business that collects a consumer's personal information"
        entity, clause = extract_clause(phrase)
        assert "business" in entity.lower()
        assert "collects" in clause.lower() or clause == ""

    def test_simple_phrase_no_clause(self):
        from arc_pipeline import extract_clause
        phrase = "personal information"
        entity, clause = extract_clause(phrase)
        assert entity == phrase or "personal information" in entity
        assert clause == ""

    def test_complex_phrase_with_relative_clause(self):
        from arc_pipeline import extract_clause
        phrase = "the data subject who has given consent"
        entity, clause = extract_clause(phrase)
        assert "data subject" in entity.lower()


# ---------------------------------------------------------------------------
# Phase 2 (continued): ARC Tuple Generation
# ---------------------------------------------------------------------------

class TestTupleGeneration:
    """Test ARC tuple extraction from regulatory statements."""

    def test_extract_data_flow_tuple(self):
        from arc_pipeline import extract_tuples
        statement = "A business shall inform consumers about the categories of personal information."
        tuples = extract_tuples(statement)
        df_tuples = [t for t in tuples if t["tuple_type"] == "data_flow"]
        assert len(df_tuples) >= 1
        t = df_tuples[0]
        assert t["verb"] != ""
        assert t["deontic_modal"] == "obligation"

    def test_extract_definition_tuple(self):
        from arc_pipeline import extract_tuples
        statement = "Personal data means any information relating to an identified or identifiable natural person."
        tuples = extract_tuples(statement)
        def_tuples = [t for t in tuples if t["tuple_type"] == "definition"]
        assert len(def_tuples) >= 1
        t = def_tuples[0]
        assert "personal data" in t["definiendum"].lower()
        assert t["definiens"] != ""

    def test_extract_right_tuple(self):
        from arc_pipeline import extract_tuples
        statement = "The data subject shall have the right to withdraw his or her consent at any time."
        tuples = extract_tuples(statement)
        right_tuples = [t for t in tuples if t["tuple_type"] == "right"]
        assert len(right_tuples) >= 1
        t = right_tuples[0]
        assert "data subject" in t["right_entity"].lower()
        assert "withdraw" in t["right_statement"].lower() or "consent" in t["right_statement"].lower()

    def test_extract_prohibition_data_flow(self):
        from arc_pipeline import extract_tuples
        statement = "User data must not be shared with third parties unless explicit permission is obtained."
        tuples = extract_tuples(statement)
        assert any(t["deontic_modal"] == "prohibition" for t in tuples)

    def test_extract_tuples_returns_list(self):
        from arc_pipeline import extract_tuples
        result = extract_tuples("Some random text without regulatory content.")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Phase 4: Phrase Similarity (ARCBert)
# ---------------------------------------------------------------------------

class TestPhraseSimilarity:
    """Test phrase embedding and similarity functions."""

    def test_embed_phrase_returns_vector(self):
        from arc_pipeline import embed_phrase
        vec = embed_phrase("personal information")
        assert vec is not None
        assert len(vec) > 0

    def test_similar_phrases_high_score(self):
        from arc_pipeline import phrase_similarity
        score = phrase_similarity(
            "in an intelligible and easily accessible form",
            "in a form that is generally understandable"
        )
        assert score > 0.5

    def test_dissimilar_phrases_lower_score(self):
        from arc_pipeline import phrase_similarity
        score = phrase_similarity(
            "access to personal information",
            "the organization notified an institution"
        )
        assert score < 0.8

    def test_identical_phrases_score_one(self):
        from arc_pipeline import phrase_similarity
        score = phrase_similarity("personal data", "personal data")
        assert score > 0.95
