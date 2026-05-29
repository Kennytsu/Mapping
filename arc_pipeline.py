"""ARC Pipeline - Automated Regulation Analysis for Privacy Compliance.

Implements the ARC framework (NDSS 2024) for extracting structured tuples
from regulatory text using NLP techniques including:
- Semantic Role Labeling (SRL) for predicate-argument identification
- Clause extraction via constituency parsing
- Tuple generation (Data Flow, Definition, Rights)
- ARCBert phrase similarity for cross-regulation comparison

Uses spaCy as the NLP backbone with rule-based fallbacks for environments
where full SRL models are unavailable.
"""

import re
from typing import Optional

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
    _SBERT_MODEL = None

    def _get_sbert():
        return None

try:
    _nlp = spacy.load("en_core_web_sm")
except OSError:
    _nlp = None


# ---------------------------------------------------------------------------
# Verb Categorization (Table I from ARC paper)
# ---------------------------------------------------------------------------

DATA_FLOW_VERBS = {
    "collect", "inform", "check", "know", "obtain", "access",
    "receive", "gather", "solicit",
    "share", "disclose", "sell", "provide", "trade", "return",
    "transfer", "give", "rent", "send", "distribute", "report", "transmit",
    "save", "retain", "store",
    "process", "use", "operate",
    "delete", "remove", "rescind",
}

DEFINITION_VERBS = {
    "mean", "define", "refer", "include", "exclude",
}

RIGHTS_VERBS = {
    "entitle", "have", "invoke", "exercise",
}

OBLIGATION_MODALS = {"must", "shall", "should"}
PERMISSION_MODALS = {"may", "can", "could", "would"}
PROHIBITION_PATTERNS = [
    "must not", "shall not", "should not", "may not", "could not",
    "cannot", "prohibited", "forbidden",
]


def categorize_verb(verb: str) -> Optional[str]:
    """Categorize a verb into data_flow, definition, or right."""
    verb_lower = verb.lower().strip()
    if verb_lower in DATA_FLOW_VERBS:
        return "data_flow"
    if verb_lower in DEFINITION_VERBS:
        return "definition"
    if verb_lower in RIGHTS_VERBS:
        return "right"
    return None


# ---------------------------------------------------------------------------
# Deontic Modal Detection
# ---------------------------------------------------------------------------

def detect_deontic_modal(statement: str) -> Optional[str]:
    """Detect deontic modal type: obligation, permission, prohibition, or None."""
    text_lower = statement.lower()

    for pattern in PROHIBITION_PATTERNS:
        if pattern in text_lower:
            return "prohibition"

    words = set(re.findall(r"\b\w+\b", text_lower))

    if words & OBLIGATION_MODALS:
        return "obligation"

    if words & PERMISSION_MODALS:
        return "permission"

    return None


# ---------------------------------------------------------------------------
# Verb Extraction
# ---------------------------------------------------------------------------

def extract_verbs(statement: str) -> list[str]:
    """Extract verbs from a statement using spaCy POS tagging."""
    if _nlp is None:
        return _extract_verbs_regex(statement)

    doc = _nlp(statement)
    verbs = []
    for token in doc:
        if token.pos_ == "VERB" or (token.pos_ == "AUX" and token.dep_ != "aux"):
            verbs.append(token.lemma_.lower())
    return verbs


def _extract_verbs_regex(statement: str) -> list[str]:
    """Fallback verb extraction using known verb lists."""
    words = re.findall(r"\b\w+\b", statement.lower())
    all_verbs = DATA_FLOW_VERBS | DEFINITION_VERBS | RIGHTS_VERBS
    found = []
    for w in words:
        if w in all_verbs:
            found.append(w)
        elif w.endswith("s") and w[:-1] in all_verbs:
            found.append(w[:-1])
        elif w.endswith("ed") and w[:-2] in all_verbs:
            found.append(w[:-2])
        elif w.endswith("ing") and w[:-3] in all_verbs:
            found.append(w[:-3])
        elif w == "means":
            found.append("mean")
        elif w == "shared":
            found.append("share")
        elif w == "collected":
            found.append("collect")
        elif w == "defined":
            found.append("define")
    return found


# ---------------------------------------------------------------------------
# SRL-based Semantic Parsing
# ---------------------------------------------------------------------------

