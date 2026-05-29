"""Shared test fixtures for compliance checking tests."""

import pytest

# Sample GDPR regulation text for testing
GDPR_ARTICLE_6 = """
The processing of personal data requires lawful basis.
A user's explicit consent is the only lawful basis for sharing the user's data.
User data must not be shared with third parties unless explicit permission from the user is obtained.
Appropriate technical and organizational measures must be used to protect personal data from unauthorized or unlawful processing and against accidental loss, destruction, or damage.
"""

GDPR_DEFINITIONS = """
'Personal data' means any information relating to an identified or identifiable natural person.
'Processing' means any operation or set of operations which is performed on personal data.
'Controller' means the natural or legal person, public authority, agency or other body which, alone or jointly with others, determines the purposes and means of the processing of personal data.
'Consent' of the data subject means any freely given, specific, informed and unambiguous indication of the data subject's wishes.
"""

GDPR_RIGHTS = """
The data subject shall have the right to withdraw his or her consent at any time.
The data subject shall have the right to obtain from the controller confirmation as to whether or not personal data concerning him or her are being processed.
Every data subject shall have the right to lodge a complaint with a supervisory authority.
"""

SAMPLE_BUSINESS_PROCESS = """
We only collect basic health data that you provide (for example: steps, heart rate) and necessary registration information (for example: name, email address).
We may share your location information with partners to help us provide services, which you have agreed to during registration.
We use industry-standard security measures to protect your data from unauthorized access, disclosure, or tampering.
"""

CCPA_STATEMENT = (
    "A business that collects a consumer's personal information shall, "
    "at or before the point of collection, inform consumers as to the "
    "categories of personal information to be collected and the purposes "
    "for which the categories of personal information shall be used."
)


@pytest.fixture
def gdpr_text():
    return GDPR_ARTICLE_6


@pytest.fixture
def gdpr_definitions():
    return GDPR_DEFINITIONS


@pytest.fixture
def gdpr_rights():
    return GDPR_RIGHTS


@pytest.fixture
def sample_business_process():
    return SAMPLE_BUSINESS_PROCESS


@pytest.fixture
def ccpa_statement():
    return CCPA_STATEMENT
