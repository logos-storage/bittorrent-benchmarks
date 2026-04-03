from pydantic import Field, computed_field
from typing_extensions import Generic, TypeVar, List

from benchmarks.core.pydantic import ConfigModel

TNodeConfig = TypeVar("TNodeConfig")
TNodeSetConfig = TypeVar("TNodeSetConfig")


class DisseminationExperimentConfig(ConfigModel, Generic[TNodeConfig, TNodeSetConfig]):
    """Base configuration for static dissemination experiments. By adhering to this schema,
    you can much more easily plug in your experiment into existing workflows.
    """

    experiment_set_id: str = Field(
        description="Identifies the group of experiment repetitions", default="unnamed"
    )
    seeder_sets: int = Field(
        gt=0, default=1, description="Number of distinct seeder sets to experiment with"
    )
    seeders: int = Field(gt=0, description="Number of seeders per seeder set")

    file_size: int = Field(gt=0, description="File size, in bytes")

    nodes: List[TNodeConfig] | TNodeSetConfig = Field(
        description="Configuration for the nodes that make up the network"
    )

    logging_cooldown: int = Field(
        ge=0,
        default=0,
        description="Time to wait after the last download completes before tearing down the experiment.",
    )

    stagger_delay: float = Field(
        ge=0,
        default=0,
        description="Delay in seconds between starting each leecher (0 = simultaneous).",
    )

    @computed_field  # type: ignore
    @property
    def experiment_type(self) -> str:
        return self.alias()
