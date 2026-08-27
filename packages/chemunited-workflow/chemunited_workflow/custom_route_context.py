"""Read-only window into a custom route call's throwaway Platform, for
custom router actions that need to reach a real device.

See docs/api-reference.md#custom-routes.
"""

from __future__ import annotations

from .platform import Platform


class CustomRouteContext:
    """Holds the Platform instance open for the current custom route call.

    A CUSTOM_ROUTES function reads `CustomRouteContext.platform` to reach a
    real device. Unlike `MonitoringContext`, which stays set for an entire
    monitoring poll cycle, this is set fresh for the duration of a single
    call — a throwaway, unlocked Platform opened just for that call and
    closed once it returns, the same pattern `send_component_command` uses
    for an ad-hoc component command. Never reuse `MonitoringContext` for
    this purpose: its Platform belongs to the poll loop for the whole
    ON-cycle, and a route call observing or closing it would race with
    monitoring.

    `None` whenever no custom route call is currently in flight. Never call
    `.close()` or `.register()` on anything reached through it: the caller
    owns this Platform's lifecycle for the call's duration.
    """

    platform: Platform | None = None
