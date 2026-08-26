"""Request/response schemas for the chemunited API."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from chemunited_workflow.durations import parse_timeout_commands


class ProcessInfo(BaseModel):
    name: str
    description: str
    config_schema: dict[str, Any]


class ProtocolMeta(BaseModel):
    filename: str
    modified: str
    size_bytes: int


class ProtocolIn(BaseModel):
    """Request body for POST /protocols. Each save always creates a new versioned file."""

    name: str
    data: dict[str, Any]


class RunRequest(BaseModel):
    protocol: str = Field(
        default="",
        title="Protocol name to run",
        description="Protocol json file containing the process order and parameters",
    )
    dry_run: bool = Field(
        default=False,
        title="Dry execution",
        description=(
            "If true, only log the commands without executing them.\n"
            "Useful to validate the snapshot order and parameters before running."
        ),
    )
    timeout_commands: str = Field(
        default="",
        title="Timeout duration to wait for device idle",
        description=(
            "Timeout duration to wait for a flowchem device to report idle after\n"
            "a command runs. If timeout_commands is set to an empty string, the\n"
            "protocol will wait indefinitely. Accepted format: <value> <unit>,\n"
            "where unit can be 's' (seconds)."
        ),
    )
    error_resilient: bool = Field(
        default=False,
        title="Error-resilient execution",
        description=(
            "If true, client-side errors (HTTP failures, timeouts) are logged "
            "but do not interrupt node execution — all commands in a node method "
            "run to completion. The node is still marked FAILED; its successors "
            "become INACTIVE. Other independent branches continue normally.\n"
            "If false (default), any error stops the entire run immediately."
        ),
    )
    record_monitoring: bool = Field(
        default=False,
        title="Record monitoring data",
        description=(
            "If true, monitoring is forced on for this run's duration and every "
            "reading polled is also persisted to log/monitoring/{run_id}/, using "
            "whatever variables are currently registered via PUT /monitoring/config. "
            "Live viewing works the same either way."
        ),
    )

    @field_validator("timeout_commands")
    @classmethod
    def validate_timeout_commands(cls, value: str) -> str:
        parse_timeout_commands(value)
        return value.strip()

    @model_validator(mode="after")
    def apply_dry_run_timeout(self) -> "RunRequest":
        if self.dry_run and not self.timeout_commands:
            self.timeout_commands = "1 s"
        return self


class RunStatus(BaseModel):
    run_id: str
    state: str
    events: list[dict[str, Any]]


class RunInputIn(BaseModel):
    """Request body for POST /run/input — an operator's reply to a pending node prompt."""

    node_id: str
    value: str


class LogMeta(BaseModel):
    filename: str
    modified: str
    size_bytes: int


class ProcessSource(BaseModel):
    name: str
    source: str


class LogSearchResult(BaseModel):
    filename: str
    line_number: int
    line: str


class ComponentStatus(BaseModel):
    component: str
    url: str
    online: bool
    status_code: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    reachability: Literal["online", "offline", "unknown"] | None = None
    reachability_supported: bool | None = None


class ComponentCommandIn(BaseModel):
    verb: Literal["get", "put"]
    params: dict[str, Any] | None = None
    body: Any | None = None


class ComponentCommandResult(BaseModel):
    component: str
    command: str
    url: str
    ok: bool
    status_code: int | None = None
    latency_ms: int | None = None
    response: Any | None = None
    error: str | None = None


class CustomRouteParameter(BaseModel):
    name: str
    required: bool
    default: Any | None = None


class CustomRouteInfo(BaseModel):
    name: str
    parameters: list[CustomRouteParameter]


class CustomRouteResult(BaseModel):
    name: str
    ok: bool
    result: Any | None = None
    error: str | None = None
    latency_ms: int | None = None


class ProjectIn(BaseModel):
    project_dir: str


class ProjectOut(BaseModel):
    project_dir: str | None = None


class PlatformDevice(BaseModel):
    id: str
    label: str
    figure: str | None = None
    is_electronic: bool | None = None
    x: float
    y: float
    w: float
    h: float


class MonitoringVariableIn(BaseModel):
    component: str = Field(
        description="Component name, matching an entry in connectivity/associations.json."
    )
    command: str = Field(description="GET command/path to poll on the component.")
    kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra query parameters passed to the GET request.",
    )


class MonitoringConfigIn(BaseModel):
    sample_time: float = Field(
        gt=0,
        description="Seconds between sampling ticks.",
    )
    request_timeout: float = Field(
        default=5.0,
        gt=0,
        description="Per-request timeout in seconds. A hung device only delays its own reading.",
    )
    variables: list[MonitoringVariableIn] = Field(default_factory=list)


class MonitoringStateOut(BaseModel):
    manual_on: bool
    run_active: bool
    recording: bool
    run_id: str | None
    effective_on: bool


class MonitoringReading(BaseModel):
    tick: int
    time: str
    value: Any | None = None
    error: str | None = None


class ExportEntry(BaseModel):
    filename: str
    size_bytes: int
    modified: str


class ExportMonitoringGroup(BaseModel):
    run_id: str
    files: list[ExportEntry]
    total_size_bytes: int


class ExportRow(BaseModel):
    log: ExportEntry
    monitoring: ExportMonitoringGroup | None = None
    protocol: ExportEntry | None = None


class ExportCleanRequest(BaseModel):
    logs: list[str] = Field(min_length=1)


class ExportCleanResult(BaseModel):
    deleted: list[str]
    count: int
