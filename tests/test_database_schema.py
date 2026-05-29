"""Tests for the extended database models (Phase 1).

Tests verify that the new compliance checking models are properly defined
with correct columns, relationships, and constraints.
"""

import pytest
from datetime import datetime


def test_regulation_document_model_exists():
    from database import RegulationDocument
    assert RegulationDocument.__tablename__ == "regulation_documents"


def test_regulation_document_has_required_fields():
    from database import RegulationDocument
    cols = {c.name for c in RegulationDocument.__table__.columns}
    required = {"id", "name", "short_name", "version", "jurisdiction",
                "full_text", "language", "created_at"}
    assert required.issubset(cols)


def test_arc_tuple_model_exists():
    from database import ArcTuple
    assert ArcTuple.__tablename__ == "arc_tuples"


def test_arc_tuple_has_required_fields():
    from database import ArcTuple
    cols = {c.name for c in ArcTuple.__table__.columns}
    required = {"id", "regulation_id", "tuple_type", "source_statement",
                "verb", "deontic_modal"}
    assert required.issubset(cols)


def test_arc_tuple_types():
    """ARC tuples must be one of: data_flow, definition, right."""
    from database import ArcTuple
    t = ArcTuple(tuple_type="data_flow")
    assert t.tuple_type == "data_flow"
    t2 = ArcTuple(tuple_type="definition")
    assert t2.tuple_type == "definition"
    t3 = ArcTuple(tuple_type="right")
    assert t3.tuple_type == "right"


def test_arc_tuple_data_flow_attributes():
    """Data flow tuple should store sender, receiver, data, and transmission principle."""
    from database import ArcTuple
    cols = {c.name for c in ArcTuple.__table__.columns}
    df_fields = {"sender_phrase", "sender_clause", "receiver_phrase",
                 "receiver_clause", "data_phrase", "data_clause",
                 "transmission_principle"}
    assert df_fields.issubset(cols)


def test_arc_tuple_definition_attributes():
    """Definition tuple should store definiendum and definiens."""
    from database import ArcTuple
    cols = {c.name for c in ArcTuple.__table__.columns}
    assert {"definiendum", "definiens"}.issubset(cols)


def test_arc_tuple_right_attributes():
    """Right tuple should store entity and right statement."""
    from database import ArcTuple
    cols = {c.name for c in ArcTuple.__table__.columns}
    assert {"right_entity", "right_statement"}.issubset(cols)


def test_eventic_graph_node_model_exists():
    from database import EventicGraphNode
    assert EventicGraphNode.__tablename__ == "eventic_graph_nodes"


def test_eventic_graph_node_has_required_fields():
    from database import EventicGraphNode
    cols = {c.name for c in EventicGraphNode.__table__.columns}
    required = {"id", "regulation_id", "node_type", "text", "embedding"}
    assert required.issubset(cols)


def test_eventic_graph_node_types():
    """Eventic graph node types from Paper 2: Organization, Person, Regulatory document, Category, Action, State."""
    from database import EventicGraphNode
    valid_types = ["organization", "person", "regulatory_document",
                   "category", "action", "state"]
    for nt in valid_types:
        node = EventicGraphNode(node_type=nt, text="test")
        assert node.node_type == nt


def test_eventic_graph_edge_model_exists():
    from database import EventicGraphEdge
    assert EventicGraphEdge.__tablename__ == "eventic_graph_edges"


def test_eventic_graph_edge_has_required_fields():
    from database import EventicGraphEdge
    cols = {c.name for c in EventicGraphEdge.__table__.columns}
    required = {"id", "source_node_id", "target_node_id", "relation_type"}
    assert required.issubset(cols)


def test_eventic_graph_edge_relation_types():
    """Relation types from Paper 2: Publish, WorkFor, Duty, Prohibited, Right, ClassifiedTo, Cite."""
    from database import EventicGraphEdge
    valid_relations = ["publish", "work_for", "duty", "prohibited",
                       "right", "classified_to", "cite"]
    for rt in valid_relations:
        edge = EventicGraphEdge(relation_type=rt)
        assert edge.relation_type == rt


def test_term_definition_model_exists():
    from database import TermDefinition
    assert TermDefinition.__tablename__ == "term_definitions"


def test_term_definition_has_required_fields():
    from database import TermDefinition
    cols = {c.name for c in TermDefinition.__table__.columns}
    required = {"id", "regulation_id", "term", "definition", "embedding"}
    assert required.issubset(cols)


def test_compliance_check_model_exists():
    from database import ComplianceCheck
    assert ComplianceCheck.__tablename__ == "compliance_checks"


def test_compliance_check_has_required_fields():
    from database import ComplianceCheck
    cols = {c.name for c in ComplianceCheck.__table__.columns}
    required = {"id", "business_process_chunk", "regulation_id",
                "result", "explanation", "created_at"}
    assert required.issubset(cols)


def test_compliance_check_results():
    """Results should be compliant, non_compliant, or undetermined."""
    from database import ComplianceCheck
    for result in ["compliant", "non_compliant", "undetermined"]:
        check = ComplianceCheck(result=result)
        assert check.result == result


def test_business_process_document_model_exists():
    from database import BusinessProcessDocument
    assert BusinessProcessDocument.__tablename__ == "business_process_documents"


def test_business_process_document_has_required_fields():
    from database import BusinessProcessDocument
    cols = {c.name for c in BusinessProcessDocument.__table__.columns}
    required = {"id", "name", "full_text", "created_at"}
    assert required.issubset(cols)


def test_business_process_chunk_model_exists():
    from database import BusinessProcessChunk
    assert BusinessProcessChunk.__tablename__ == "business_process_chunks"


def test_business_process_chunk_has_required_fields():
    from database import BusinessProcessChunk
    cols = {c.name for c in BusinessProcessChunk.__table__.columns}
    required = {"id", "document_id", "text", "chunk_index", "embedding"}
    assert required.issubset(cols)
