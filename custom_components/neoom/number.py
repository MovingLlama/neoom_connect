"""Number Plattform für neoom AI.

Diese Datei definiert Entitäten zur Zahleneingabe (Slider oder Eingabefelder),
mit denen Werte an das lokale BEAAM Gateway gesendet werden können
(z.B. Ladeleistung oder Reservierungs-Ziele).
"""

from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import NeoomLocalCoordinator

# Diese Schlüssel werden konsequent ignoriert, auch wenn die API sie als "controllable" (steuerbar) markiert.
# Grund: Oft sind diese Werte kritisch für das Batteriemanagementsystem oder 
# sollten nicht manuell von einem übergeordneten System wie Home Assistant permanent überschrieben werden.
IGNORE_KEYS: List[str] = ["MIN_SOC", "MAX_POWER_CHARGE_FALLBACK", "TARGET_POWER"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[NumberEntity]], None],
) -> None:
    """Richtet die Number-Plattform basierend auf dem Konfigurationseintrag ein.
    
    Diese Methode baut Number-Entitäten dynamisch auf, indem sie die BEAAM 
    Konfiguration nach steuerbaren, numerischen Datenpunkten durchsucht.
    """
    
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    # Number-Entitäten steuern nur das lokale Gateway, daher brauchen wir nur den lokalen Coordinator
    local_coordinator: NeoomLocalCoordinator = data["local"]

    entities: List[NumberEntity] = []

    # Hole die statische Konfiguration (enthält alle bekannten Geräte)
    beaam_config: Dict[str, Any] = (
        local_coordinator.data.get("config", {}) if local_coordinator.data else {}
    )
    
    if beaam_config:
        things: Dict[str, Any] = beaam_config.get("things", {})
        
        for thing_id, thing_data in things.items():
            if not thing_data:
                continue

            datapoints: Dict[str, Any] = thing_data.get("dataPoints", {})

            for dp_id, dp_data in datapoints.items():
                if not dp_data:
                    continue

                # Wir interessieren uns nur für steuerbare ("controllable": true) Zahlen ("NUMBER")
                dtype: str = dp_data.get("dataType", "")
                controllable: bool = dp_data.get("controllable", False)
                key: str = dp_data.get("key", "")
                
                # Filtern von unerwünschten Schlüsseln
                if dtype == "NUMBER" and controllable and key not in IGNORE_KEYS:
                    entities.append(
                        NeoomLocalNumber(
                            coordinator=local_coordinator, 
                            thing_id=thing_id, 
                            thing_data=thing_data, 
                            dp_id=dp_id, 
                            dp_data=dp_data
                        )
                    )

    # Entitäten in Home Assistant registrieren
    async_add_entities(entities)


class NeoomLocalNumber(CoordinatorEntity, NumberEntity):
    """Repräsentation eines steuerbaren numerischen Werts (Number Entity)."""

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        dp_id: str,
        dp_data: Dict[str, Any],
    ) -> None:
        """Initialisiert die Number-Entität."""
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type: str = thing_data.get("type", "Unknown")
        self._dp_id = dp_id
        self._key: str = dp_data.get("key", "")
        self._uom_raw: str = dp_data.get("unitOfMeasure", "")
        
        # Mache den Namen benutzerfreundlich
        friendly_thing_name = self._thing_type.replace("_", " ").title()
        friendly_dp_name = self._key.replace("_", " ").title()
        
        self._attr_name = f"{friendly_thing_name} {friendly_dp_name}"
        self._attr_unique_id = f"{thing_id}_{dp_id}_number"

        # Setze Einheiten, Device Class und Limits basierend auf der Einheit
        if self._uom_raw == "%":
            # Prozentwerte (Slider 0-100)
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = NumberDeviceClass.BATTERY
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100
            self._attr_native_step = 1
            self._attr_mode = NumberMode.SLIDER
        elif self._uom_raw == "W":
            # Leistungswerte in Watt (Eingabebox für präzise Werte, auch negativ)
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_device_class = NumberDeviceClass.POWER
            # Standardgrenzwerte für übliche Heimsysteme (+/- 20kW)
            self._attr_native_min_value = -20000 
            self._attr_native_max_value = 20000
            self._attr_native_step = 100
            self._attr_mode = NumberMode.BOX
        else:
            # Fallback für unbekannte Einheiten (Standard: Eingabebox)
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100000
            self._attr_native_step = 1
            self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> Optional[float]:
        """Gibt den aktuellen Wert aus dem Koordinator zurück, um ihn in der UI anzuzeigen."""
        if not self.coordinator.data:
            return None
        
        state_map: Dict[str, Any] = self.coordinator.data.get("states", {})
        data_point: Optional[Dict[str, Any]] = state_map.get(self._dp_id)
        
        if data_point:
            val = data_point.get("value")
            if val is not None:
                return float(val)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Wird aufgerufen, wenn der Benutzer einen neuen Wert in der HA-Oberfläche eingibt.
        
        Sendet den neuen Wert via API an das BEAAM Gateway.
        """
        LOGGER.info("Setze %s auf %s", self._key, value)
        await self.coordinator.async_send_command(self._thing_id, self._key, value)

    @property
    def device_info(self) -> DeviceInfo:
        """Verknüpfung der Entität mit dem physischen Gerät (Thing) im Device Registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_id)},
            name=f"neoom {self._thing_type}",
            manufacturer="neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway"),
        )
