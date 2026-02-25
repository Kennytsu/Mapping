"""
Seed script: populate PostgreSQL with frameworks, controls, and official mappings.

Usage:
    python seed_data.py [--bsi path/to/bsi.pdf] [--c5 path/to/c5.xlsx]

If no files are given, only the framework records are created.
Place files in ./data/ or pass explicit paths.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import select
from database import init_db_sync, SyncSession, Framework, Control, Mapping
from document_parser import parse_bsi_zuordnung_pdf, parse_excel


# ---------------------------------------------------------------------------
# Framework definitions
# ---------------------------------------------------------------------------

FRAMEWORKS = [
    {
        "name": "ISO/IEC 27001:2022",
        "short_name": "ISO27001",
        "version": "2022",
        "description": "International standard for information security management systems",
    },
    {
        "name": "BSI IT-Grundschutz Kompendium",
        "short_name": "BSI",
        "version": "Edition 6 (2022)",
        "description": "German Federal Office for Information Security - IT baseline protection",
    },
    {
        "name": "BSI Cloud Computing Compliance Criteria Catalogue",
        "short_name": "C5",
        "version": "2020",
        "description": "BSI C5:2020 cloud security criteria",
    },
]

# ISO 27001:2022 Annex A controls for seeding
ISO_27001_CONTROLS = [
    ("A.5.1", "Policies for information security", "Organizational"),
    ("A.5.2", "Information security roles and responsibilities", "Organizational"),
    ("A.5.3", "Segregation of duties", "Organizational"),
    ("A.5.4", "Management responsibilities", "Organizational"),
    ("A.5.5", "Contact with authorities", "Organizational"),
    ("A.5.6", "Contact with special interest groups", "Organizational"),
    ("A.5.7", "Threat intelligence", "Organizational"),
    ("A.5.8", "Information security in project management", "Organizational"),
    ("A.5.9", "Inventory of information and other associated assets", "Organizational"),
    ("A.5.10", "Acceptable use of information and other associated assets", "Organizational"),
    ("A.5.11", "Return of assets", "Organizational"),
    ("A.5.12", "Classification of information", "Organizational"),
    ("A.5.13", "Labelling of information", "Organizational"),
    ("A.5.14", "Information transfer", "Organizational"),
    ("A.5.15", "Access control", "Organizational"),
    ("A.5.16", "Identity management", "Organizational"),
    ("A.5.17", "Authentication information", "Organizational"),
    ("A.5.18", "Access rights", "Organizational"),
    ("A.5.19", "Information security in supplier relationships", "Organizational"),
    ("A.5.20", "Addressing information security within supplier agreements", "Organizational"),
    ("A.5.21", "Managing information security in the ICT supply chain", "Organizational"),
    ("A.5.22", "Monitoring, review and change management of supplier services", "Organizational"),
    ("A.5.23", "Information security for use of cloud services", "Organizational"),
    ("A.5.24", "Information security incident management planning and preparation", "Organizational"),
    ("A.5.25", "Assessment and decision on information security events", "Organizational"),
    ("A.5.26", "Response to information security incidents", "Organizational"),
    ("A.5.27", "Learning from information security incidents", "Organizational"),
    ("A.5.28", "Collection of evidence", "Organizational"),
    ("A.5.29", "Information security during disruption", "Organizational"),
    ("A.5.30", "ICT readiness for business continuity", "Organizational"),
    ("A.5.31", "Legal, statutory, regulatory and contractual requirements", "Organizational"),
    ("A.5.32", "Intellectual property rights", "Organizational"),
    ("A.5.33", "Protection of records", "Organizational"),
    ("A.5.34", "Privacy and protection of PII", "Organizational"),
    ("A.5.35", "Independent review of information security", "Organizational"),
    ("A.5.36", "Compliance with policies, rules and standards for information security", "Organizational"),
    ("A.5.37", "Documented operating procedures", "Organizational"),
    ("A.6.1", "Screening", "People"),
    ("A.6.2", "Terms and conditions of employment", "People"),
    ("A.6.3", "Information security awareness, education and training", "People"),
    ("A.6.4", "Disciplinary process", "People"),
    ("A.6.5", "Responsibilities after termination or change of employment", "People"),
    ("A.6.6", "Confidentiality or non-disclosure agreements", "People"),
    ("A.6.7", "Remote working", "People"),
    ("A.6.8", "Information security event reporting", "People"),
    ("A.7.1", "Physical security perimeters", "Physical"),
    ("A.7.2", "Physical entry", "Physical"),
    ("A.7.3", "Securing offices, rooms and facilities", "Physical"),
    ("A.7.4", "Physical security monitoring", "Physical"),
    ("A.7.5", "Protecting against physical and environmental threats", "Physical"),
    ("A.7.6", "Working in secure areas", "Physical"),
    ("A.7.7", "Clear desk and clear screen", "Physical"),
    ("A.7.8", "Equipment siting and protection", "Physical"),
    ("A.7.9", "Security of assets off-premises", "Physical"),
    ("A.7.10", "Storage media", "Physical"),
    ("A.7.11", "Supporting utilities", "Physical"),
    ("A.7.12", "Cabling security", "Physical"),
    ("A.7.13", "Equipment maintenance", "Physical"),
    ("A.7.14", "Secure disposal or re-use of equipment", "Physical"),
    ("A.8.1", "User endpoint devices", "Technological"),
    ("A.8.2", "Privileged access rights", "Technological"),
    ("A.8.3", "Information access restriction", "Technological"),
    ("A.8.4", "Access to source code", "Technological"),
    ("A.8.5", "Secure authentication", "Technological"),
    ("A.8.6", "Capacity management", "Technological"),
    ("A.8.7", "Protection against malware", "Technological"),
    ("A.8.8", "Management of technical vulnerabilities", "Technological"),
    ("A.8.9", "Configuration management", "Technological"),
    ("A.8.10", "Information deletion", "Technological"),
    ("A.8.11", "Data masking", "Technological"),
    ("A.8.12", "Data leakage prevention", "Technological"),
    ("A.8.13", "Information backup", "Technological"),
    ("A.8.14", "Redundancy of information processing facilities", "Technological"),
    ("A.8.15", "Logging", "Technological"),
    ("A.8.16", "Monitoring activities", "Technological"),
    ("A.8.17", "Clock synchronization", "Technological"),
    ("A.8.18", "Use of privileged utility programs", "Technological"),
    ("A.8.19", "Installation of software on operational systems", "Technological"),
    ("A.8.20", "Networks security", "Technological"),
    ("A.8.21", "Security of network services", "Technological"),
    ("A.8.22", "Segregation of networks", "Technological"),
    ("A.8.23", "Web filtering", "Technological"),
    ("A.8.24", "Use of cryptography", "Technological"),
    ("A.8.25", "Secure development life cycle", "Technological"),
    ("A.8.26", "Application security requirements", "Technological"),
    ("A.8.27", "Secure system architecture and engineering principles", "Technological"),
    ("A.8.28", "Secure coding", "Technological"),
    ("A.8.29", "Security testing in development and acceptance", "Technological"),
    ("A.8.30", "Outsourced development", "Technological"),
    ("A.8.31", "Separation of development, test and production environments", "Technological"),
    ("A.8.32", "Change management", "Technological"),
    ("A.8.33", "Test information", "Technological"),
    ("A.8.34", "Protection of information systems during audit testing", "Technological"),
]


ISO_27001_CLAUSES = {
    "4.1": "Understanding the organization and its context",
    "4.2": "Understanding the needs and expectations of interested parties",
    "4.3": "Determining the scope of the ISMS",
    "4.4": "Information security management system",
    "5.1": "Leadership and commitment",
    "5.2": "Policy",
    "5.3": "Organizational roles, responsibilities and authorities",
    "6.1": "Actions to address risks and opportunities",
    "6.2": "Information security objectives and planning to achieve them",
    "6.3": "Planning of changes",
    "7.1": "Resources",
    "7.2": "Competence",
    "7.3": "Awareness",
    "7.4": "Communication",
    "7.5": "Documented information",
    "8.1": "Operational planning and control",
    "8.2": "Information security risk assessment",
    "8.3": "Information security risk treatment",
    "9.1": "Monitoring, measurement, analysis and evaluation",
    "9.2": "Internal audit",
    "9.3": "Management review",
    "10.1": "Continual improvement",
    "10.2": "Nonconformity and corrective action",
}


def seed_frameworks(session) -> dict[str, int]:
    """Create or update framework records. Returns short_name -> id map."""
    fw_map = {}
    for fw_def in FRAMEWORKS:
        existing = session.execute(
            select(Framework).where(Framework.short_name == fw_def["short_name"])
        ).scalar_one_or_none()
        if existing:
            fw_map[fw_def["short_name"]] = existing.id
        else:
            fw = Framework(**fw_def)
            session.add(fw)
            session.flush()
            fw_map[fw_def["short_name"]] = fw.id
            print(f"  Created framework: {fw_def['name']}")
    return fw_map


def seed_iso_controls(session, fw_id: int):
    """Seed ISO 27001:2022 Annex A controls."""
    added = 0
    for ctrl_id, title, category in ISO_27001_CONTROLS:
        existing = session.execute(
            select(Control).where(
                Control.framework_id == fw_id,
                Control.control_id == ctrl_id,
            )
        ).scalar_one_or_none()
        if not existing:
            session.add(Control(
                framework_id=fw_id,
                control_id=ctrl_id,
                title=title,
                category=category,
            ))
            added += 1
    session.flush()
    print(f"  ISO 27001 controls: {added} added")


def ingest_document(session, parse_result: dict, target_fw_id: int, iso_fw_id: int, source_doc: str):
    """Import parsed controls and mappings into the database."""
    if not parse_result.get("success"):
        print(f"  Parse failed: {parse_result.get('error')}")
        return

    controls_added = 0
    mappings_added = 0

    # Add controls to target framework
    for ctrl in parse_result.get("controls", []):
        existing = session.execute(
            select(Control).where(
                Control.framework_id == target_fw_id,
                Control.control_id == ctrl["control_id"],
            )
        ).scalar_one_or_none()
        if not existing:
            session.add(Control(
                framework_id=target_fw_id,
                control_id=ctrl["control_id"],
                title=ctrl.get("title", ""),
                description=ctrl.get("description", ""),
                category=ctrl.get("category", ""),
            ))
            controls_added += 1
    session.flush()

    # Build lookup: (control_id, framework_id) -> db id
    all_controls = session.execute(
        select(Control.id, Control.control_id, Control.framework_id)
    ).all()
    lookup = {(r[1], r[2]): r[0] for r in all_controls}

    # Add mappings
    for m in parse_result.get("mappings", []):
        src_id = lookup.get((m["source"], iso_fw_id))
        tgt_id = lookup.get((m["target"], target_fw_id))

        # If the ISO control doesn't exist yet, create it
        if not src_id and m["source"]:
            existing = session.execute(
                select(Control).where(
                    Control.framework_id == iso_fw_id,
                    Control.control_id == m["source"],
                )
            ).scalar_one_or_none()
            if not existing:
                clause_title = ISO_27001_CLAUSES.get(
                    m["source"], f"ISO {m['source']}"
                )
                ctrl = Control(
                    framework_id=iso_fw_id,
                    control_id=m["source"],
                    title=clause_title,
                    category="Clause" if not m["source"].startswith("A.") else "Annex A",
                )
                session.add(ctrl)
                session.flush()
                src_id = ctrl.id
                lookup[(m["source"], iso_fw_id)] = src_id
            else:
                src_id = existing.id

        if src_id and tgt_id:
            existing = session.execute(
                select(Mapping).where(
                    Mapping.source_control_id == src_id,
                    Mapping.target_control_id == tgt_id,
                )
            ).scalar_one_or_none()
            if not existing:
                session.add(Mapping(
                    source_control_id=src_id,
                    target_control_id=tgt_id,
                    confidence=1.0,
                    source_type="official",
                    source_document=source_doc,
                ))
                mappings_added += 1

    session.flush()
    print(f"  Controls added: {controls_added}, Mappings added: {mappings_added}")


def main():
    parser = argparse.ArgumentParser(description="Seed the compliance mapping database")
    parser.add_argument("--bsi", type=str, help="Path to BSI Zuordnungstabelle PDF")
    parser.add_argument("--c5", type=str, help="Path to C5 cross-reference Excel")
    args = parser.parse_args()

    print("Initializing database...")
    init_db_sync()

    session = SyncSession()
    try:
        print("Seeding frameworks...")
        fw_map = seed_frameworks(session)

        print("Seeding ISO 27001 controls...")
        seed_iso_controls(session, fw_map["ISO27001"])

        # Fix placeholder clause titles from prior seeds
        for clause_id, clause_title in ISO_27001_CLAUSES.items():
            ctrl = session.execute(
                select(Control).where(
                    Control.framework_id == fw_map["ISO27001"],
                    Control.control_id == clause_id,
                )
            ).scalar_one_or_none()
            if ctrl and ctrl.title != clause_title:
                ctrl.title = clause_title
        session.flush()

        if args.bsi:
            bsi_path = Path(args.bsi)
            if bsi_path.exists():
                print(f"Ingesting BSI PDF: {bsi_path}")
                content = bsi_path.read_bytes()
                result = parse_bsi_zuordnung_pdf(content, "BSI Zuordnungstabelle")
                ingest_document(session, result, fw_map["BSI"], fw_map["ISO27001"], bsi_path.name)
            else:
                print(f"  BSI file not found: {bsi_path}")

        if args.c5:
            c5_path = Path(args.c5)
            if c5_path.exists():
                print(f"Ingesting C5 Excel: {c5_path}")
                content = c5_path.read_bytes()
                result = parse_excel(content, "C5 Cross-Reference")
                ingest_document(session, result, fw_map["C5"], fw_map["ISO27001"], c5_path.name)
            else:
                print(f"  C5 file not found: {c5_path}")

        session.commit()
        print("Done.")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
