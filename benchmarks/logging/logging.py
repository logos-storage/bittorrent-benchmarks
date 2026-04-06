"""This module standardizes interfaces for consuming logs from external log sources; i.e. infrastructure
that stores logs. Such infrastructure might be a simple file system, a service like Logstash, or a database."""

import datetime
import json
import logging
from abc import ABC, abstractmethod
from csv import DictWriter
from enum import Enum
from json import JSONDecodeError
from typing import Type, TextIO, Iterable, Callable, Dict, Tuple, cast, Optional

from pydantic import ValidationError, computed_field, Field, BaseModel

from benchmarks.core.pydantic import SnakeCaseModel

MARKER = ">>"

logger = logging.getLogger(__name__)


class LogEntry(SnakeCaseModel):
    """
    Base class for log entries. Built so that structured logs are easy to produce with the standard logging module;
    e.g.:

    >> logging.getLogger(__name__)
    >>
    >> class DownloadEvent(LogEntry):
    >>     file: str
    >>     timestamp: datetime.datetime
    >>     node: str
    >>
    >> logger.info(DownloadEvent(file='some_file.csv', timestamp=datetime.datetime.now(), node='node1'))
    """

    def __str__(self):
        return f"{MARKER}{self.model_dump_json()}"

    @computed_field  # type: ignore
    @property
    def entry_type(self) -> str:
        return self.alias()

    @classmethod
    def adapt(cls, model: Type[BaseModel]) -> Type["AdaptedLogEntry"]:
        """Adapts an existing Pydantic model to a LogEntry. This is useful for when you have a model
        that you want to log and later recover from logs using :class:`LogParser` or :class:`LogSplitter`."""

        def adapt_instance(klass, data: BaseModel):
            return klass.model_validate(data.model_dump())

        def recover_instance(self):
            return model.model_validate(self.model_dump())

        adapted = type(
            f"{model.__name__}LogEntry",
            (
                LogEntry,
                model,
            ),
            {
                "adapt_instance": classmethod(adapt_instance),
                "recover_instance": recover_instance,
            },
        )

        return cast(Type[AdaptedLogEntry], adapted)


class AdaptedLogEntry(LogEntry, ABC):
    """Interface extension to adapted :class:`LogEntry`es which allows converting instances from the original model
    into the adapted model and vice-versa."""

    @classmethod
    @abstractmethod
    def adapt_instance(cls, data: BaseModel) -> "AdaptedLogEntry":
        pass

    @abstractmethod
    def recover_instance(self) -> BaseModel:
        pass


class ConfigToLogAdapters:
    """Utility class for managing adapted log entry types. This is mostly used to register different :class:`Experiment`
    configuration classes (typically :class:`ExperimentBuilder` models) so they can be logged and later recovered."""

    def __init__(self) -> None:
        self.adapters: Dict[Type[BaseModel], Type[AdaptedLogEntry]] = {}

    def adapt(self, model: Type[BaseModel]) -> Type[AdaptedLogEntry]:
        if model in self.adapters:
            return self.adapters[model]

        adapted = LogEntry.adapt(model)
        self.adapters[model] = adapted
        return adapted

    def adapt_instance(self, instance: BaseModel) -> AdaptedLogEntry:
        return self.adapt(instance.__class__).adapt_instance(instance)

    def adapted_types(self) -> Iterable[Type[AdaptedLogEntry]]:
        return self.adapters.values()

    def __getitem__(self, model: Type[BaseModel]) -> Type[AdaptedLogEntry]:
        return self.adapt(model)


type Logs = Iterable[LogEntry]


