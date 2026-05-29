"""Tests for compliance API endpoints (Phase 5).

Tests the new FastAPI endpoints for regulation management,
tuple extraction, compliance checking, and eventic graph operations.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

import database
from database import Base


@pytest_asyncio.fixture
async def client():
    """Create test client with in-memory SQLite database."""
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


@pytest.mark.asyncio
async def test_upload_regulation(client):
    response = await client.post(
        "/api/regulations/upload",
        json={
            "name": "General Data Protection Regulation",
            "short_name": "GDPR",
            "version": "2016/679",
            "jurisdiction": "EU",
            "full_text": "Personal data means any information relating to an identified natural person.",
            "language": "en",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["short_name"] == "GDPR"


@pytest.mark.asyncio
async def test_list_regulations(client):
    # Upload one first
    await client.post(
        "/api/regulations/upload",
        json={
            "name": "GDPR",
            "short_name": "GDPR",
            "full_text": "Test regulation text.",
        },
    )
    response = await client.get("/api/regulations")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_extract_tuples(client):
    # Upload regulation
    reg_resp = await client.post(
        "/api/regulations/upload",
        json={
            "name": "GDPR",
            "short_name": "GDPR",
            "full_text": "A business shall inform consumers about the categories of personal information.",
        },
    )
    reg_id = reg_resp.json()["id"]

    # Extract tuples
    response = await client.post(f"/api/regulations/{reg_id}/extract-tuples")
    assert response.status_code == 200
    data = response.json()
    assert "tuples" in data
    assert isinstance(data["tuples"], list)
    assert len(data["tuples"]) >= 1


@pytest.mark.asyncio
async def test_get_tuples(client):
    # Upload and extract
    reg_resp = await client.post(
        "/api/regulations/upload",
        json={
            "name": "GDPR",
            "short_name": "GDPR",
            "full_text": "Personal data means any information relating to an identified natural person.",
        },
    )
    reg_id = reg_resp.json()["id"]
    await client.post(f"/api/regulations/{reg_id}/extract-tuples")

    # Get tuples
    response = await client.get(f"/api/regulations/{reg_id}/tuples")
    assert response.status_code == 200
    data = response.json()
    assert "tuples" in data
    assert isinstance(data["tuples"], list)


@pytest.mark.asyncio
async def test_compliance_check(client):
    # Upload regulation
    reg_resp = await client.post(
        "/api/regulations/upload",
        json={
            "name": "GDPR",
            "short_name": "GDPR",
            "full_text": "User data must not be shared with third parties without explicit consent.",
        },
    )
    reg_id = reg_resp.json()["id"]

    # Run compliance check
    response = await client.post(
        "/api/compliance/check",
        json={
            "regulation_id": reg_id,
            "business_text": "We share your location information with partners to help us provide services.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    for r in data["results"]:
        assert "chunk" in r
        assert "result" in r
        assert r["result"] in ("compliant", "non_compliant", "undetermined")


@pytest.mark.asyncio
async def test_build_eventic_graph(client):
    reg_resp = await client.post(
        "/api/regulations/upload",
        json={
            "name": "GDPR",
            "short_name": "GDPR",
            "full_text": "The controller shall implement appropriate technical measures.",
        },
    )
    reg_id = reg_resp.json()["id"]

    response = await client.post(f"/api/eventic-graph/build", json={"regulation_id": reg_id})
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


@pytest.mark.asyncio
async def test_regulation_compare(client):
    # Upload two regulations
    r1 = await client.post(
        "/api/regulations/upload",
        json={"name": "GDPR", "short_name": "GDPR", "full_text": "Personal data must be processed lawfully."},
    )
    r2 = await client.post(
        "/api/regulations/upload",
        json={"name": "CCPA", "short_name": "CCPA", "full_text": "A business shall inform consumers about personal information collected."},
    )

    response = await client.get(
        "/api/regulations/compare",
        params={"reg_id_1": r1.json()["id"], "reg_id_2": r2.json()["id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "similarity_score" in data


@pytest.mark.asyncio
async def test_regulation_not_found(client):
    response = await client.post("/api/regulations/9999/extract-tuples")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_compliance_check_missing_fields(client):
    response = await client.post("/api/compliance/check", json={})
    assert response.status_code == 422
