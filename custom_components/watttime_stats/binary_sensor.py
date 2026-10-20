"""Clean Now binary sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENDPOINT_FORECAST, SIGNAL_MOER
from .coordinator import WattTimeConfigEntry
from .entity import WattTimeEntity, co2


async def async_setup_entry(
    hass: HomeAssistant, entry: WattTimeConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Clean Now when the account has forecasts."""
    coordinator = entry.runtime_data
    if coordinator.has(SIGNAL_MOER, ENDPOINT_FORECAST):
        async_add_entities([WattTimeCleanNow(coordinator, "clean_now")])


class WattTimeCleanNow(WattTimeEntity, BinarySensorEntity):
    """On while emissions are in the cleanest part of the look-ahead."""

    @property
    def is_on(self) -> bool | None:
        """Whether it is clean right now."""
        outlook = self.coordinator.data.outlook
        return outlook.clean_now if outlook else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The cutoff in use."""
        outlook = self.coordinator.data.outlook
        unit, convert = co2(self.coordinator.config_entry)
        return {"threshold": round(convert(outlook.threshold), 1) if outlook else None, "unit": unit}
