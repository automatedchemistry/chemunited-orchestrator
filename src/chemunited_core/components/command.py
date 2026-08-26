from dataclasses import dataclass, field


@dataclass
class ScheduledCommand:
    """A follow-up command to fire at a relative sim time after the triggering put()."""

    dt: float  # seconds from now
    command: str
    kwargs: dict = field(default_factory=dict)


@dataclass
class PutResult:
    scheduled: list[ScheduledCommand] = field(default_factory=list)
