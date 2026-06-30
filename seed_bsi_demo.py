"""
Seed BSI IT-Grundschutz Kompendium controls and ISO 27001 ↔ BSI mappings.

Based on the publicly available BSI IT-Grundschutz Kompendium Edition 2022
(https://www.bsi.bund.de/DE/Themen/Unternehmen-und-Organisationen/Standards-und-Zertifizierung/IT-Grundschutz/IT-Grundschutz-Kompendium/)
and the official BSI cross-reference table to ISO 27001:2022.
"""

import sys
from sqlalchemy import select
from database import init_db_sync, SyncSession, Framework, Control, Mapping

# ---------------------------------------------------------------------------
# BSI IT-Grundschutz modules (representative subset for demo)
# format: (control_id, title, category, description)
# ---------------------------------------------------------------------------

BSI_CONTROLS = [
    # ISMS - Security Management
    ("ISMS.1.A1",  "Übernahme der Gesamtverantwortung für Informationssicherheit durch die Leitung", "ISMS",
     "The management must take overall responsibility for information security and actively support the security process."),
    ("ISMS.1.A2",  "Festlegung der Sicherheitsziele und -strategie", "ISMS",
     "Information security objectives and strategy must be defined and documented."),
    ("ISMS.1.A3",  "Erstellung einer Leitlinie zur Informationssicherheit", "ISMS",
     "An information security policy must be created, approved by management, and communicated."),
    ("ISMS.1.A4",  "Benennung eines Informationssicherheitsbeauftragten", "ISMS",
     "An Information Security Officer (ISB) must be appointed with defined responsibilities."),
    ("ISMS.1.A6",  "Festlegung der Organisationsstruktur für Informationssicherheit", "ISMS",
     "Roles and responsibilities for information security must be defined and assigned."),
    ("ISMS.1.A8",  "Integration der Mitarbeiter in den Sicherheitsprozess", "ISMS",
     "All employees must be involved in the information security process and regularly trained."),

    # ORP - Organisation and Personnel
    ("ORP.1.A1",   "Festlegung von Verantwortlichkeiten und Regelungen", "ORP",
     "Responsibilities and rules for information security must be established and documented."),
    ("ORP.1.A2",   "Zuweisung der Zuständigkeiten für Informationssicherheit", "ORP",
     "Responsibilities for information security tasks must be clearly assigned."),
    ("ORP.2.A1",   "Geregelte Einarbeitung neuer Mitarbeiter", "ORP",
     "New employees must be systematically introduced to security policies and procedures."),
    ("ORP.2.A2",   "Geregelte Verfahrensweise beim Weggang von Mitarbeitern", "ORP",
     "A defined process must exist for revoking access rights and retrieving assets when employees leave."),
    ("ORP.2.A4",   "Festlegung von Regelungen für den Einsatz von Fremdpersonal", "ORP",
     "Rules for the use of external personnel and contractors must be defined and enforced."),
    ("ORP.3.A1",   "Sensibilisierung der Mitarbeiter für Informationssicherheit", "ORP",
     "Employees must be regularly sensitized to information security risks and responsibilities."),
    ("ORP.3.A2",   "Schulung des Personals", "ORP",
     "Personnel must receive regular training on information security relevant to their role."),
    ("ORP.4.A1",   "Regelungen für die Nutzung von Identitäten und Berechtigungen", "ORP",
     "Rules for using identities and access rights must be defined and implemented."),

    # CON - Concepts and Procedures
    ("CON.1.A1",   "Auswahl geeigneter kryptografischer Verfahren", "CON",
     "Suitable cryptographic methods must be selected based on protection requirements."),
    ("CON.1.A2",   "Datensicherungskonzept", "CON",
     "A backup concept must be created covering backup requirements, procedures, and restoration testing."),
    ("CON.3.A1",   "Erhebung der Einflussfaktoren der Datensicherung", "CON",
     "Factors influencing data backup requirements must be identified and documented."),
    ("CON.3.A2",   "Festlegung der Verfahrensweise für die Datensicherung", "CON",
     "Backup procedures must be defined covering frequency, method, and retention."),
    ("CON.6.A1",   "Regelung der Vorgehensweise für Löschung und Vernichtung", "CON",
     "Procedures for secure deletion and destruction of data and media must be defined."),
    ("CON.7.A1",   "Sicherheitsrichtlinie für die mobile Nutzung", "CON",
     "A security policy for mobile device use must be created and communicated to users."),
    ("CON.8.A1",   "Definition von Sicherheitsanforderungen für Softwareentwicklungsprojekte", "CON",
     "Security requirements must be defined at the start of every software development project."),

    # OPS - Operations
    ("OPS.1.1.2.A1", "Ordnungsgemäße IT-Administration", "OPS",
     "IT systems must be administered in an orderly manner with defined responsibilities."),
    ("OPS.1.1.3.A1", "Konzept für das Patch- und Änderungsmanagement", "OPS",
     "A patch and change management concept must be developed and implemented."),
    ("OPS.1.1.4.A1", "Erstellung eines Schutzkonzepts gegen Schadprogramme", "OPS",
     "A protection concept against malware must be created covering detection and response."),
    ("OPS.1.1.5.A1", "Erstellung einer Sicherheitsrichtlinie für die Protokollierung", "OPS",
     "A logging security policy must be defined specifying what must be logged and for how long."),
    ("OPS.1.2.2.A1", "Festlegung der Anforderungen an Archivierung", "OPS",
     "Requirements for archiving must be defined including retention periods and formats."),
    ("OPS.2.2.A1",   "Erstellung eines Cloud-Nutzungskonzepts", "OPS",
     "A cloud usage concept must be created before cloud services are adopted."),

    # APP - Applications
    ("APP.1.1.A1",  "Sicherstellen der Integrität von Office-Produkten", "APP",
     "The integrity of office software must be ensured through secure installation processes."),
    ("APP.3.1.A1",  "Authentisierung bei Webanwendungen", "APP",
     "Web applications must implement secure authentication mechanisms."),
    ("APP.3.1.A2",  "Zugriffskontrolle bei Webanwendungen", "APP",
     "Web applications must implement proper access control to protect data and functions."),
    ("APP.3.2.A1",  "Planung des Einsatzes eines Webservers", "APP",
     "The deployment of web servers must be planned including security requirements."),
    ("APP.5.2.A1",  "Sichere Grundkonfiguration für Microsoft Exchange", "APP",
     "Microsoft Exchange must be configured securely according to baseline hardening guidelines."),

    # SYS - IT Systems
    ("SYS.1.1.A1",  "Geeignete Aufstellung von IT-Systemen", "SYS",
     "IT systems must be physically positioned to protect against unauthorized access and environmental threats."),
    ("SYS.1.1.A3",  "Aktivieren von Autoupdate-Mechanismen", "SYS",
     "Automatic update mechanisms must be activated or a regular manual update process established."),
    ("SYS.1.2.A1",  "Planung von Windows Server", "SYS",
     "The deployment of Windows Server systems must be planned including security configuration."),
    ("SYS.2.1.A1",  "Festlegung einer Sicherheitsrichtlinie für Clients", "SYS",
     "A security policy for client systems must be defined and enforced."),
    ("SYS.3.1.A1",  "Regelungen für mobile Endgeräte", "SYS",
     "Rules for mobile devices must be established covering use, security, and management."),
    ("SYS.3.2.2.A1","Festlegung einer Strategie für das Mobile Device Management", "SYS",
     "A Mobile Device Management (MDM) strategy must be defined and documented."),

    # NET - Networks
    ("NET.1.1.A1",  "Sicherheitsrichtlinie für die Netz-Architektur", "NET",
     "A security policy for network architecture must be created."),
    ("NET.1.1.A2",  "Dokumentation des Netzes", "NET",
     "The network topology and all components must be documented and kept up to date."),
    ("NET.1.2.A1",  "Planung des Netzmanagements", "NET",
     "Network management must be planned including monitoring, configuration management, and access control."),
    ("NET.3.2.A1",  "Erstellung einer Sicherheitsrichtlinie für Firewalls", "NET",
     "A security policy for firewalls must be created defining allowed and denied traffic."),

    # INF - Infrastructure
    ("INF.1.A1",   "Planung der Gebäudesicherheit", "INF",
     "Building security must be planned to protect IT infrastructure from physical threats."),
    ("INF.1.A2",   "Angepasste Aufteilung der Zutrittsrechte", "INF",
     "Access rights to buildings and secure areas must be appropriately distributed."),
    ("INF.2.A1",   "Festlegung von Anforderungen an Rechenzentren", "INF",
     "Requirements for data centers must be defined covering physical security, power, and cooling."),
    ("INF.8.A1",   "Sichere Nutzung von häuslichen Arbeitsplätzen", "INF",
     "Home workplaces must meet defined security requirements for physical and logical security."),

    # DER - Detection and Response
    ("DER.1.A1",   "Erstellung einer Sicherheitsrichtlinie für die Detektion von Sicherheitsvorfällen", "DER",
     "A policy for detecting security incidents must be created defining monitoring requirements."),
    ("DER.2.1.A1", "Definition eines Sicherheitsvorfalls", "DER",
     "Security incidents must be defined and classified to ensure consistent detection and response."),
    ("DER.2.1.A2", "Erstellung eines Incident-Response-Plans", "DER",
     "An incident response plan must be created covering roles, procedures, and communication."),
    ("DER.2.2.A1", "Erstellung eines Leitfadens für IT-Forensik", "DER",
     "A forensics guide must be created covering evidence preservation and investigation procedures."),
    ("DER.4.A1",   "Erstellung eines Konzepts für Business Continuity Management", "DER",
     "A Business Continuity Management (BCM) concept must be created covering critical processes."),
]

