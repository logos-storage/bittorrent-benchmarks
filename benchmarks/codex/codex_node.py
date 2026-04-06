import logging
import socket
from functools import cached_property
from typing import Iterator, Set
from urllib.error import HTTPError

import requests
from attr import dataclass
from requests.exceptions import ConnectionError
from tenacity import (
    stop_after_attempt,
    wait_exponential,
    retry,
    retry_if_not_exception_type,
)
from urllib3.util import Url

from benchmarks.codex.agent.agent import Cid, DownloadStatus
from benchmarks.codex.agent.codex_agent_client import CodexAgentClient
from benchmarks.core.concurrency import await_predicate
from benchmarks.core.experiments.experiments import ExperimentComponent
from benchmarks.core.network import Node, DownloadHandle
from benchmarks.core.utils.units import megabytes

STOP_POLICY = stop_after_attempt(5)
WAIT_POLICY = wait_exponential(exp_base=2, min=4, max=16)
DELETE_TIMEOUT = 3600  # timeouts for deletes should be generous (https://github.com/codex-storage/nim-codex/pull/1103)

logger = logging.getLogger(__name__)


@dataclass
class CodexMeta:
    name: str


class CodexNode(Node[Cid, CodexMeta], ExperimentComponent):
    def __init__(
        self, codex_api_url: Url, agent: CodexAgentClient, remove_data: bool = True
    ) -> None:
        self.codex_api_url = codex_api_url
        self.agent = agent
        # Lightweight tracking of datasets created by this node. It's OK if we lose them.
        self.hosted_datasets: Set[Cid] = set()
        self.remove_data = remove_data

    def is_ready(self) -> bool:
        try:
            requests.get(
                str(self.codex_api_url._replace(path="/api/storage/v1/debug/info"))
            )
            return True
        except (ConnectionError, socket.gaierror):
            return False

    @retry(
        stop=STOP_POLICY,
        wait=WAIT_POLICY,
        retry=retry_if_not_exception_type(HTTPError),
    )
    def genseed(self, size: int, seed: int, meta: CodexMeta) -> Cid:
        cid = self.agent.generate(size=size, seed=seed, name=meta.name)
        self.hosted_datasets.add(cid)
        return cid

    @retry(
        stop=STOP_POLICY,
        wait=WAIT_POLICY,
        retry=retry_if_not_exception_type(HTTPError),
    )
    def leech(self, handle: Cid) -> DownloadHandle:
        self.hosted_datasets.add(handle)
        return CodexDownloadHandle(parent=self, monitor_url=self.agent.download(handle))

    def remove(self, handle: Cid) -> bool:
        if self.remove_data:
            response = requests.delete(
                str(self.codex_api_url._replace(path=f"/api/storage/v1/data/{handle}")),
                timeout=DELETE_TIMEOUT,
            )

            response.raise_for_status()

        return True

    def exists_local(self, handle: Cid) -> bool:
        """Check if a dataset exists on the node."""
        response = requests.get(
            str(self.codex_api_url._replace(path=f"/api/storage/v1/data/{handle}"))
        )

        response.close()

        if response.status_code == 404:
            return False

        if response.status_code != 200:
            response.raise_for_status()

        return True

    def download_local(
        self, handle: Cid, chunk_size: int = megabytes(1)
    ) -> Iterator[bytes]:
        """Retrieves the contents of a locally available
        dataset from the node."""
        response = requests.get(
            str(self.codex_api_url._replace(path=f"/api/storage/v1/data/{handle}"))
        )

        response.raise_for_status()

        return response.iter_content(chunk_size=chunk_size)

    def blocks_sent(self, metrics_port: int = 8008) -> int:
        """Query the Prometheus metrics endpoint for blocks sent count."""
        try:
            metrics_url = self.codex_api_url._replace(port=metrics_port, path="/metrics")
            response = requests.get(str(metrics_url), timeout=5)
            response.raise_for_status()
            for line in response.text.splitlines():
                if line.startswith("storage_block_exchange_blocks_sent_total"):
                    return int(float(line.split()[1]))
        except Exception:
            pass
        return 0

    def wipe_all_datasets(self):
        for dataset in list(self.hosted_datasets):
            self.remove(dataset)
            self.hosted_datasets.remove(dataset)

    @cached_property
    def name(self) -> str:
        return self.agent.node_id()

    def __str__(self):
        return f"CodexNode({self.codex_api_url.url, self.agent})"


class CodexDownloadHandle(DownloadHandle):
    def __init__(self, parent: CodexNode, monitor_url: Url):
        self.monitor_url = monitor_url
        self.parent = parent

    def await_for_completion(self, timeout: float = 0) -> bool:
        def _predicate():
            completion = self.completion()
            return completion.downloaded == completion.total

        return await_predicate(_predicate, timeout, polling_interval=1)

    @property
    def node(self) -> Node:
        return self.parent

    def completion(self) -> DownloadStatus:
        response = requests.get(str(self.monitor_url))
        response.raise_for_status()

        return DownloadStatus.model_validate(response.json())
