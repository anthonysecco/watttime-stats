"""WattTime sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENDPOINT_FORECAST, ENDPOINT_HISTORICAL, SIGNAL_HEALTH, SIGNAL_MOER, UNIT_HEALTH
from .coordinator import WattTimeConfigEntry, WattTimeCoordinator, WattTimeData
from .entity import WattTimeEntity, clock, co2

Convert = Callable[[float], float]


def _no_attrs(data: WattTimeData, convert: Convert) -> dict[str, Any]:
    return {}


@dataclass(frozen=True, kw_only=True)
class WattTimeSensorDescription(SensorEntityDescription):
    """How to read one sensor from the coordinator data."""

    value_fn: Callable[[WattTimeData, Convert], Any]
    attrs_fn: Callable[[WattTimeData, Convert], dict[str, Any]] = _no_attrs
    co2_unit: bool = False
    needs: tuple[str, str] | None = None  # (signal, endpoint) the account must have


def _round(value: float | None, convert: Convert) -> float | None:
    return None if value is None else round(convert(value), 1)


def _window_text(d: WattTimeData) -> str | None:
    return f"{clock(d.window.start)} – {clock(d.window.end)}" if d.window else None


def _status(d: WattTimeData) -> str | None:
    o = d.outlook
    if o is None:
        return None
    if o.clean_now:
        return f"Clean until {clock(o.until)}" if o.until else "Clean through the forecast"
    if o.next_start:
        return f"Next clean {clock(o.next_start)} – {clock(o.next_end)}"
    return "No clean stretch ahead"


FORECAST = (SIGNAL_MOER, ENDPOINT_FORECAST)

SENSORS: tuple[WattTimeSensorDescription, ...] = (
    WattTimeSensorDescription(
        key="emissions_index",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d, c: d.index,
        attrs_fn=lambda d, c: {"valid_from": d.index_time.isoformat() if d.index_time else None},
    ),
    WattTimeSensorDescription(
        key="marginal_emissions",
        co2_unit=True,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d, c: _round(d.moer.value if d.moer else None, c),
        attrs_fn=lambda d, c: {
            "valid_from": d.moer.time.isoformat() if d.moer else None,
            "source": d.moer_source,
        },
    ),
    WattTimeSensorDescription(
        key="health_damage",
        native_unit_of_measurement=UNIT_HEALTH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        needs=(SIGNAL_HEALTH, ENDPOINT_HISTORICAL),
        value_fn=lambda d, c: round(d.health.value, 2) if d.health else None,
        attrs_fn=lambda d, c: {"valid_from": d.health.time.isoformat() if d.health else None},
    ),
    WattTimeSensorDescription(
        key="cleanest_window",
        device_class=SensorDeviceClass.TIMESTAMP,
        needs=FORECAST,
        value_fn=lambda d, c: d.window.start if d.window else None,
        attrs_fn=lambda d, c: {
            "end": d.window.end.isoformat() if d.window else None,
            "average": _round(d.window.average if d.window else None, c),
            "text": _window_text(d),
        },
    ),
    WattTimeSensorDescription(
        key="clean_until",
        device_class=SensorDeviceClass.TIMESTAMP,
        needs=FORECAST,
        value_fn=lambda d, c: d.outlook.until if d.outlook and d.outlook.clean_now else None,
    ),
    WattTimeSensorDescription(
        key="next_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
        needs=FORECAST,
        value_fn=lambda d, c: d.outlook.next_start if d.outlook and not d.outlook.clean_now else None,
        attrs_fn=lambda d, c: {
            "end": d.outlook.next_end.isoformat() if d.outlook and d.outlook.next_end else None
        },
    ),
    WattTimeSensorDescription(
        key="clean_status",
        needs=FORECAST,
        value_fn=lambda d, c: _status(d),
    ),
    WattTimeSensorDescription(
        key="clean_threshold",
        co2_unit=True,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        needs=FORECAST,
        value_fn=lambda d, c: _round(d.outlook.threshold if d.outlook else None, c),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: WattTimeConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the sensors this account has data for."""
    coordinator = entry.runtime_data
    async_add_entities(
        WattTimeSensor(coordinator, d) for d in SENSORS if d.needs is None or coordinator.has(*d.needs)
    )


class WattTimeSensor(WattTimeEntity, SensorEntity):
    """One WattTime value."""

    entity_description: WattTimeSensorDescription

    def __init__(self, coordinator: WattTimeCoordinator, description: WattTimeSensorDescription) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        unit, self._convert = co2(coordinator.config_entry)
        if description.co2_unit:
            self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        """Current value."""
        return self.entity_description.value_fn(self.coordinator.data, self._convert)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Details such as when the value applies from."""
        return self.entity_description.attrs_fn(self.coordinator.data, self._convert)