class LogParser:
    """:class:`LogParser` will pick up log entries from a stream and parse them into :class:`LogEntry` instances.
    It works by trying to find a special marker (>>) in the log line, and then parsing the JSON that follows it.
    This allows us to flexibly overlay structured logs on top of existing logging frameworks without having to
    aggressively modify them."""

    def __init__(self):
        self.entry_types = {}
        self.warn_counts = 10

    def register(self, entry_type: Type[LogEntry]):
        self.entry_types[entry_type.alias()] = entry_type

    def parse(self, log: Iterable[str]) -> Logs:
        for line in log:
            parsed = self.parse_single(line)
            if not parsed:
                continue
            yield parsed

    def parse_single(self, line: str) -> Optional[LogEntry]:
        marker_len = len(MARKER)
        index = line.find(MARKER)
        if index == -1:
            return None

        type_tag = ""  # just to calm down mypy
        try:
            # Should probably test this against a regex for the type tag to see which is faster.
            json_line = json.loads(line[index + marker_len :])
            type_tag = json_line.get("entry_type")
            if not type_tag or (type_tag not in self.entry_types):
                return None
            return self.entry_types[type_tag].model_validate(json_line)
        except JSONDecodeError:
            pass
        except ValidationError as err:
            # This is usually something we want to know about, as if the message has a type_tag
            # that we know, then we should probably be able to parse it.
            self.warn_counts -= 1  # avoid flooding everything with warnings
            if self.warn_counts > 0:
                logger.warning(
                    f"Schema failed for line with known type tag {type_tag}: {err}"
                )
            elif self.warn_counts == 0:
                logger.warning("Too many errors: suppressing further schema warnings.")

        return None


class LogSplitterFormats(Enum):
    jsonl = "jsonl"
    csv = "csv"


class LogSplitter:
    """:class:`LogSplitter` will split parsed logs into different files based on the entry type.
    The output format can be set for each entry type."""

    def __init__(
        self,
        output_factory=Callable[[str, LogSplitterFormats], TextIO],
        output_entry_type=False,
    ) -> None:
        self.output_factory = output_factory
        self.outputs: Dict[str, Tuple[Callable[[LogEntry], None], TextIO]] = {}
        self.formats: Dict[str, LogSplitterFormats] = {}
        self.exclude = {"entry_type"} if not output_entry_type else set()

    def set_format(self, entry_type: Type[LogEntry], output_format: LogSplitterFormats):
        self.formats[entry_type.alias()] = output_format

    def split(self, log: Iterable[LogEntry]):
        for entry in log:
            self.split_single(entry)

    def split_single(self, entry: LogEntry):
        write, _ = self.outputs.get(entry.entry_type, (None, None))

        if write is None:
            output_format = self.formats.get(entry.entry_type, LogSplitterFormats.csv)
            output_stream = self.output_factory(entry.entry_type, output_format)

            write = self._formatting_writer(entry, output_stream, output_format)
            self.outputs[entry.entry_type] = write, output_stream

        write(entry)

    def _formatting_writer(
        self, entry: LogEntry, output_stream: TextIO, output_format: LogSplitterFormats
    ) -> Callable[[LogEntry], None]:
        if output_format == LogSplitterFormats.csv:
            writer = DictWriter(
                output_stream, fieldnames=entry.model_dump(exclude=self.exclude).keys()
            )
            writer.writeheader()
            return lambda x: writer.writerow(x.model_dump(exclude=self.exclude))

        elif output_format == LogSplitterFormats.jsonl:

            def write_jsonl(x: LogEntry):
                output_stream.write(x.model_dump_json(exclude=self.exclude) + "\n")

            return write_jsonl

        else:
            raise ValueError(f"Unknown output format: {output_format}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for _, output in self.outputs.values():
            output.close()


type NodeId = str


class Event(LogEntry):
    name: str  # XXX this ends up being redundant for custom event schemas... need to think of a better solution.
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


class NodeEvent(Event):
    node: NodeId


class Metric(NodeEvent):
    value: int | float


class DownloadMetric(Metric):
    name: str = "download"
    dataset_name: str


class BlocksServedMetric(Metric):
    name: str = "blocks_served"


class EventBoundary(Enum):
    start = "start"
    end = "end"


class RequestEvent(NodeEvent):
    destination: NodeId
    request_id: str
    type: EventBoundary


class ExperimentStatus(Event):
    repetition: int
    duration: float
    error: Optional[str] = None


class ExperimentStage(Event):
    stage: str
    type: EventBoundary
    error: Optional[str] = None


def basic_log_parser() -> LogParser:
    """Constructs a basic log parser which can understand some common log entry types."""
    parser = LogParser()
    parser.register(Event)
    parser.register(NodeEvent)
    parser.register(Metric)
    parser.register(DownloadMetric)
    parser.register(BlocksServedMetric)
    parser.register(RequestEvent)
    parser.register(ExperimentStatus)
    parser.register(ExperimentStage)
    return parser