# ---------------------------------------------------------------------------
# Official ISO 27001:2022 ↔ BSI mappings
# Based on BSI-Standard 200-2 cross-reference table (public document)
# ---------------------------------------------------------------------------

ISO_BSI_MAPPINGS = [
    # A.5 Organizational controls
    ("A.5.1",  "ISMS.1.A3"),   # Policies ↔ Security policy
    ("A.5.1",  "ISMS.1.A2"),   # Policies ↔ Security objectives
    ("A.5.2",  "ISMS.1.A4"),   # Roles ↔ ISB appointment
    ("A.5.2",  "ORP.1.A2"),    # Roles ↔ Responsibility assignment
    ("A.5.3",  "ORP.1.A1"),    # Segregation ↔ Responsibilities
    ("A.5.4",  "ISMS.1.A1"),   # Management resp ↔ Overall responsibility
    ("A.5.7",  "DER.1.A1"),    # Threat intel ↔ Detection policy
    ("A.5.8",  "CON.8.A1"),    # Project management ↔ SW security requirements
    ("A.5.15", "ORP.4.A1"),    # Access control ↔ Identity/permission rules
    ("A.5.16", "ORP.4.A1"),    # Identity management ↔ Identity/permission rules
    ("A.5.17", "APP.3.1.A1"),  # Authentication info ↔ Web app authentication
    ("A.5.18", "ORP.4.A1"),    # Access rights ↔ Identity/permission rules
    ("A.5.19", "ORP.2.A4"),    # Supplier security ↔ External personnel rules
    ("A.5.23", "OPS.2.2.A1"),  # Cloud services ↔ Cloud usage concept
    ("A.5.24", "DER.2.1.A2"),  # Incident mgmt planning ↔ IR plan
    ("A.5.25", "DER.2.1.A1"),  # Assessment of events ↔ Incident definition
    ("A.5.26", "DER.2.1.A2"),  # Incident response ↔ IR plan
    ("A.5.27", "DER.2.1.A2"),  # Learning from incidents ↔ IR plan
    ("A.5.28", "DER.2.2.A1"),  # Evidence ↔ Forensics guide
    ("A.5.29", "DER.4.A1"),    # Business continuity ↔ BCM concept
    ("A.5.30", "DER.4.A1"),    # ICT readiness ↔ BCM concept
    ("A.5.33", "OPS.1.2.2.A1"),# Protection of records ↔ Archiving
    ("A.5.36", "ISMS.1.A3"),   # Compliance ↔ Security policy

    # A.6 People controls
    ("A.6.1",  "ORP.2.A1"),    # Screening ↔ New employee onboarding
    ("A.6.2",  "ORP.2.A1"),    # Terms of employment ↔ New employee onboarding
    ("A.6.3",  "ORP.3.A2"),    # Training ↔ Personnel training
    ("A.6.3",  "ORP.3.A1"),    # Awareness ↔ Security awareness
    ("A.6.4",  "ORP.1.A1"),    # Disciplinary ↔ Responsibilities
    ("A.6.5",  "ORP.2.A2"),    # Termination ↔ Employee departure
    ("A.6.7",  "CON.7.A1"),    # Remote working ↔ Mobile security policy
    ("A.6.8",  "DER.2.1.A1"),  # Event reporting ↔ Incident definition

    # A.7 Physical controls
    ("A.7.1",  "INF.1.A1"),    # Physical perimeters ↔ Building security
    ("A.7.2",  "INF.1.A2"),    # Physical entry ↔ Access rights
    ("A.7.3",  "INF.1.A1"),    # Secure offices ↔ Building security
    ("A.7.4",  "INF.1.A1"),    # Physical monitoring ↔ Building security
    ("A.7.8",  "SYS.1.1.A1"),  # Equipment siting ↔ IT system placement
    ("A.7.9",  "SYS.3.1.A1"),  # Off-premises assets ↔ Mobile device rules
    ("A.7.10", "CON.6.A1"),    # Storage media ↔ Deletion/destruction
    ("A.7.11", "INF.2.A1"),    # Supporting utilities ↔ Data center requirements
    ("A.7.12", "INF.2.A1"),    # Cabling ↔ Data center requirements
    ("A.7.14", "CON.6.A1"),    # Secure disposal ↔ Deletion/destruction

    # A.8 Technological controls
    ("A.8.1",  "SYS.2.1.A1"),  # User endpoints ↔ Client security policy
    ("A.8.2",  "ORP.4.A1"),    # Privileged access ↔ Identity/permission rules
    ("A.8.3",  "APP.3.1.A2"),  # Access restriction ↔ Web app access control
    ("A.8.5",  "APP.3.1.A1"),  # Secure authentication ↔ Web app authentication
    ("A.8.7",  "OPS.1.1.4.A1"),# Malware ↔ Malware protection concept
    ("A.8.8",  "OPS.1.1.3.A1"),# Vulnerability mgmt ↔ Patch management
    ("A.8.9",  "OPS.1.1.2.A1"),# Config mgmt ↔ IT administration
    ("A.8.10", "CON.6.A1"),    # Data deletion ↔ Deletion/destruction
    ("A.8.11", "CON.1.A1"),    # Data masking ↔ Cryptographic methods
    ("A.8.12", "NET.1.1.A1"),  # DLP ↔ Network architecture policy
    ("A.8.13", "CON.3.A2"),    # Backup ↔ Backup procedures
    ("A.8.13", "CON.3.A1"),    # Backup ↔ Backup requirements
    ("A.8.14", "DER.4.A1"),    # Redundancy ↔ BCM concept
    ("A.8.15", "OPS.1.1.5.A1"),# Logging ↔ Logging policy
    ("A.8.16", "DER.1.A1"),    # Monitoring ↔ Detection policy
    ("A.8.19", "OPS.1.1.3.A1"),# Software installation ↔ Patch/change mgmt
    ("A.8.20", "NET.1.1.A1"),  # Network security ↔ Network architecture policy
    ("A.8.20", "NET.1.1.A2"),  # Network security ↔ Network documentation
    ("A.8.21", "NET.3.2.A1"),  # Network services ↔ Firewall policy
    ("A.8.22", "NET.1.1.A1"),  # Network segregation ↔ Network architecture
    ("A.8.24", "CON.1.A1"),    # Cryptography ↔ Cryptographic methods
    ("A.8.25", "CON.8.A1"),    # Secure dev lifecycle ↔ SW security requirements
    ("A.8.32", "OPS.1.1.3.A1"),# Change management ↔ Patch/change mgmt
]


