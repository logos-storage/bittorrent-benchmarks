import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient

from benchmarks.codex.agent import api
from benchmarks.codex.agent.agent import CodexAgent
from benchmarks.codex.agent.tests.fake_codex import FakeCodex


@pytest.mark.asyncio
async def test_should_create_file():
    codex_client = FakeCodex()
    codex_agent = CodexAgent(codex_client)

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.codex_agent] = lambda: codex_agent

    client = TestClient(app)

    response = client.post(
        "/api/v1/codex/dataset",
        params={"name": "dataset-1", "size": 1024, "seed": 12},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.charset_encoding == "utf-8"

    manifest = await codex_client.manifest(response.text)

    assert manifest.datasetSize == 1024


@pytest.mark.asyncio
async def test_should_report_when_download_is_complete():
    codex_client = FakeCodex()
    codex_agent = CodexAgent(codex_client)

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.codex_agent] = lambda: codex_agent

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/codex/dataset",
            params={"name": "dataset-1", "size": 1024, "seed": 12},
        )

        assert response.status_code == 200
        assert response.charset_encoding == "utf-8"

        cid = response.text

        download_stream = codex_client.create_download_stream(cid)

        response = await client.post(
            "/api/v1/codex/download",
            params={"cid": cid},
        )

        assert response.status_code == 202
        assert response.json() == {
            "status": f"http://testserver/api/v1/codex/download/{cid}/status"
        }

        download_stream.feed_data(b"0" * 1024)
        download_stream.feed_eof()

        await codex_agent.ongoing_downloads[cid].download_task

        response = await client.get(f"api/v1/codex/download/{cid}/status")

        assert response.status_code == 200
        assert response.json() == {"downloaded": 1024, "total": 1024}
