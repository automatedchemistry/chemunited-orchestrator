"""Window into the monitoring poll loop for custom monitoring sources: its
current Platform, for reading a real device, and the one control a source
may need — stopping the active protocol run, for a safety interlock.

See docs/api-reference.md#custom-sources.
"""

from __future__ import annotations

from collections.abc import Callable

from .platform import Platform


class MonitoringContext:
    """Holds the Platform instance the monitoring poll loop currently has open.

    A CUSTOM_SOURCES function reads `MonitoringContext.platform` to reach a
    real device — it's the exact same Platform (and ComponentClient
    instances/locks) real-component readings use for that ON-cycle, so a
    device read shares its lock and connection instead of opening a second,
    separately-locked connection to the same physical device.

    `None` whenever no poll cycle is currently running — a function that
    reads a device should treat this as "no reading available" rather than
    assume it's always set. Never call `.close()` or `.register()` on
    anything reached through it: the poll loop owns this Platform's
    lifecycle for the whole ON-cycle.

    `stop_run()` stops the active protocol run the way the dashboard's Stop
    button does — for a source acting as a safety interlock, such as an
    overpressure trip. Like `platform`, it is only wired up while a poll
    cycle runs inside the API server.
    """

    platform: Platform | None = None
    # Published by the API's MonitoringService alongside `platform`.
    _stop_run: Callable[[], bool] | None = None

    @classmethod
    def stop_run(cls) -> bool:
        """Stop the active protocol run, as the dashboard's Stop button does.

        Returns True if a run was stopped; False if none was running, or no
        run control is available (no poll cycle running, or outside the API
        server).
        """
        stop = cls._stop_run
        return bool(stop is not None and stop())
