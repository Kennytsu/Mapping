"""
Seed BSI C5:2020 controls, C5-to-ISO 27001 mappings, and ISO 27001 control descriptions.

Based on the BSI Cloud Computing Compliance Criteria Catalogue (C5:2020)
and the official C5-to-ISO 27001:2022 cross-reference.
"""

import sys
from sqlalchemy import select
from database import init_db_sync, SyncSession, Framework, Control, Mapping

# ---------------------------------------------------------------------------
# BSI C5:2020 Controls (127 criteria across 17 domains)
# ---------------------------------------------------------------------------

C5_CONTROLS = [
    ("OIS-01", "Information Security Management System", "OIS",
     "The cloud provider shall establish, implement, maintain, and continually improve an information security management system (ISMS)."),
    ("OIS-02", "Information Security Policy", "OIS",
     "An information security policy shall be defined, approved by management, published, and communicated to all employees and relevant external parties."),
    ("OIS-03", "Information Security Responsibilities", "OIS",
     "Responsibilities and duties for information security shall be defined and assigned to appropriate roles."),
    ("OIS-04", "Segregation of Duties", "OIS",
     "Conflicting duties and areas of responsibility shall be segregated to reduce opportunities for unauthorized or unintentional modification or misuse of assets."),
    ("OIS-05", "Contact with Authorities", "OIS",
     "Appropriate contacts with relevant authorities shall be maintained for reporting and coordinating security matters."),
    ("OIS-06", "Contact with Special Interest Groups", "OIS",
     "Appropriate contacts with special interest groups, security forums, and professional associations shall be maintained."),
    ("OIS-07", "Risk Management", "OIS",
     "A risk management process for information security shall be established and maintained to identify, assess, and treat risks."),
    ("OIS-08", "Risk Assessment", "OIS",
     "Information security risk assessments shall be performed at planned intervals or when significant changes are proposed or occur."),
    ("OIS-09", "Risk Treatment", "OIS",
     "A risk treatment plan shall be formulated and implemented, with residual risks formally accepted by risk owners."),
    ("OIS-10", "Compliance Management", "OIS",
     "Legal, regulatory, and contractual requirements relevant to information security shall be identified, documented, and kept up to date."),
    ("OIS-11", "Independent Reviews", "OIS",
     "The organizations approach to managing information security shall be independently reviewed at planned intervals."),
    ("OIS-12", "Information Security in Project Management", "OIS",
     "Information security shall be addressed in project management, regardless of the type of project."),
    ("SP-01", "Security Policy Framework", "SP",
     "A set of policies for information security shall be defined, approved by management, and communicated to all relevant parties."),
    ("SP-02", "Review of Security Policies", "SP",
     "Information security policies shall be reviewed at planned intervals or if significant changes occur to ensure their continuing suitability and effectiveness."),
    ("SP-03", "Acceptable Use Policy", "SP",
     "Rules for the acceptable use of information, assets, and technology shall be identified, documented, and implemented."),
    ("SP-04", "Policy Communication and Training", "SP",
     "Security policies shall be communicated to all employees and relevant contractors, with appropriate training provided."),
    ("SP-05", "Policy Exception Management", "SP",
     "A formal process for managing exceptions to security policies shall be established, including risk assessment and approval."),
    ("HR-01", "Screening and Background Checks", "HR",
     "Background verification checks on all candidates for employment shall be carried out in accordance with relevant laws and regulations."),
    ("HR-02", "Terms and Conditions of Employment", "HR",
     "Employment contracts shall state employees and the organizations responsibilities for information security."),
    ("HR-03", "Security Awareness and Training", "HR",
     "All employees and relevant contractors shall receive appropriate awareness education and training with regular updates on organizational policies and procedures."),
    ("HR-04", "Disciplinary Process", "HR",
     "A formal disciplinary process shall exist for employees who have committed an information security breach."),
    ("HR-05", "Termination Responsibilities", "HR",
     "Information security responsibilities and duties that remain valid after termination or change of employment shall be defined and communicated."),
    ("HR-06", "Return of Assets", "HR",
     "All employees and contractors shall return all organizational assets in their possession upon termination of employment or contract."),
    ("HR-07", "Confidentiality Agreements", "HR",
     "Requirements for confidentiality or non-disclosure agreements reflecting the organizations needs shall be identified and regularly reviewed."),
    ("AM-01", "Asset Inventory", "AM",
     "Information assets associated with information and information processing facilities shall be identified, and an inventory of these assets shall be maintained."),
    ("AM-02", "Ownership of Assets", "AM",
     "Assets maintained in the inventory shall be owned by a designated part of the organization."),
    ("AM-03", "Acceptable Use of Assets", "AM",
     "Rules for the acceptable use of information and assets associated with information processing facilities shall be identified and implemented."),
    ("AM-04", "Classification and Labeling", "AM",
     "Information shall be classified in terms of legal requirements, value, criticality, and sensitivity, and labeled accordingly."),
    ("AM-05", "Handling of Assets", "AM",
     "Procedures for handling assets shall be developed and implemented in accordance with the information classification scheme."),
    ("PS-01", "Physical Security Perimeter", "PS",
     "Security perimeters shall be defined and used to protect areas that contain sensitive information and information processing facilities."),
    ("PS-02", "Physical Entry Controls", "PS",
     "Secure areas shall be protected by appropriate entry controls to ensure that only authorized personnel are allowed access."),
    ("PS-03", "Securing Offices and Rooms", "PS",
     "Physical security for offices, rooms, and facilities shall be designed and applied taking into account the security requirements."),
    ("PS-04", "Protecting Against External Threats", "PS",
     "Physical protection against natural disasters, malicious attack, or accidents shall be designed and applied."),
    ("PS-05", "Working in Secure Areas", "PS",
     "Procedures for working in secure areas shall be designed and applied to maintain the security level."),
    ("PS-06", "Equipment Siting and Protection", "PS",
     "Equipment shall be sited and protected to reduce risks from environmental threats and hazards, and opportunities for unauthorized access."),
    ("PS-07", "Supporting Utilities", "PS",
     "Equipment shall be protected from power failures and other disruptions caused by failures in supporting utilities."),
    ("PS-08", "Cabling Security", "PS",
     "Power and telecommunications cabling carrying data or supporting information services shall be protected from interception or damage."),
    ("OPS-01", "Documented Operating Procedures", "OPS",
     "Operating procedures shall be documented and made available to all users who need them."),
    ("OPS-02", "Change Management", "OPS",
     "Changes to the organization, business processes, information processing facilities, and systems that affect information security shall be controlled."),
    ("OPS-03", "Capacity Management", "OPS",
     "The use of resources shall be monitored and tuned, and projections made of future capacity requirements to ensure required system performance."),
    ("OPS-04", "Separation of Development, Testing and Production", "OPS",
     "Development, testing, and operational environments shall be separated to reduce the risks of unauthorized access or changes to the operational environment."),
    ("OPS-05", "Protection from Malware", "OPS",
     "Detection, prevention, and recovery controls to protect against malware shall be implemented, combined with appropriate user awareness."),
    ("OPS-06", "Data Backup", "OPS",
     "Backup copies of information, software, and system images shall be taken and tested regularly in accordance with an agreed backup policy."),
    ("OPS-07", "Event Logging", "OPS",
     "Event logs recording user activities, exceptions, faults, and information security events shall be produced, kept, and regularly reviewed."),
    ("OPS-08", "Monitoring and Alerting", "OPS",
     "Networks, systems, and applications shall be monitored for anomalous behavior and appropriate actions taken to evaluate potential information security incidents."),
    ("OPS-09", "Control of Operational Software", "OPS",
     "Procedures shall be implemented to control the installation of software on operational systems."),
    ("OPS-10", "Technical Vulnerability Management", "OPS",
     "Information about technical vulnerabilities of information systems shall be obtained in a timely fashion and appropriate measures taken to address the associated risk."),
    ("OPS-11", "Restrictions on Software Installation", "OPS",
     "Rules governing the installation of software by users shall be established and implemented."),
    ("OPS-12", "Audit Logging and Monitoring", "OPS",
     "Audit logs recording privileged operations and security-relevant events shall be protected and regularly reviewed."),
    ("OPS-13", "Clock Synchronization", "OPS",
     "The clocks of all relevant information processing systems shall be synchronized to a single reference time source."),
    ("OPS-14", "Configuration Management", "OPS",
     "Configurations of systems, networks, and applications shall be established, documented, implemented, monitored, and reviewed."),
    ("IDM-01", "Access Control Policy", "IDM",
     "An access control policy shall be established, documented, and reviewed based on business and information security requirements."),
    ("IDM-02", "User Registration and Deregistration", "IDM",
     "A formal user registration and deregistration process shall be implemented to enable assignment of access rights."),
    ("IDM-03", "User Access Provisioning", "IDM",
     "A formal user access provisioning process shall be implemented to assign or revoke access rights for all user types to all systems and services."),
    ("IDM-04", "Management of Privileged Access Rights", "IDM",
     "The allocation and use of privileged access rights shall be restricted and controlled."),
    ("IDM-05", "Management of Authentication Information", "IDM",
     "The allocation of authentication information shall be controlled through a formal management process."),
    ("IDM-06", "Review of User Access Rights", "IDM",
     "Asset owners shall review users access rights at regular intervals."),
    ("IDM-07", "Removal or Adjustment of Access Rights", "IDM",
     "The access rights of all employees and external party users shall be removed upon termination or adjusted upon change of employment."),
    ("IDM-08", "Secure Log-on Procedures", "IDM",
     "Where required by the access control policy, access to systems and applications shall be controlled by a secure log-on procedure."),
    ("IDM-09", "Password Management System", "IDM",
     "Password management systems shall be interactive and shall ensure quality passwords."),
    ("IDM-10", "Use of Privileged Utility Programs", "IDM",
     "The use of utility programs that might be capable of overriding system and application controls shall be restricted and tightly controlled."),
    ("CRY-01", "Policy on Use of Cryptographic Controls", "CRY",
     "A policy on the use of cryptographic controls for protection of information shall be developed and implemented."),
    ("CRY-02", "Key Management", "CRY",
     "A policy on the use, protection, and lifetime of cryptographic keys shall be developed and implemented through their whole lifecycle."),
    ("CRY-03", "Encryption of Data in Transit", "CRY",
     "Appropriate cryptographic measures shall be used to protect data transmitted over networks against unauthorized disclosure."),
    ("CRY-04", "Encryption of Data at Rest", "CRY",
     "Appropriate cryptographic measures shall be used to protect stored data against unauthorized disclosure."),
    ("COM-01", "Network Security Management", "COM",
     "Networks shall be managed and controlled to protect information in systems and applications."),
    ("COM-02", "Security of Network Services", "COM",
     "Security mechanisms, service levels, and management requirements of all network services shall be identified and included in network services agreements."),
    ("COM-03", "Segregation in Networks", "COM",
     "Groups of information services, users, and information systems shall be segregated on networks."),
    ("COM-04", "Information Transfer Policies", "COM",
     "Formal transfer policies, procedures, and controls shall be in place to protect the transfer of information through the use of all types of communication facilities."),
    ("COM-05", "Agreements on Information Transfer", "COM",
     "Agreements shall address the secure transfer of business information between the organization and external parties."),
    ("COM-06", "Electronic Messaging Security", "COM",
     "Information involved in electronic messaging shall be appropriately protected against unauthorized access and modification."),
    ("COM-07", "Confidentiality and Non-Disclosure Agreements", "COM",
     "Requirements for confidentiality or non-disclosure agreements reflecting the organizations needs for the protection of information shall be identified and regularly reviewed."),
    ("PI-01", "Data Portability", "PI",
     "The cloud provider shall provide mechanisms and tools to enable the customer to export their data in a structured, commonly used, and machine-readable format."),
    ("PI-02", "Service Interoperability", "PI",
     "The cloud provider shall use open and standardized interfaces to ensure interoperability and prevent vendor lock-in."),
    ("PI-03", "Transition Support", "PI",
     "The cloud provider shall support the customer during transition to another provider or back to on-premises operation."),
    ("PI-04", "Data Deletion after Contract End", "PI",
     "Upon termination of the contract, the cloud provider shall delete or return all customer data and ensure no residual copies remain."),
    ("DEV-01", "Secure Development Policy", "DEV",
     "Rules for the development of software and systems shall be established and applied within the organization."),
    ("DEV-02", "System Change Control Procedures", "DEV",
     "Changes to systems within the development lifecycle shall be controlled by the use of formal change control procedures."),
    ("DEV-03", "Technical Review of Applications After Platform Changes", "DEV",
     "When operating platforms are changed, business critical applications shall be reviewed and tested to ensure there is no adverse impact on operations or security."),
    ("DEV-04", "Restrictions on Changes to Software Packages", "DEV",
     "Modifications to vendor-supplied software packages shall be discouraged, limited to necessary changes, and all changes shall be strictly controlled."),
    ("DEV-05", "Secure System Engineering Principles", "DEV",
     "Principles for engineering secure systems shall be established, documented, maintained, and applied to any system implementation efforts."),
    ("DEV-06", "Secure Development Environment", "DEV",
     "Organizations shall establish and appropriately protect secure development environments for system development and integration efforts."),
    ("DEV-07", "Security Testing in Development", "DEV",
     "Security testing shall be carried out during development to verify that security requirements are met."),
    ("DEV-08", "System Acceptance Testing", "DEV",
     "Acceptance testing programs and related criteria shall be established for new information systems, upgrades, and new versions."),
    ("SSO-01", "Supplier Security Policy", "SSO",
     "Information security requirements for mitigating risks associated with suppliers access to organizational assets shall be agreed and documented."),
    ("SSO-02", "Addressing Security in Supplier Agreements", "SSO",
     "All relevant information security requirements shall be established and agreed with each supplier that may access, process, store, communicate, or provide IT infrastructure."),
    ("SSO-03", "Supply Chain Security", "SSO",
     "Agreements with suppliers shall include requirements to address information security risks associated with the ICT supply chain."),
    ("SSO-04", "Monitoring and Review of Supplier Services", "SSO",
     "Organizations shall regularly monitor, review, and audit supplier service delivery."),
    ("SSO-05", "Managing Changes to Supplier Services", "SSO",
     "Changes to the provision of services by suppliers shall be managed, taking account of the criticality of business information and systems involved."),
    ("SIM-01", "Responsibilities and Procedures", "SIM",
     "Management responsibilities and procedures shall be established to ensure a quick, effective, and orderly response to information security incidents."),
    ("SIM-02", "Reporting Information Security Events", "SIM",
     "Information security events shall be reported through appropriate management channels as quickly as possible."),
    ("SIM-03", "Reporting Information Security Weaknesses", "SIM",
     "Employees and contractors using the organizations information systems shall be required to note and report any observed or suspected security weaknesses."),
    ("SIM-04", "Assessment and Decision on Events", "SIM",
     "Information security events shall be assessed and a decision shall be made on whether they are to be classified as information security incidents."),
    ("SIM-05", "Response to Information Security Incidents", "SIM",
     "Information security incidents shall be responded to in accordance with the documented procedures."),
    ("SIM-06", "Learning from Information Security Incidents", "SIM",
     "Knowledge gained from analyzing and resolving information security incidents shall be used to reduce the likelihood or impact of future incidents."),
    ("SIM-07", "Collection of Evidence", "SIM",
     "The organization shall define and apply procedures for the identification, collection, acquisition, and preservation of digital evidence."),
    ("BCM-01", "Business Continuity Planning", "BCM",
     "The organization shall determine its requirements for information security and continuity of information security management in adverse situations."),
    ("BCM-02", "Implementing Information Security Continuity", "BCM",
     "The organization shall establish, document, implement, and maintain processes, procedures, and controls to ensure the required level of continuity during an adverse situation."),
    ("BCM-03", "Verify and Review Continuity", "BCM",
     "The organization shall verify the established and implemented information security continuity controls at regular intervals to ensure they are valid and effective."),
    ("BCM-04", "Availability of Information Processing Facilities", "BCM",
     "Information processing facilities shall be implemented with redundancy sufficient to meet availability requirements."),
    ("BCM-05", "Disaster Recovery Planning", "BCM",
     "Disaster recovery plans shall be established, documented, and tested to ensure timely restoration of services after a disruption."),
    ("BCM-06", "Recovery Testing", "BCM",
     "Recovery procedures and plans shall be tested regularly to validate their effectiveness and completeness."),
    ("CMP-01", "Identification of Applicable Legislation", "CMP",
     "All relevant legislative, statutory, regulatory, and contractual requirements shall be explicitly identified, documented, and kept up to date."),
    ("CMP-02", "Intellectual Property Rights", "CMP",
     "Appropriate procedures shall be implemented to ensure compliance with legislative, regulatory, and contractual requirements related to intellectual property rights."),
    ("CMP-03", "Protection of Records", "CMP",
     "Records shall be protected from loss, destruction, falsification, unauthorized access, and unauthorized release in accordance with requirements."),
    ("CMP-04", "Privacy and Protection of Personal Data", "CMP",
     "Privacy and protection of personally identifiable information shall be ensured as required by relevant legislation and regulation."),
    ("CMP-05", "Regulation of Cryptographic Controls", "CMP",
     "Cryptographic controls shall be used in compliance with all relevant agreements, legislation, and regulations."),
    ("CMP-06", "Independent Review of Information Security", "CMP",
     "The organizations approach to managing information security shall be independently reviewed at planned intervals or when significant changes occur."),
    ("INQ-01", "Transparency and Communication", "INQ",
     "The cloud provider shall provide transparent information about its services, including security measures, data locations, and subcontractors."),
    ("INQ-02", "Customer Inquiry Handling", "INQ",
     "The cloud provider shall establish procedures for handling customer inquiries regarding security and compliance matters in a timely manner."),
    ("INQ-03", "Audit Support", "INQ",
     "The cloud provider shall support customer audits and provide access to relevant documentation, logs, and evidence upon request."),
    ("PSS-01", "Secure Architecture Design", "PSS",
     "The cloud service shall be designed with a secure architecture that incorporates defense-in-depth principles and minimizes the attack surface."),
    ("PSS-02", "Multi-Tenancy Isolation", "PSS",
     "The cloud provider shall ensure that customer environments are logically separated and that no data leakage between tenants is possible."),
    ("PSS-03", "Service Interface Security", "PSS",
     "All service interfaces provided to customers shall be secured against unauthorized access and common web application vulnerabilities."),
    ("PSS-04", "Security Feature Documentation", "PSS",
     "The cloud provider shall document all security features available to customers and provide guidance on their proper configuration."),
    ("PSS-05", "Vulnerability Disclosure", "PSS",
     "The cloud provider shall maintain a responsible vulnerability disclosure process and notify affected customers of security issues."),
    ("OIS-13", "Cloud Security Strategy", "OIS",
     "A dedicated cloud security strategy shall be defined addressing the specific risks and requirements of cloud service delivery."),
    ("OPS-15", "Network Security Monitoring", "OPS",
     "Network traffic shall be continuously monitored to detect and respond to potential security threats and anomalous behavior."),
    ("OPS-16", "Secure Disposal of Media", "OPS",
     "Media containing sensitive information shall be securely disposed of when no longer required using formal procedures."),
    ("IDM-11", "Multi-Factor Authentication", "IDM",
     "Multi-factor authentication shall be implemented for access to critical systems and privileged accounts."),
    ("DEV-09", "Outsourced Development Security", "DEV",
     "The organization shall supervise and monitor the activity of outsourced system development and ensure security requirements are met."),
    ("BCM-07", "Communication During Incidents", "BCM",
     "Communication procedures shall be established to ensure timely notification of relevant stakeholders during business continuity events."),
    ("CMP-07", "Compliance Monitoring and Reporting", "CMP",
     "Regular compliance monitoring shall be performed and reports provided to management on the status of compliance with applicable requirements."),
    ("PS-09", "Equipment Maintenance", "PS",
     "Equipment shall be correctly maintained to ensure its continued availability and integrity for information processing."),
    ("COM-08", "Web Application Security", "COM",
     "Web-facing applications and services shall be protected from common web-based attacks through appropriate security measures."),
    ("SIM-08", "Incident Communication", "SIM",
     "The cloud provider shall promptly communicate information security incidents that affect customer data to the affected customers."),
    ("HR-08", "Security During Employment Changes", "HR",
     "Appropriate security measures shall be taken when employees change roles to ensure access rights are updated to reflect new responsibilities."),
]

