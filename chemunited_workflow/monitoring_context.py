"""Read-only window into the monitoring poll loop's current Platform, for
custom monitoring sources that need to read a real device.

See docs/api-reference.md#custom-sources.
"""

from __future__ import annotations

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
    """

    platform: Platform | None = None