def parse_statement(statement: str) -> list[dict]:
    """Parse a regulatory statement into semantic role frames.

    Returns list of frames, each with 'verb' and 'args' dict mapping
    role names to text spans.
    """
    if _nlp is None:
        return _parse_statement_rule_based(statement)

    doc = _nlp(statement)
    frames = []

    for token in doc:
        if token.pos_ != "VERB":
            continue
        verb_lemma = token.lemma_.lower()
        if categorize_verb(verb_lemma) is None:
            continue

        args = {}
        # Use dependency parsing as a lightweight SRL proxy
        for child in token.children:
            if child.dep_ == "nsubj" or child.dep_ == "nsubjpass":
                args["arg0"] = _get_subtree_text(child)
            elif child.dep_ in ("dobj", "attr", "oprd"):
                args["arg1"] = _get_subtree_text(child)
            elif child.dep_ in ("dative", "iobj"):
                args["arg2"] = _get_subtree_text(child)
            elif child.dep_ in ("prep", "agent"):
                prep_text = _get_subtree_text(child)
                if "arg1" not in args:
                    args["arg1"] = prep_text
                else:
                    args.setdefault("argm", [])
                    if isinstance(args["argm"], list):
                        args["argm"].append(prep_text)

        # Also find temporal/purpose modifiers
        for child in token.children:
            if child.dep_ == "advmod" or child.dep_ == "npadvmod":
                args.setdefault("argm_tmp", _get_subtree_text(child))
            elif child.dep_ == "advcl":
                args.setdefault("argm_prp", _get_subtree_text(child))

        frames.append({"verb": verb_lemma, "args": args})

    if not frames:
        return _parse_statement_rule_based(statement)

    return frames


def _get_subtree_text(token) -> str:
    """Get the text of a token's full subtree."""
    return " ".join(t.text for t in token.subtree)


def _parse_statement_rule_based(statement: str) -> list[dict]:
    """Rule-based fallback for SRL when spaCy model is insufficient."""
    frames = []
    verbs = extract_verbs(statement)

    for verb in verbs:
        category = categorize_verb(verb)
        if category is None:
            continue

        args = _extract_args_rule_based(statement, verb)
        frames.append({"verb": verb, "args": args})

    return frames


def _extract_args_rule_based(statement: str, verb: str) -> dict:
    """Extract arguments using regex patterns around the verb."""
    args = {}
    text_lower = statement.lower()

    # Find verb position
    verb_patterns = [verb, verb + "s", verb + "ed", verb + "ing"]
    if verb == "mean":
        verb_patterns.append("means")
    if verb == "share":
        verb_patterns.append("shared")

    verb_pos = -1
    for vp in verb_patterns:
        idx = text_lower.find(vp)
        if idx != -1:
            verb_pos = idx
            break

    if verb_pos == -1:
        return args

    before = statement[:verb_pos].strip()
    after = statement[verb_pos:].strip()

    # Remove deontic modals from before text
    for modal in OBLIGATION_MODALS | PERMISSION_MODALS:
        before = re.sub(rf"\b{modal}\b\s*,?\s*$", "", before, flags=re.IGNORECASE).strip()

    if before:
        args["arg0"] = before.rstrip(",").strip()

    # After the verb, extract object
    verb_match = re.match(r"\w+\s+(.+)", after)
    if verb_match:
        args["arg1"] = verb_match.group(1).strip().rstrip(".")

    return args


# ---------------------------------------------------------------------------
# Clause Extraction
# ---------------------------------------------------------------------------

_RELATIVE_CLAUSE_PATTERN = re.compile(
    r"^(.+?)\s+(that|which|who|whose|whom|where|when)\s+(.+)$",
    re.IGNORECASE
)

_SUBORDINATE_PATTERNS = [
    re.compile(r"^(.+?),\s*(that|which|who)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(that|which|who|whose)\s+(.+)$", re.IGNORECASE),
]


def extract_clause(phrase: str) -> tuple[str, str]:
    """Extract entity phrase and subordinate clause from a complex phrase.

    Returns (entity_phrase, clause) where clause may be empty.
    """
    phrase = phrase.strip()

    if not phrase:
        return ("", "")

    # Try spaCy-based extraction first
    if _nlp is not None:
        entity, clause = _extract_clause_spacy(phrase)
        if clause:
            return (entity, clause)

    # Regex fallback for relative clauses
    for pattern in _SUBORDINATE_PATTERNS:
        match = pattern.match(phrase)
        if match:
            entity = match.group(1).strip()
            relative_pronoun = match.group(2)
            clause_text = match.group(3).strip()
            return (entity, f"{relative_pronoun} {clause_text}")

    match = _RELATIVE_CLAUSE_PATTERN.match(phrase)
    if match:
        entity = match.group(1).strip()
        relative_pronoun = match.group(2)
        clause_text = match.group(3).strip()
        return (entity, f"{relative_pronoun} {clause_text}")

    return (phrase, "")