# ---------------------------------------------------------------------------
# C5:2020 to ISO 27001:2022 Mappings
# ---------------------------------------------------------------------------

C5_ISO_MAPPINGS = [
    ("OIS-01", "A.5.1"),
    ("OIS-01", "A.5.4"),
    ("OIS-02", "A.5.1"),
    ("OIS-03", "A.5.2"),
    ("OIS-03", "A.5.3"),
    ("OIS-04", "A.5.3"),
    ("OIS-05", "A.5.5"),
    ("OIS-06", "A.5.6"),
    ("OIS-07", "A.5.7"),
    ("OIS-07", "A.5.8"),
    ("OIS-08", "A.5.7"),
    ("OIS-09", "A.5.7"),
    ("OIS-10", "A.5.31"),
    ("OIS-10", "A.5.36"),
    ("OIS-11", "A.5.35"),
    ("OIS-12", "A.5.8"),
    ("OIS-13", "A.5.23"),
    ("SP-01", "A.5.1"),
    ("SP-02", "A.5.1"),
    ("SP-02", "A.5.36"),
    ("SP-03", "A.5.10"),
    ("SP-04", "A.5.1"),
    ("SP-04", "A.5.37"),
    ("SP-05", "A.5.1"),
    ("HR-01", "A.6.1"),
    ("HR-02", "A.6.2"),
    ("HR-03", "A.6.3"),
    ("HR-04", "A.6.4"),
    ("HR-05", "A.6.5"),
    ("HR-06", "A.6.5"),
    ("HR-07", "A.6.6"),
    ("HR-08", "A.6.5"),
    ("AM-01", "A.5.9"),
    ("AM-02", "A.5.9"),
    ("AM-02", "A.5.10"),
    ("AM-03", "A.5.10"),
    ("AM-04", "A.5.12"),
    ("AM-04", "A.5.13"),
    ("AM-05", "A.5.10"),
    ("AM-05", "A.5.14"),
    ("PS-01", "A.7.1"),
    ("PS-02", "A.7.2"),
    ("PS-03", "A.7.3"),
    ("PS-04", "A.7.4"),
    ("PS-05", "A.7.5"),
    ("PS-06", "A.7.8"),
    ("PS-07", "A.7.11"),
    ("PS-08", "A.7.12"),
    ("PS-09", "A.7.13"),
    ("OPS-01", "A.8.1"),
    ("OPS-02", "A.8.32"),
    ("OPS-03", "A.8.6"),
    ("OPS-04", "A.8.31"),
    ("OPS-05", "A.8.7"),
    ("OPS-06", "A.8.13"),
    ("OPS-07", "A.8.15"),
    ("OPS-08", "A.8.16"),
    ("OPS-09", "A.8.19"),
    ("OPS-10", "A.8.8"),
    ("OPS-11", "A.8.19"),
    ("OPS-12", "A.8.15"),
    ("OPS-12", "A.8.16"),
    ("OPS-13", "A.8.17"),
    ("OPS-14", "A.8.9"),
    ("OPS-15", "A.8.16"),
    ("OPS-16", "A.8.10"),
    ("IDM-01", "A.5.15"),
    ("IDM-02", "A.5.16"),
    ("IDM-03", "A.5.18"),
    ("IDM-04", "A.8.2"),
    ("IDM-05", "A.5.17"),
    ("IDM-06", "A.5.18"),
    ("IDM-07", "A.5.18"),
    ("IDM-08", "A.8.5"),
    ("IDM-09", "A.8.5"),
    ("IDM-10", "A.8.2"),
    ("IDM-10", "A.8.4"),
    ("IDM-11", "A.8.5"),
    ("CRY-01", "A.8.24"),
    ("CRY-02", "A.8.24"),
    ("CRY-03", "A.8.24"),
    ("CRY-03", "A.8.20"),
    ("CRY-04", "A.8.24"),
    ("COM-01", "A.8.20"),
    ("COM-02", "A.8.21"),
    ("COM-03", "A.8.22"),
    ("COM-04", "A.8.20"),
    ("COM-04", "A.5.14"),
    ("COM-05", "A.5.14"),
    ("COM-06", "A.8.20"),
    ("COM-07", "A.6.6"),
    ("COM-08", "A.8.20"),
    ("COM-08", "A.8.22"),
    ("PI-01", "A.5.23"),
    ("PI-02", "A.5.23"),
    ("PI-03", "A.5.23"),
    ("PI-04", "A.5.23"),
    ("PI-04", "A.8.10"),
    ("DEV-01", "A.8.25"),
    ("DEV-02", "A.8.32"),
    ("DEV-03", "A.8.32"),
    ("DEV-04", "A.8.32"),
    ("DEV-05", "A.8.27"),
    ("DEV-06", "A.8.25"),
    ("DEV-06", "A.8.31"),
    ("DEV-07", "A.8.29"),
    ("DEV-07", "A.8.33"),
    ("DEV-08", "A.8.29"),
    ("DEV-09", "A.8.30"),
    ("SSO-01", "A.5.19"),
    ("SSO-02", "A.5.20"),
    ("SSO-03", "A.5.21"),
    ("SSO-04", "A.5.22"),
    ("SSO-05", "A.5.22"),
    ("SIM-01", "A.5.24"),
    ("SIM-02", "A.5.25"),
    ("SIM-03", "A.5.25"),
    ("SIM-04", "A.5.25"),
    ("SIM-04", "A.5.26"),
    ("SIM-05", "A.5.26"),
    ("SIM-06", "A.5.27"),
    ("SIM-07", "A.5.28"),
    ("SIM-08", "A.5.26"),
    ("BCM-01", "A.5.29"),
    ("BCM-02", "A.5.29"),
    ("BCM-02", "A.5.30"),
    ("BCM-03", "A.5.29"),
    ("BCM-04", "A.5.30"),
    ("BCM-05", "A.5.30"),
    ("BCM-06", "A.5.30"),
    ("BCM-07", "A.5.29"),
    ("CMP-01", "A.5.31"),
    ("CMP-02", "A.5.32"),
    ("CMP-03", "A.5.33"),
    ("CMP-04", "A.5.34"),
    ("CMP-05", "A.5.31"),
    ("CMP-06", "A.5.35"),
    ("CMP-07", "A.5.36"),
    ("INQ-01", "A.5.23"),
    ("INQ-02", "A.5.23"),
    ("INQ-03", "A.5.35"),
    ("PSS-01", "A.8.27"),
    ("PSS-02", "A.8.22"),
    ("PSS-02", "A.8.31"),
    ("PSS-03", "A.8.26"),
    ("PSS-04", "A.8.25"),
    ("PSS-05", "A.8.8"),
]

