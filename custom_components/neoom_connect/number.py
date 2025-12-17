"""Number Plattform für neoom Connect (Steuerung)."""
from homeassistant.components.number import (
    NumberEntity,
    NumberDeviceClass,
    NumberMode,
)
from homeassistant.const import UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, LOGGER

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Richtet die Number-Plattform ein."""
    data = hass.data[DOMAIN][entry.entry_id]
    local_coordinator = data["local"]

    entities = []

    # Hole Konfiguration (kann initial leer sein)
    beaam_config = local_coordinator.data.get("config", {}) if local_coordinator.data else {}
    
    if beaam_config:
        things = beaam_config.get("things", {})
        
        for thing_id, thing_data in things.items():
            if not thing_data: continue

            thing_type = thing_data.get("type")
            datapoints = thing_data.get("dataPoints", {})

            for dp_id, dp_data in datapoints.items():
                if not dp_data: continue

                # Suche nach steuerbaren numerischen Werten ("controllable": true)
                dtype = dp_data.get("dataType")
                controllable = dp_data.get("controllable", False)
                
                if dtype == "NUMBER" and controllable:
                    entities.append(NeoomLocalNumber(
                        local_coordinator, 
                        thing_id, 
                        thing_data, 
                        dp_id, 
                        dp_data
                    ))

    async_add_entities(entities)


class NeoomLocalNumber(CoordinatorEntity, NumberEntity):
    """Repräsentation eines steuerbaren Nummern-Werts (Slider/Input)."""

    def __init__(self, coordinator, thing_id, thing_data, dp_id, dp_data):
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type = thing_data.get("type", "Unknown")
        self._dp_id = dp_id
        self._key = dp_data.get("key")
        self._uom_raw = dp_data.get("unitOfMeasure")
        
        friendly_thing_name = self._thing_type.replace("_", " ").title()
        friendly_dp_name = self._key.replace("_", " ").title()
        self._attr_name = f"{friendly_thing_name} {friendly_dp_name}"
        self._attr_unique_id = f"{thing_id}_{dp_id}_number"

        # Setze Einheiten und Device Class
        if self._uom_raw == "%":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = NumberDeviceClass.BATTERY
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100
            self._attr_native_step = 1
        elif self._uom_raw == "W":
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_device_class = NumberDeviceClass.POWER
            # Dynamische Bereiche wären besser, aber wir setzen sichere Standardwerte basierend auf typischen Systemgrößen
            # Max Speicherleistung ~15kW, Max Netz ~11kW (laut Beispiel-JSON)
            self._attr_native_min_value = -20000 
            self._attr_native_max_value = 20000
            self._attr_native_step = 100
        else:
            # Fallback für unbekannte Einheiten
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100000
            self._attr_native_step = 1

        # Modus: Eingabebox für Leistung (sicherer), Slider für Prozent
        self._attr_mode = NumberMode.BOX 
        if self._uom_raw == "%":
             self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self):
        """Gibt den aktuellen Wert aus dem Koordinator zurück."""
        if not self.coordinator.data: return None
        
        state_map = self.coordinator.data.get("states", {})
        data_point = state_map.get(self._dp_id)
        
        if data_point:
            val = data_point.get("value")
            if val is not None:
                return float(val)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Sendet den neuen Wert an die API."""
        LOGGER.info(f"Setze {self._key} auf {value}")
        await self.coordinator.async_send_command(self._thing_id, self._key, value)

    @property
    def device_info(self):
        """Verknüpfung zum Gerät."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_id)},
            name=f"neoom {self._thing_type}",
            manufacturer="neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway")
        )