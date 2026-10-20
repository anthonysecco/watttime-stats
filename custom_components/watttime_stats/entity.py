"""Shared entity base."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTION,
    CONF_REGION_NAME,
    CONF_UNIT,
    DEFAULT_UNIT,
    DOMAIN,
    G_KWH_PER_LBS_MWH,
    UNIT_G_KWH,
    UNIT_OPTIONS,
)
from .coordinator import WattTimeCoordinator


def co2(entry: ConfigEntry) -> tuple[str, Callable[[float], float]]:
    """The chosen CO2 unit and a converter from lbs/MWh."""
    unit = UNIT_OPTIONS.get(entry.options.get(CONF_UNIT, DEFAULT_UNIT), UNIT_G_KWH)
    if unit == UNIT_G_KWH:
        return unit, lambda v: v * G_KWH_PER_LBS_MWH
    return unit, lambda v: v


def clock(moment: datetime | None) -> str | None:
    """Local time like "4:30 PM"."""
    if moment is None:
        return None
    local = dt_util.as_local(moment)
    return f"{local.hour % 12 or 12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


class WattTimeEntity(CoordinatorEntity[WattTimeCoordinator]):
    """Groups every entity under one WattTime service device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: WattTimeCoordinator, key: str) -> None:
        """Set up names and IDs."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="WattTime",
            manufacturer="WattTime",
            model=entry.data.get(CONF_REGION_NAME),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://watttime.org/",
        )
