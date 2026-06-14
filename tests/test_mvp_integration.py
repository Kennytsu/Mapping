"""Integration test: Full MVP flow from upload to mappings visible in Coverage.

Tests the complete pipeline:
1. Upload Regulation A → Framework + Controls created
2. Upload Regulation B → Framework + Controls created
3. Generate Mappings → Persisted in mappings table
4. Coverage API shows the mappings
5. Control Lookup shows the controls
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from database import Base


@pytest_asyncio.fixture
async def client():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    from app import app
    from database import get_session
    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    await test_engine.dispose()


GDPR_TEXT = """The controller shall implement appropriate technical and organizational measures to ensure a level of security appropriate to the risk.
The data subject shall have the right to obtain from the controller confirmation as to whether or not personal data are being processed.
Personal data must not be shared with third parties without the explicit consent of the data subject.
'Personal data' means any information relating to an identified or identifiable natural person."""

ISO_TEXT = """The organization shall implement information security controls appropriate to the risk assessment.
Access to information and information processing facilities shall be restricted to authorized personnel.
Information classified as confidential shall not be disclosed to external parties without authorization.
'Information asset' means any data or system of value to the organization."""


@pytest.mark.asyncio
async def test_full_mvp_flow(client):
    """Complete flow: upload → extract → generate mappings → visible in coverage."""

    # Step 1: Upload GDPR
    resp = await client.post("/api/regulations/upload", json={
        "name": "General Data Protection Regulation",
        "short_name": "GDPR",
        "version": "2016/679",
        "jurisdiction": "EU",
        "full_text": GDPR_TEXT,
    })
    assert resp.status_code == 200
    gdpr = resp.json()
    assert gdpr["short_name"] == "GDPR"

    # Step 2: Upload ISO 27001
    resp = await client.post("/api/regulations/upload", json={
        "name": "ISO/IEC 27001",
        "short_name": "ISO27001",
        "version": "2022",
        "jurisdiction": "International",
        "full_text": ISO_TEXT,
    })
    assert resp.status_code == 200
    iso = resp.json()
    assert iso["short_name"] == "ISO27001"

    # Step 3: Verify frameworks were created
    resp = await client.get("/api/frameworks")
    assert resp.status_code == 200
    frameworks = resp.json()
    fw_names = [f["short_name"] for f in frameworks]
    assert "GDPR" in fw_names
    assert "ISO27001" in fw_names

    # Step 4: Verify controls were created
    resp = await client.get("/api/controls", params={"q": "GDPR"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3  # at least 3 GDPR statements become controls

    resp = await client.get("/api/controls", params={"q": "ISO27001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3

    # Step 5: Generate mappings between GDPR and ISO
    gdpr_fw_id = next(f["id"] for f in frameworks if f["short_name"] == "GDPR")
    iso_fw_id = next(f["id"] for f in frameworks if f["short_name"] == "ISO27001")

    resp = await client.post("/api/regulations/generate-mappings", json={
        "source_regulation_id": gdpr["id"],
        "target_regulation_id": iso["id"],
        "threshold": 0.3,
    })
    assert resp.status_code == 200
    mapping_data = resp.json()
    assert mapping_data["mappings_found"] >= 1
    assert mapping_data["mappings_persisted"] >= 1

    # Step 6: Verify mappings appear in Coverage API
    resp = await client.get("/api/coverage", params={
        "source": gdpr_fw_id,
        "target": iso_fw_id,
    })
    assert resp.status_code == 200
    coverage = resp.json()
    assert coverage["mapped_controls"] >= 1
    assert coverage["coverage_percentage"] > 0

    # Step 7: Verify individual control shows mappings
    ctrl_resp = await client.get("/api/controls", params={"framework_id": gdpr_fw_id, "limit": 1})
    ctrl_data = ctrl_resp.json()
    if ctrl_data["items"]:
        ctrl_id = ctrl_data["items"][0]["control_id"]
        resp = await client.get(f"/api/mappings/{ctrl_id}", params={"framework_id": gdpr_fw_id})
        # Should either have mappings or return 200 with empty list
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_upload_creates_framework_and_controls(client):
    """Uploading a regulation creates a Framework with Controls."""
    resp = await client.post("/api/regulations/upload", json={
        "name": "Test Regulation",
        "short_name": "TEST",
        "full_text": "Organizations must encrypt sensitive data. Users shall have access to their records.",
    })
    assert resp.status_code == 200

    # Check framework exists
    resp = await client.get("/api/frameworks")
    frameworks = resp.json()
    assert any(f["short_name"] == "TEST" for f in frameworks)

    # Check controls exist
    test_fw = next(f for f in frameworks if f["short_name"] == "TEST")
    assert test_fw["control_count"] >= 2


@pytest.mark.asyncio
async def test_generated_mappings_have_ai_suggested_type(client):
    """Generated mappings are stored with source_type=ai_suggested."""
    await client.post("/api/regulations/upload", json={
        "name": "Reg A", "short_name": "REGA",
        "full_text": "The controller shall protect personal data with appropriate measures.",
    })
    await client.post("/api/regulations/upload", json={
        "name": "Reg B", "short_name": "REGB",
        "full_text": "The organization must safeguard information with adequate controls.",
    })

    regs = (await client.get("/api/regulations")).json()
    reg_a = next(r for r in regs if r["short_name"] == "REGA")
    reg_b = next(r for r in regs if r["short_name"] == "REGB")

    resp = await client.post("/api/regulations/generate-mappings", json={
        "source_regulation_id": reg_a["id"],
        "target_regulation_id": reg_b["id"],
        "threshold": 0.3,
    })
    data = resp.json()

    for m in data["mappings"]:
        assert m["source_type"] == "ai_suggested"
        assert m["confidence"] >= 0.3
        assert m["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_duplicate_upload_reuses_framework(client):
    """Uploading same regulation twice doesn't create duplicate framework."""
    await client.post("/api/regulations/upload", json={
        "name": "GDPR", "short_name": "GDPR", "full_text": "Data must be protected.",
    })
    await client.post("/api/regulations/upload", json={
        "name": "GDPR v2", "short_name": "GDPR", "full_text": "Data must be protected. Users have rights.",
    })

    resp = await client.get("/api/frameworks")
    frameworks = resp.json()
    gdpr_fws = [f for f in frameworks if f["short_name"] == "GDPR"]
    assert len(gdpr_fws) == 1  # Only one framework, not two
