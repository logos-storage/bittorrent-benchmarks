from pydantic import BaseModel

API_VERSION = "v1"

Cid = str


class Manifest(BaseModel):
    cid: Cid
    treeCid: Cid
    datasetSize: int
    blockSize: int
    filename: str
    mimetype: str

    @staticmethod
    def from_codex_api_response(response: dict) -> "Manifest":
        return Manifest.model_validate(
            dict(cid=response["cid"], **response["manifest"])
        )
