"""Request and response shapes for the chaos module.

Every scenario has its own small request model (so validation errors name the right field), but they
all reduce to the same internal ``EventSpec`` that the service applies. The generic ``/chaos/apply``
endpoint and the ``multi-failure`` endpoint reuse the same parameter models.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.enums import ChaosStatus, ScenarioType, TargetType
from app.errors import BadRequestError, field_code
from app.schemas.network import Name

# One definition of each constraint, shared by every request that uses it.
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False, description="Percent, 0 to 100")]
Milliseconds = Annotated[float, Field(ge=0, allow_inf_nan=False, description="Milliseconds, >= 0")]
Mbps = Annotated[float, Field(gt=0, allow_inf_nan=False, description="Mbps, > 0")]
ReductionPercent = Annotated[
    float, Field(ge=0, lt=100, allow_inf_nan=False, description="Percent of bandwidth removed, 0 to < 100")
]

FAILURE_SCENARIOS = (ScenarioType.ROUTER_FAILURE, ScenarioType.LINK_FAILURE)
SINGLE_SCENARIOS = tuple(s for s in ScenarioType if s is not ScenarioType.MULTI_FAILURE)


@dataclass(frozen=True)
class EventSpec:
    """One validated change to one node or link, before it touches the database."""
    scenario: ScenarioType
    target_type: TargetType
    target_id: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentSpec:
    name: str | None
    description: str | None
    scenario: ScenarioType
    events: list[EventSpec]


class _Meta(BaseModel):
    experiment_name: Name | None = Field(default=None, description="Optional; a name is generated if omitted")
    description: str | None = Field(default=None, max_length=1000)


# --- specialised requests ---------------------------------------------------------------------
class RouterFailureRequest(_Meta):
    node_id: str = Field(examples=["node_003"])

    def to_experiment(self) -> ExperimentSpec:
        return _single(self, EventSpec(ScenarioType.ROUTER_FAILURE, TargetType.NODE, self.node_id))


class LinkFailureRequest(_Meta):
    link_id: str = Field(examples=["link_003"])

    def to_experiment(self) -> ExperimentSpec:
        return _single(self, EventSpec(ScenarioType.LINK_FAILURE, TargetType.LINK, self.link_id))


class PacketLossRequest(_Meta):
    link_id: str = Field(examples=["link_003"])
    packet_loss: Percent = Field(examples=[30])

    def to_experiment(self) -> ExperimentSpec:
        spec = EventSpec(ScenarioType.PACKET_LOSS, TargetType.LINK, self.link_id, {"packet_loss": self.packet_loss})
        return _single(self, spec)


class LatencyRequest(_Meta):
    link_id: str = Field(examples=["link_003"])
    latency: Milliseconds = Field(examples=[150])

    def to_experiment(self) -> ExperimentSpec:
        return _single(self, EventSpec(ScenarioType.LATENCY, TargetType.LINK, self.link_id, {"latency": self.latency}))


class BandwidthReductionRequest(_Meta):
    link_id: str = Field(examples=["link_003"])
    bandwidth: Mbps = Field(examples=[20])

    def to_experiment(self) -> ExperimentSpec:
        spec = EventSpec(ScenarioType.BANDWIDTH_REDUCTION, TargetType.LINK, self.link_id, {"bandwidth": self.bandwidth})
        return _single(self, spec)


class CongestionRequest(_Meta):
    link_id: str = Field(examples=["link_003"])
    latency_increase: Milliseconds = Field(default=0, examples=[50])
    bandwidth_reduction_percent: ReductionPercent = Field(default=0, examples=[40])
    packet_loss: Percent = Field(default=0, description="Extra loss in percentage points, added to the link's own", examples=[10])

    def to_experiment(self) -> ExperimentSpec:
        params = {
            "latency_increase": self.latency_increase,
            "bandwidth_reduction_percent": self.bandwidth_reduction_percent,
            "packet_loss": self.packet_loss,
        }
        return _single(self, EventSpec(ScenarioType.CONGESTION, TargetType.LINK, self.link_id, params))


# --- multi-failure: one event per entry, chosen by "type" ------------------------------------------
class _RouterFailureEvent(BaseModel):
    type: Literal["router_failure"]
    node_id: str


class _LinkFailureEvent(BaseModel):
    type: Literal["link_failure"]
    link_id: str


class _PacketLossEvent(BaseModel):
    type: Literal["packet_loss"]
    link_id: str
    packet_loss: Percent


class _LatencyEvent(BaseModel):
    type: Literal["latency"]
    link_id: str
    latency: Milliseconds


class _BandwidthEvent(BaseModel):
    type: Literal["bandwidth_reduction"]
    link_id: str
    bandwidth: Mbps


class _CongestionEvent(BaseModel):
    type: Literal["congestion"]
    link_id: str
    latency_increase: Milliseconds = 0
    bandwidth_reduction_percent: ReductionPercent = 0
    packet_loss: Percent = 0


MultiEvent = Annotated[
    Union[_RouterFailureEvent, _LinkFailureEvent, _PacketLossEvent, _LatencyEvent, _BandwidthEvent, _CongestionEvent],
    Field(discriminator="type"),
]


def _event_spec(event: BaseModel) -> EventSpec:
    scenario = ScenarioType(event.type)  # type: ignore[attr-defined]
    if scenario is ScenarioType.ROUTER_FAILURE:
        return EventSpec(scenario, TargetType.NODE, event.node_id)  # type: ignore[attr-defined]
    params = event.model_dump(exclude={"type", "link_id"})
    return EventSpec(scenario, TargetType.LINK, event.link_id, params)  # type: ignore[attr-defined]


class MultiFailureRequest(_Meta):
    events: list[MultiEvent] = Field(min_length=1, max_length=50, description="Applied together as one experiment")

    def to_experiment(self) -> ExperimentSpec:
        return ExperimentSpec(
            self.experiment_name, self.description, ScenarioType.MULTI_FAILURE, [_event_spec(e) for e in self.events]
        )


# --- generic apply -----------------------------------------------------------------------------
class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo in "parameters" must not silently do nothing


class _NoParams(_Params):
    pass


class _PacketLossParams(_Params):
    packet_loss: Percent


class _LatencyParams(_Params):
    latency: Milliseconds


class _BandwidthParams(_Params):
    bandwidth: Mbps


class _CongestionParams(_Params):
    latency_increase: Milliseconds = 0
    bandwidth_reduction_percent: ReductionPercent = 0
    packet_loss: Percent = 0


class _MultiParams(_Params):
    events: list[MultiEvent] = Field(min_length=1, max_length=50)


_PARAM_MODELS: dict[ScenarioType, type[_Params]] = {
    ScenarioType.ROUTER_FAILURE: _NoParams,
    ScenarioType.LINK_FAILURE: _NoParams,
    ScenarioType.PACKET_LOSS: _PacketLossParams,
    ScenarioType.LATENCY: _LatencyParams,
    ScenarioType.BANDWIDTH_REDUCTION: _BandwidthParams,
    ScenarioType.CONGESTION: _CongestionParams,
    ScenarioType.MULTI_FAILURE: _MultiParams,
}


class ApplyRequest(_Meta):
    """Generic form of every scenario. For ``multi_failure`` put ``{"events": [...]}`` in ``parameters``."""
    scenario: ScenarioType
    target_id: str | None = Field(default=None, description="node_id (router_failure) or link_id; not used by multi_failure")
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_experiment(self) -> ExperimentSpec:
        try:
            params = _PARAM_MODELS[self.scenario].model_validate(self.parameters)
        except ValidationError as exc:
            err = exc.errors()[0]
            loc = [str(p) for p in err["loc"]]
            raise BadRequestError(f"parameters.{'.'.join(loc)}: {err['msg']}", field_code(loc[-1] if loc else "parameters")) from None

        if self.scenario is ScenarioType.MULTI_FAILURE:
            events = [_event_spec(e) for e in params.events]  # type: ignore[attr-defined]
            return ExperimentSpec(self.experiment_name, self.description, self.scenario, events)
        if not self.target_id:
            raise BadRequestError(f"target_id is required for '{self.scenario.value}'", "invalid_target_id")
        target_type = TargetType.NODE if self.scenario is ScenarioType.ROUTER_FAILURE else TargetType.LINK
        spec = EventSpec(self.scenario, target_type, self.target_id, params.model_dump())
        return _single(self, spec)


def _single(meta: _Meta, spec: EventSpec) -> ExperimentSpec:
    return ExperimentSpec(meta.experiment_name, meta.description, spec.scenario, [spec])


# --- responses ------------------------------------------------------------------------------------
class ChaosEventResponse(BaseModel):
    event_id: str = Field(examples=["evt_001"])
    scenario: ScenarioType
    target_type: TargetType
    target_id: str
    target_label: str = Field(description="Node name, or 'A ↔ B' for a link")
    parameters: dict[str, Any]
    previous_state: dict[str, Any] = Field(description="The target's original state before any active chaos")
    new_state: dict[str, Any] | None = Field(description="Its effective state right after this event")
    status: ChaosStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ExperimentResponse(BaseModel):
    experiment_id: str = Field(examples=["chaos_001"])
    network_id: str
    name: str
    description: str | None = None
    scenario: ScenarioType
    target: str = Field(description="target id, or 'network' for multi_failure")
    target_label: str
    status: ChaosStatus
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    events: list[ChaosEventResponse]


class ActiveExperiment(BaseModel):
    """One active experiment. For single-event experiments the scenario's parameters (packet_loss,
    latency, ...) are repeated at the top level for convenience; multi_failure lists its ``events``."""
    experiment_id: str
    name: str
    scenario: ScenarioType
    target: str
    target_label: str
    status: ChaosStatus
    created_at: datetime
    started_at: datetime | None = None
    packet_loss: float | None = None
    latency: float | None = None
    bandwidth: float | None = None
    latency_increase: float | None = None
    bandwidth_reduction_percent: float | None = None
    events: list[ChaosEventResponse]


class ActiveChaosResponse(BaseModel):
    network_id: str
    active_experiments: list[ActiveExperiment]


class HistoryItem(BaseModel):
    experiment_id: str
    name: str
    scenario: ScenarioType
    target: str
    target_label: str
    status: ChaosStatus
    event_count: int
    created_at: datetime
    ended_at: datetime | None = None


class HistoryResponse(BaseModel):
    network_id: str
    experiments: list[HistoryItem] = Field(description="Newest first")


class RestoredTarget(BaseModel):
    target_type: TargetType
    target_id: str
    target_label: str
    state: dict[str, Any] = Field(description="Effective state after the revert (still layered if other chaos is active)")


class RevertResponse(BaseModel):
    network_id: str
    experiment_id: str
    status: ChaosStatus
    already_reverted: bool = Field(description="True if the experiment was already reverted; nothing changed")
    reverted_events: int
    restored: list[RestoredTarget]


class ResetResponse(BaseModel):
    network_id: str
    reverted_experiments: int
    status: Literal["reset"] = "reset"