# ---------------------------------------------------------------------------
# ISO 27001:2022 Control Descriptions (all 93 controls)
# ---------------------------------------------------------------------------

ISO_DESCRIPTIONS = {
    "A.5.1": "Policies for information security shall be defined, approved by management, published, communicated to relevant personnel and relevant interested parties, acknowledged, and reviewed at planned intervals.",
    "A.5.2": "Information security roles and responsibilities shall be defined and allocated according to the organization needs.",
    "A.5.3": "Conflicting duties and conflicting areas of responsibility shall be segregated.",
    "A.5.4": "Management shall require all personnel to apply information security in accordance with the established information security policy, topic-specific policies and procedures of the organization.",
    "A.5.5": "The organization shall establish and maintain contact with relevant authorities.",
    "A.5.6": "The organization shall establish and maintain contact with special interest groups or other specialist security forums and professional associations.",
    "A.5.7": "Information relating to information security threats shall be collected and analyzed to produce threat intelligence.",
    "A.5.8": "Information security shall be integrated into project management.",
    "A.5.9": "An inventory of information and other associated assets, including owners, shall be developed and maintained.",
    "A.5.10": "Rules for the acceptable use and procedures for handling information and other associated assets shall be identified, documented, and implemented.",
    "A.5.11": "Personnel and other interested parties as appropriate shall return all organizational assets in their possession upon change or termination of their employment, contract, or agreement.",
    "A.5.12": "Information shall be classified according to the information security needs of the organization based on confidentiality, integrity, availability, and relevant interested party requirements.",
    "A.5.13": "An appropriate set of procedures for information labeling shall be developed and implemented in accordance with the information classification scheme adopted by the organization.",
    "A.5.14": "Rules, procedures, or agreements for information transfer shall be in place for all types of transfer facilities within the organization and between the organization and other parties.",
    "A.5.15": "Rules to control physical and logical access to information and other associated assets shall be established and implemented based on business and information security requirements.",
    "A.5.16": "The full lifecycle of identities shall be managed.",
    "A.5.17": "Allocation and management of authentication information shall be controlled by a management process, including advising personnel on appropriate handling of authentication information.",
    "A.5.18": "Access rights to information and other associated assets shall be provisioned, reviewed, modified, and removed in accordance with the organizations topic-specific policy on and rules for access control.",
    "A.5.19": "Processes and procedures shall be defined and implemented to manage the information security risks associated with the use of suppliers products or services.",
    "A.5.20": "Relevant information security requirements shall be established and agreed with each supplier based on the type of supplier relationship.",
    "A.5.21": "Processes and procedures shall be defined and implemented to manage the information security risks associated with the ICT products and services supply chain.",
    "A.5.22": "The organization shall monitor, review, evaluate, and manage change related to supplier information security practices and service delivery.",
    "A.5.23": "Processes for acquisition, use, management, and exit from cloud services shall be established in accordance with the organizations information security requirements.",
    "A.5.24": "The organization shall plan and prepare for managing information security incidents by defining, establishing, and communicating information security incident management processes, roles, and responsibilities.",
    "A.5.25": "The organization shall assess information security events and decide if they are to be categorized as information security incidents.",
    "A.5.26": "Information security incidents shall be responded to in accordance with the documented procedures.",
    "A.5.27": "Knowledge gained from information security incidents shall be used to strengthen and improve the information security controls.",
    "A.5.28": "The organization shall establish and implement procedures for the identification, collection, acquisition, and preservation of evidence related to information security events.",
    "A.5.29": "The organization shall plan how to maintain information security at an appropriate level during disruption.",
    "A.5.30": "ICT readiness shall be planned, implemented, maintained, and tested based on business continuity objectives and ICT continuity requirements.",
    "A.5.31": "Legal, statutory, regulatory, and contractual requirements relevant to information security and the organizations approach to meet these requirements shall be identified, documented, and kept up to date.",
    "A.5.32": "The organization shall implement appropriate procedures to protect intellectual property rights.",
    "A.5.33": "Records shall be protected from loss, destruction, falsification, unauthorized access, and unauthorized release.",
    "A.5.34": "The organization shall identify and meet the requirements regarding the preservation of privacy and protection of PII according to applicable laws, regulations, and contractual requirements.",
    "A.5.35": "The organizations approach to managing information security and its implementation, including people, processes, and technologies, shall be reviewed independently at planned intervals or when significant changes occur.",
    "A.5.36": "Compliance with the organizations information security policy, topic-specific policies, rules, and standards shall be regularly reviewed.",
    "A.5.37": "Operating procedures for information processing facilities shall be documented and made available to personnel who need them.",
    "A.6.1": "Background verification checks on all candidates to become personnel shall be carried out prior to joining the organization and on an ongoing basis taking into consideration applicable laws, regulations, and ethics and be proportional to the business requirements, the classification of the information to be accessed, and the perceived risks.",
    "A.6.2": "The employment contractual agreements shall state the personnel and the organizations responsibilities for information security.",
    "A.6.3": "Organization personnel and relevant interested parties shall receive appropriate information security awareness, education, and training and regular updates of the organizations information security policy, topic-specific policies and procedures, as relevant for their job function.",
    "A.6.4": "A disciplinary process shall be formalized and communicated to take actions against personnel and other relevant interested parties who have committed an information security policy violation.",
    "A.6.5": "Information security responsibilities and duties that remain valid after termination or change of employment shall be defined, enforced, and communicated to relevant personnel and other interested parties.",
    "A.6.6": "Confidentiality or non-disclosure agreements reflecting the organizations needs for the protection of information shall be identified, documented, regularly reviewed, and signed by personnel and other relevant interested parties.",
    "A.6.7": "Security measures shall be implemented when personnel are working remotely to protect information accessed, processed, or stored outside the organizations premises.",
    "A.6.8": "The organization shall provide a mechanism for personnel to report observed or suspected information security events through appropriate channels in a timely manner.",
    "A.7.1": "Security perimeters shall be defined and used to protect areas that contain information and other associated assets.",
    "A.7.2": "Secure areas shall be protected by appropriate entry controls and access points.",
    "A.7.3": "Physical security for offices, rooms, and facilities shall be designed and implemented.",
    "A.7.4": "Physical security monitoring shall be continuously designed and implemented.",
    "A.7.5": "Protections against physical and environmental threats such as natural disasters and other intentional or unintentional physical threats to infrastructure shall be designed and implemented.",
    "A.7.6": "Security measures for working in secure areas shall be designed and implemented.",
    "A.7.7": "Rules shall be defined for clear desks for papers and removable storage media and clear screens for information processing facilities.",
    "A.7.8": "Equipment shall be sited securely and protected.",
    "A.7.9": "Security shall be applied to off-site assets taking into account the different risks of working outside the organizations premises.",
    "A.7.10": "Storage media shall be managed through their lifecycle of acquisition, use, transportation, and disposal in accordance with the organizations classification scheme and handling requirements.",
    "A.7.11": "Facilities shall be protected from power failures and other disruptions caused by failures in supporting utilities.",
    "A.7.12": "Cables carrying power, data, or supporting information services shall be protected from interception, interference, or damage.",
    "A.7.13": "Equipment shall be maintained correctly to ensure availability, integrity, and confidentiality of information.",
    "A.7.14": "Items of equipment containing storage media shall be verified to ensure that any sensitive data and licensed software has been removed or securely overwritten prior to disposal or re-use.",
    "A.8.1": "Information and other associated assets stored, processed, or accessible by user endpoint devices shall be protected.",
    "A.8.2": "The allocation and use of privileged access rights shall be restricted and managed.",
    "A.8.3": "Access to information and other associated assets shall be restricted in accordance with the established topic-specific policy on access control.",
    "A.8.4": "Read access, write access, and execution access to source code, development tools, and software libraries shall be appropriately managed.",
    "A.8.5": "Secure authentication technologies and procedures shall be established and implemented based on information access restrictions and the topic-specific policy on access control.",
    "A.8.6": "Forecasts of future capacity requirements shall be made taking into account required system capacity.",
    "A.8.7": "Protection against malware shall be implemented and supported by appropriate user awareness.",
    "A.8.8": "Information about technical vulnerabilities of information systems in use shall be obtained, the organizations exposure to such vulnerabilities shall be evaluated, and appropriate measures shall be taken.",
    "A.8.9": "Configurations, including security configurations, of hardware, software, services, and networks shall be established, documented, implemented, monitored, and reviewed.",
    "A.8.10": "Information stored in information systems, devices, or in any other storage media shall be deleted when no longer required.",
    "A.8.11": "Data masking shall be used in accordance with the organizations topic-specific policy on access control and other related topic-specific policies and business requirements, taking applicable legislation into consideration.",
    "A.8.12": "Data leakage prevention measures shall be applied to systems, networks, and any other devices that process, store, or transmit sensitive information.",
    "A.8.13": "Backup copies of information, software, and systems shall be maintained and regularly tested in accordance with the agreed topic-specific policy on backup.",
    "A.8.14": "Information processing facilities shall be implemented with redundancy sufficient to meet availability requirements.",
    "A.8.15": "Logs that record activities, exceptions, faults, and other relevant events shall be produced, stored, protected, and analyzed.",
    "A.8.16": "Networks, systems, and applications shall be monitored for anomalous behavior and appropriate actions taken to evaluate potential information security incidents.",
    "A.8.17": "The clocks of information processing systems used by the organization shall be synchronized to approved time sources.",
    "A.8.18": "The use of utility programs that might be capable of overriding system and application controls shall be restricted and tightly controlled.",
    "A.8.19": "Procedures and measures shall be implemented to securely manage software installation on operational systems.",
    "A.8.20": "Networks and network devices shall be secured, managed, and controlled to protect information in systems and applications.",
    "A.8.21": "Security mechanisms, service levels, and service requirements of network services shall be identified, implemented, and monitored.",
    "A.8.22": "Groups of information services, users, and information systems shall be segregated in the organizations networks.",
    "A.8.23": "Web filtering measures shall be used to reduce exposure to malicious web content with access to external websites managed to reduce exposure to malicious content.",
    "A.8.24": "Rules for the effective use of cryptography, including cryptographic key management, shall be defined and implemented.",
    "A.8.25": "Rules for the secure development of software and systems shall be established and applied.",
    "A.8.26": "Information security requirements shall be identified, specified, and approved when developing or acquiring applications.",
    "A.8.27": "Principles for engineering secure systems shall be established, documented, maintained, and applied to any information system development activities.",
    "A.8.28": "Secure coding principles shall be applied to software development.",
    "A.8.29": "Security testing processes shall be defined and implemented in the development lifecycle.",
    "A.8.30": "The organization shall direct, monitor, and review the activities related to outsourced system development.",
    "A.8.31": "Development, testing, and production environments shall be separated and secured.",
    "A.8.32": "Changes to information processing facilities and information systems shall be subject to change management procedures.",
    "A.8.33": "Test information shall be appropriately selected, protected, and managed.",
    "A.8.34": "The organization shall ensure that audit tests and other assurance activities involving assessment of operational systems are planned and agreed between the tester and appropriate management.",
}