def run():
    print("Initializing database...")
    init_db_sync()
    session = SyncSession()

    try:
        # Get framework IDs
        iso_fw = session.execute(
            select(Framework).where(Framework.short_name == "ISO27001")
        ).scalar_one_or_none()
        bsi_fw = session.execute(
            select(Framework).where(Framework.short_name == "BSI")
        ).scalar_one_or_none()

        if not iso_fw or not bsi_fw:
            print("ERROR: Frameworks not found. Run seed_data.py first.")
            sys.exit(1)

        # Seed BSI controls
        print(f"Seeding {len(BSI_CONTROLS)} BSI IT-Grundschutz controls...")
        bsi_added = 0
        for ctrl_id, title, category, description in BSI_CONTROLS:
            existing = session.execute(
                select(Control).where(
                    Control.framework_id == bsi_fw.id,
                    Control.control_id == ctrl_id,
                )
            ).scalar_one_or_none()
            if not existing:
                session.add(Control(
                    framework_id=bsi_fw.id,
                    control_id=ctrl_id,
                    title=title,
                    description=description,
                    category=category,
                ))
                bsi_added += 1
        session.flush()
        print(f"  BSI controls added: {bsi_added}")

        # Build lookup
        all_controls = session.execute(
            select(Control.id, Control.control_id, Control.framework_id)
        ).all()
        lookup = {(r[1], r[2]): r[0] for r in all_controls}

        # Seed ISO ↔ BSI mappings
        print(f"Seeding {len(ISO_BSI_MAPPINGS)} ISO 27001 ↔ BSI mappings...")
        map_added = 0
        for iso_id, bsi_id in ISO_BSI_MAPPINGS:
            src = lookup.get((iso_id, iso_fw.id))
            tgt = lookup.get((bsi_id, bsi_fw.id))
            if not src or not tgt:
                continue
            existing = session.execute(
                select(Mapping).where(
                    Mapping.source_control_id == src,
                    Mapping.target_control_id == tgt,
                )
            ).scalar_one_or_none()
            if not existing:
                session.add(Mapping(
                    source_control_id=src,
                    target_control_id=tgt,
                    confidence=1.0,
                    source_type="official",
                    source_document="BSI-Standard 200-2 / ISO 27001:2022 cross-reference",
                ))
                map_added += 1

        session.commit()
        print(f"  Mappings added: {map_added}")
        print("Done! BSI controls and ISO↔BSI mappings are ready.")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
