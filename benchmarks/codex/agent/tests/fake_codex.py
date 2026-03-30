import json
import re
from asyncio import StreamReader
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Dict, Optional, AsyncIterator, Tuple, IO

from aiohttp import web, ClientTimeout
from urllib3.util import Url

from benchmarks.codex.client.async_client import AsyncCodexClient, Cid
from benchmarks.codex.client.common import Manifest
from benchmarks.core.utils.streams import BaseStreamReader


class FakeCodex(AsyncCodexClient):
    def __init__(self) -> None:
        self.storage: Dict[Cid, Manifest] = {}
        self.streams: Dict[Cid, StreamReader] = {}

    async def upload(
        self,
        name: str,
        mime_type: str,
        content: IO,
        timeout: Optional[ClientTimeout] = None,
    ) -> Cid:
        data = content.read()
        cid = "Qm" + str(hash(data))
        self.storage[cid] = Manifest(
            cid=cid,
            datasetSize=len(data),
            mimetype=mime_type,
            blockSize=1,
            filename=name,
            treeCid="",
        )
        return cid

    async def manifest(self, cid: Cid) -> Manifest:
        return self.storage[cid]

    def create_download_stream(self, cid: Cid) -> StreamReader:
        reader = StreamReader()
        self.streams[cid] = reader
        return reader

    @asynccontextmanager
    async def download(
        self, cid: Cid, timeout: Optional[ClientTimeout] = None
    ) -> AsyncIterator[BaseStreamReader]:
        yield self.streams[cid]


@asynccontextmanager
async def fake_codex_api() -> AsyncIterator[Tuple[FakeCodex, Url]]:
    codex = FakeCodex()
    routes = web.RouteTableDef()

    @routes.get("/api/storage/v1/data/{cid}/network/manifest")
    async def manifest(request):
        cid = request.match_info["cid"]
        assert cid in codex.storage
        # Gets the manifest in a similar shape as the Codex response.
        manifest = json.loads(codex.storage[cid].model_dump_json())
        return web.json_response(
            data={
                "cid": manifest.pop("cid"),
                "manifest": manifest,
            }
        )

    @routes.post("/api/storage/v1/data")
    async def upload(request):
        await request.post()
        filename = re.findall(
            r'filename="(.+)"', request.headers["Content-Disposition"]
        )[0]
        cid = await codex.upload(
            name=filename,
            mime_type=request.headers["Content-Type"],
            content=BytesIO(await request.read()),
        )
        return web.Response(text=cid)

    @routes.get("/api/storage/v1/data/{cid}")
    async def download(request):
        cid = request.match_info["cid"]
        assert cid in codex.streams
        reader = codex.streams[cid]

        # We basically copy the stream onto the response.
        response = web.StreamResponse()
        await response.prepare(request)
        while not reader.at_eof():
            await response.write(await reader.read(1024))

        await response.write_eof()
        return response

    app = web.Application()
    app.add_routes(routes)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "localhost", 8888)
    await site.start()

    try:
        yield codex, Url(scheme="http", host="localhost", port=8888)
    finally:
        await site.stop()
        await runner.cleanup()