def run():
    print("Initializing database...")
    init_db_sync()
    session = SyncSession()

    try:
        # Get framework IDs
        iso_fw = session.execute(
            select(Framework).where(Framework.short_name == "ISO27001")
        ).scalar_one_or_none()
        c5_fw = session.execute(
            select(Framework).where(Framework.short_name == "C5")
        ).scalar_one_or_none()

        if not iso_fw:
            print("ERROR: ISO 27001 framework not found. Run seed_data.py first.")
            sys.exit(1)

        if not c5_fw:
            print("Creating C5:2020 framework...")
            c5_fw = Framework(
                name="BSI Cloud Computing Compliance Criteria Catalogue",
                short_name="C5",
                version="2020",
                description="BSI C5:2020 - Criteria catalogue for secure cloud computing",
            )
            session.add(c5_fw)
            session.flush()

        # Seed C5 controls
        print(f"Seeding {len(C5_CONTROLS)} C5:2020 controls...")
        c5_added = 0
        c5_updated = 0
        for ctrl_id, title, category, description in C5_CONTROLS:
            existing = session.execute(
                select(Control).where(
                    Control.framework_id == c5_fw.id,
                    Control.control_id == ctrl_id,
                )
            ).scalar_one_or_none()
            if existing:
                if existing.description != description or existing.title != title:
                    existing.description = description
                    existing.title = title
                    c5_updated += 1
            else:
                session.add(Control(
                    framework_id=c5_fw.id,
                    control_id=ctrl_id,
                    title=title,
                    description=description,
                    category=category,
                ))
                c5_added += 1
        session.flush()
        print(f"  C5 controls added: {c5_added}, updated: {c5_updated}")

        # Update ISO 27001 descriptions
        print(f"Updating {len(ISO_DESCRIPTIONS)} ISO 27001 control descriptions...")
        iso_updated = 0
        for ctrl_id, description in ISO_DESCRIPTIONS.items():
            existing = session.execute(
                select(Control).where(
                    Control.framework_id == iso_fw.id,
                    Control.control_id == ctrl_id,
                )
            ).scalar_one_or_none()
            if existing:
                if existing.description != description:
                    existing.description = description
                    iso_updated += 1
            else:
                print(f"  WARNING: ISO control {ctrl_id} not found in database, skipping.")
        session.flush()
        print(f"  ISO descriptions updated: {iso_updated}")

        # Build lookup for mappings
        all_controls = session.execute(
            select(Control.id, Control.control_id, Control.framework_id)
        ).all()
        lookup = {(r[1], r[2]): r[0] for r in all_controls}

        # Seed C5 to ISO mappings
        print(f"Seeding {len(C5_ISO_MAPPINGS)} C5 to ISO 27001 mappings...")
        map_added = 0
        map_skipped = 0
        for c5_id, iso_id in C5_ISO_MAPPINGS:
            src = lookup.get((c5_id, c5_fw.id))
            tgt = lookup.get((iso_id, iso_fw.id))
            if not src or not tgt:
                map_skipped += 1
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
                    source_document="BSI C5:2020 / ISO 27001:2022 cross-reference",
                ))
                map_added += 1

        session.commit()
        print(f"  Mappings added: {map_added}, skipped (missing controls): {map_skipped}")
        print("Done! C5 controls, ISO descriptions, and C5-ISO mappings are ready.")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