def _extract_clause_spacy(phrase: str) -> tuple[str, str]:
    """Use spaCy to identify noun phrase and relative clause."""
    doc = _nlp(phrase)

    # Look for relative clause marker
    for token in doc:
        if token.dep_ == "relcl":
            head = token.head
            entity_end = head.idx + len(head.text)
            entity = phrase[:entity_end].strip()
            clause = phrase[entity_end:].strip()
            if clause.startswith(","):
                clause = clause[1:].strip()
            return (entity, clause)

    # Look for 'that/which/who' introducing a clause
    for token in doc:
        if token.text.lower() in ("that", "which", "who", "whose", "whom") and token.dep_ in ("nsubj", "mark", "ref"):
            split_idx = token.idx
            entity = phrase[:split_idx].strip()
            clause = phrase[split_idx:].strip()
            if entity:
                return (entity, clause)

    return (phrase, "")


# ---------------------------------------------------------------------------
# ARC Tuple Generation
# ---------------------------------------------------------------------------

def extract_tuples(statement: str) -> list[dict]:
    """Extract ARC tuples from a regulatory statement.

    Returns list of dicts with keys depending on tuple_type:
    - data_flow: sender_phrase, sender_clause, receiver_phrase, receiver_clause,
                 data_phrase, data_clause, transmission_principle
    - definition: definiendum, definiens
    - right: right_entity, right_statement
    All tuples also have: tuple_type, verb, deontic_modal, source_statement
    """
    deontic = detect_deontic_modal(statement)
    frames = parse_statement(statement)
    tuples = []

    for frame in frames:
        verb = frame["verb"]
        category = categorize_verb(verb)
        if category is None:
            continue

        base = {
            "tuple_type": category,
            "verb": verb,
            "deontic_modal": deontic or "",
            "source_statement": statement,
        }

        if category == "data_flow":
            t = _build_data_flow_tuple(frame, base)
            tuples.append(t)
        elif category == "definition":
            t = _build_definition_tuple(frame, statement, base)
            tuples.append(t)
        elif category == "right":
            t = _build_right_tuple(frame, statement, base)
            tuples.append(t)

    # If no frames found but statement has deontic + regulatory verbs, try harder
    if not tuples and deontic:
        tuples = _fallback_tuple_extraction(statement, deontic)

    return tuples


def _build_data_flow_tuple(frame: dict, base: dict) -> dict:
    """Build a data flow tuple from a parsed frame."""
    args = frame["args"]
    sender_raw = args.get("arg0", "")
    data_raw = args.get("arg1", "")
    receiver_raw = args.get("arg2", "")

    sender_phrase, sender_clause = extract_clause(sender_raw)
    data_phrase, data_clause = extract_clause(data_raw)
    receiver_phrase, receiver_clause = extract_clause(receiver_raw)

    tp_parts = []
    if "argm_tmp" in args:
        tp_parts.append(args["argm_tmp"])
    if "argm_prp" in args:
        tp_parts.append(args["argm_prp"])
    if isinstance(args.get("argm"), list):
        tp_parts.extend(args["argm"])

    return {
        **base,
        "sender_phrase": sender_phrase,
        "sender_clause": sender_clause,
        "receiver_phrase": receiver_phrase,
        "receiver_clause": receiver_clause,
        "data_phrase": data_phrase,
        "data_clause": data_clause,
        "transmission_principle": "; ".join(tp_parts) if tp_parts else "",
    }


def _build_definition_tuple(frame: dict, statement: str, base: dict) -> dict:
    """Build a definition tuple from a parsed frame."""
    args = frame["args"]

    definiendum = args.get("arg0", "")
    definiens = args.get("arg1", "")

    # For 'means'/'defines' patterns, the subject is the term
    if not definiendum and not definiens:
        match = re.match(
            r"['\u2018\u201C\"]*(.+?)['\u2019\u201D\"]*\s+(?:means?|defines?|refers?\s+to|includes?)\s+(.+)",
            statement, re.IGNORECASE,
        )
        if match:
            definiendum = match.group(1).strip(" '\"'\"")
            definiens = match.group(2).strip(" .")

    return {
        **base,
        "definiendum": definiendum,
        "definiens": definiens,
    }


def _build_right_tuple(frame: dict, statement: str, base: dict) -> dict:
    """Build a right tuple from a parsed frame."""
    args = frame["args"]

    right_entity = args.get("arg0", "")
    right_statement = args.get("arg1", "")

    # Look for "shall have the right to X" pattern
    if not right_statement or "right" not in right_statement.lower():
        match = re.search(
            r"(.+?)\s+(?:shall\s+)?have\s+the\s+right\s+to\s+(.+)",
            statement, re.IGNORECASE,
        )
        if match:
            right_entity = match.group(1).strip()
            right_statement = match.group(2).strip().rstrip(".")

    return {
        **base,
        "right_entity": right_entity,
        "right_statement": right_statement,
    }


