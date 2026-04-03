import random
from itertools import islice
from typing import List, cast

from pydantic import Field, model_validator
from pydantic_core import Url
from urllib3.util import parse_url

from benchmarks.codex.agent.codex_agent_client import CodexAgentClient
from benchmarks.codex.client.common import Cid
from benchmarks.codex.codex_node import CodexMeta, CodexNode
from benchmarks.core.experiments.dissemination_experiment.config import (
    DisseminationExperimentConfig,
)
from benchmarks.core.experiments.dissemination_experiment.static import (
    StaticDisseminationExperiment,
)
from benchmarks.core.experiments.experiments import (
    ExperimentBuilder,
    ExperimentEnvironment,
    ExperimentComponent,
)
from benchmarks.core.experiments.iterated_experiment import IteratedExperiment
from benchmarks.core.pydantic import SnakeCaseModel, Host
from benchmarks.core.utils.random import sample


class CodexNodeConfig(SnakeCaseModel):
    name: str
    address: Host
    disc_port: int
    api_port: int
    agent_url: Url


class CodexNodeSetConfig(SnakeCaseModel):
    network_size: int = Field(gt=1)
    name: str
    address: str
    disc_port: int
    api_port: int
    first_node_index: int = 1
    nodes: List[CodexNodeConfig] = []
    agent_url: str

    @model_validator(mode="after")
    def expand_nodes(self):
        self.nodes = [
            CodexNodeConfig(
                name=self.name.format(node_index=str(i)),
                address=self.address.format(node_index=str(i)),
                disc_port=self.disc_port,
                api_port=self.api_port,
                agent_url=self.agent_url.format(node_index=str(i)),
            )
            for i in range(
                self.first_node_index, self.first_node_index + self.network_size
            )
        ]
        return self


CodexDisseminationExperiment = IteratedExperiment[
    StaticDisseminationExperiment[Cid, CodexMeta]
]


class CodexExperimentConfig(
    ExperimentBuilder[CodexDisseminationExperiment],
    DisseminationExperimentConfig[CodexNodeConfig, CodexNodeSetConfig],
):
    repetitions: int = Field(
        gt=0, description="How many experiment repetitions to run for each seeder set"
    )

    download_metric_unit_bytes: int = 1
    remove_data: bool = False

    def build(self) -> CodexDisseminationExperiment:
        node_specs = (
            self.nodes.nodes
            if isinstance(self.nodes, CodexNodeSetConfig)
            else self.nodes
        )

        agents = [
            CodexAgentClient(parse_url(str(node.agent_url))) for node in node_specs
        ]

        network = [
            CodexNode(
                codex_api_url=parse_url(f"http://{str(node.address)}:{node.api_port}"),
                agent=agents[i],
                remove_data=self.remove_data,
            )
            for i, node in enumerate(node_specs)
        ]

        env = ExperimentEnvironment(
            components=cast(List[ExperimentComponent], network + agents),
            ping_max=10,
            polling_interval=0.5,
        )

        def repetitions():
            for seeder_set in range(self.seeder_sets):
                seeders = list(islice(sample(len(network)), self.seeders))
                for experiment_run in range(self.repetitions):
                    yield env.bind(
                        StaticDisseminationExperiment(
                            network=network,
                            seeders=seeders,
                            file_size=self.file_size,
                            seed=random.randint(0, 2**16),
                            meta=CodexMeta(f"dataset-{seeder_set}-{experiment_run}"),
                            logging_cooldown=self.logging_cooldown,
                            stagger_delay=self.stagger_delay,
                        )
                    )

        return IteratedExperiment(
            repetitions(), experiment_set_id=self.experiment_set_id
        )
