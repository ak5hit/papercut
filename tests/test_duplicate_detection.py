from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from storage.document_store import DocumentStore


def _mock_async_session() -> AsyncMock:
    """Return an AsyncMock whose execute().scalar_one_or_none() returns None by default."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock
    return session


@pytest.fixture
def store() -> DocumentStore:
    return DocumentStore(_mock_async_session())


@pytest.mark.asyncio
async def test_find_duplicate_returns_match_by_content_hash(store: DocumentStore) -> None:
    """querying with a known content_hash returns the matching document."""
    from models.canonical_document import CanonicalDocument

    doc = CanonicalDocument.create(
        raw_text="test",
        metadata={"filename": "test.pdf"},
        extraction_strategy="generic_small",
        content_hash="abc123",
    )

    mock_model = MagicMock()
    mock_model.to_canonical.return_value = doc
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_model
    store.session.execute.return_value = result_mock

    found = await store.find_duplicate("abc123")
    assert found is not None
    assert found.metadata["filename"] == "test.pdf"
    assert found.content_hash == "abc123"


@pytest.mark.asyncio
async def test_find_duplicate_no_match_different_hash(store: DocumentStore) -> None:
    """querying with an unknown content_hash returns None."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    store.session.execute.return_value = result_mock

    found = await store.find_duplicate("nonexistent")
    assert found is None


@pytest.mark.asyncio
async def test_find_duplicate_ignores_null_hash(store: DocumentStore) -> None:
    """old documents with content_hash=NULL do not match a content_hash query."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    store.session.execute.return_value = result_mock

    found = await store.find_duplicate("anyhash")
    assert found is None


@pytest.mark.asyncio
async def test_save_document_roundtrips_content_hash(store: DocumentStore) -> None:
    """content_hash flows through save → retrieve round-trip."""
    from models.canonical_document import CanonicalDocument

    doc = CanonicalDocument.create(
        raw_text="test content",
        metadata={"filename": "test.pdf"},
        extraction_strategy="generic_small",
        content_hash="sha256test123",
    )

    await store.save_document(doc)

    call_args = store.session.add.call_args
    assert call_args is not None
    saved = call_args[0][0]
    assert saved.content_hash == "sha256test123"


# ─── /check-duplicate endpoint ───────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    from api.routes.documents import router
    from storage.database import get_session

    a = FastAPI()
    a.include_router(router)

    # Override get_session to return a MagicMock (awaitable = mock itself)
    mock_session = MagicMock()

    async def mock_get_session() -> Any:
        return mock_session

    a.dependency_overrides[get_session] = mock_get_session
    return a


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    c = TestClient(app)
    # Simulate the app being ready (_require_ready checks this)
    def get_state():
        return {"ready": True}
    return c


def test_check_duplicate_returns_false_when_no_match(client: TestClient) -> None:
    """GET /documents/check-duplicate with unknown hash returns is_duplicate: false."""
    with patch("api.routes.documents.DocumentStore") as MockStore:
        instance = MockStore.return_value
        instance.find_duplicate = AsyncMock(return_value=None)

        resp = client.get("/documents/check-duplicate?content_hash=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate"] is False


def test_check_duplicate_returns_true_when_match(client: TestClient) -> None:
    """GET /documents/check-duplicate with known hash returns is_duplicate: true + details."""
    from models.canonical_document import CanonicalDocument

    existing = CanonicalDocument.create(
        raw_text="test",
        metadata={"filename": "existing.pdf"},
        extraction_strategy="generic_small",
    )

    with patch("api.routes.documents.DocumentStore") as MockStore:
        instance = MockStore.return_value
        instance.find_duplicate = AsyncMock(return_value=existing)

        resp = client.get("/documents/check-duplicate?content_hash=matchinghash")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate"] is True
        assert data["existing_filename"] == "existing.pdf"


def test_upload_returns_duplicate_event_when_match(client: TestClient, app: FastAPI) -> None:
    """POST /documents/upload with duplicate content_hash returns SSE error code: DUPLICATE."""
    from storage.database import get_session

    existing_doc = MagicMock()
    existing_doc.metadata = {"filename": "existing.pdf"}
    existing_doc.id = uuid4()

    # Override get_session to return a working session for the pre-flight check
    mock_session = MagicMock()

    async def mock_get_session() -> Any:
        return mock_session

    app.dependency_overrides[get_session] = mock_get_session

    with patch("api.routes.documents.DocumentStore") as MockStore:
        instance = MockStore.return_value
        instance.find_duplicate = AsyncMock(return_value=existing_doc)

        resp = client.post(
            "/documents/upload",
            files={"file": ("test.pdf", b"hello world", "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "DUPLICATE" in body
        assert "already uploaded" in body.lower()


def test_upload_proceeds_when_not_duplicate(client: TestClient, app: FastAPI) -> None:
    """POST /documents/upload with new content_hash starts extraction (phase events or error)."""
    from storage.database import get_session

    mock_session = MagicMock()

    async def mock_get_session() -> Any:
        return mock_session

    app.dependency_overrides[get_session] = mock_get_session

    with patch("api.routes.documents.DocumentStore") as MockStore:
        instance = MockStore.return_value
        instance.find_duplicate = AsyncMock(return_value=None)

        resp = client.post(
            "/documents/upload",
            files={"file": ("test.pdf", b"unique content", "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "DUPLICATE" not in body