def _fallback_tuple_extraction(statement: str, deontic: str) -> list[dict]:
    """Last-resort extraction using pure regex for known patterns."""
    tuples = []

    # Check for "shall have the right" pattern
    right_match = re.search(
        r"(.+?)\s+shall\s+have\s+the\s+right\s+to\s+(.+)",
        statement, re.IGNORECASE,
    )
    if right_match:
        tuples.append({
            "tuple_type": "right",
            "verb": "have",
            "deontic_modal": deontic,
            "source_statement": statement,
            "right_entity": right_match.group(1).strip(),
            "right_statement": right_match.group(2).strip().rstrip("."),
        })
        return tuples

    # Check for definition patterns
    def_match = re.match(
        r"['\u2018\u201C\"]*(.+?)['\u2019\u201D\"]*\s+(?:means?|defines?|refers?\s+to)\s+(.+)",
        statement, re.IGNORECASE,
    )
    if def_match:
        tuples.append({
            "tuple_type": "definition",
            "verb": "mean",
            "deontic_modal": "",
            "source_statement": statement,
            "definiendum": def_match.group(1).strip(" '\"'\""),
            "definiens": def_match.group(2).strip(" ."),
        })
        return tuples

    # Check for data flow with prohibition
    verbs_found = extract_verbs(statement)
    for v in verbs_found:
        if categorize_verb(v) == "data_flow":
            tuples.append({
                "tuple_type": "data_flow",
                "verb": v,
                "deontic_modal": deontic,
                "source_statement": statement,
                "sender_phrase": "",
                "sender_clause": "",
                "receiver_phrase": "",
                "receiver_clause": "",
                "data_phrase": "",
                "data_clause": "",
                "transmission_principle": "",
            })
            break

    return tuples


# ---------------------------------------------------------------------------
# Phrase Similarity (ARCBert-style)
# ---------------------------------------------------------------------------

def embed_phrase(phrase: str) -> list[float]:
    """Embed a phrase using sentence-transformers (SBERT).

    Returns a list of floats representing the embedding vector.
    """
    model = _get_sbert()
    if model is None:
        return _simple_embed(phrase)

    embedding = model.encode(phrase, convert_to_numpy=True)
    return embedding.tolist()


def phrase_similarity(phrase1: str, phrase2: str) -> float:
    """Compute cosine similarity between two phrase embeddings."""
    model = _get_sbert()
    if model is None:
        return _simple_similarity(phrase1, phrase2)

    embeddings = model.encode([phrase1, phrase2], convert_to_numpy=True)
    cos_sim = np.dot(embeddings[0], embeddings[1]) / (
        np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
    )
    return float(cos_sim)


def _simple_embed(phrase: str) -> list[float]:
    """Fallback embedding using word overlap (for testing without SBERT)."""
    words = set(phrase.lower().split())
    vocab = sorted(DATA_FLOW_VERBS | DEFINITION_VERBS | RIGHTS_VERBS |
                   {"data", "personal", "information", "user", "consent",
                    "business", "controller", "subject", "right", "process"})
    vec = [1.0 if w in words else 0.0 for w in vocab]
    return vec


def _simple_similarity(phrase1: str, phrase2: str) -> float:
    """Fallback similarity using Jaccard-like overlap."""
    words1 = set(phrase1.lower().split())
    words2 = set(phrase2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    base_sim = len(intersection) / len(union) if union else 0.0
    if phrase1.lower() == phrase2.lower():
        return 1.0
    return min(base_sim * 1.5, 0.99)


# ---------------------------------------------------------------------------
# Pipeline: Process full regulation document
# ---------------------------------------------------------------------------

def process_regulation(text: str) -> list[dict]:
    """Process a full regulation document into ARC tuples.

    Splits text into statements and extracts tuples from each.
    """
    statements = _split_into_statements(text)
    all_tuples = []
    for stmt in statements:
        stmt = stmt.strip()
        if len(stmt) < 10:
            continue
        tuples = extract_tuples(stmt)
        all_tuples.extend(tuples)
    return all_tuples


def _split_into_statements(text: str) -> list[str]:
    """Split regulation text into individual statements."""
    # Split on sentence boundaries, bullet points, or newlines
    text = re.sub(r"\n\s*[•\-\*]\s*", "\n", text)
    statements = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in statements if s.strip()]
