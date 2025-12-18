"""Select Plattform für neoom Connect (Auswahl-Menüs)."""
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, LOGGER

# Bekannte Optionen für spezifische Schlüssel.
# Da die API uns keine Liste der erlaubten Werte gibt, müssen wir sie hier definieren.
KNOWN_OPTIONS = {
    "PHASE_SWITCHING_MODE": ["AUTO", "FORCE_1_PHASE", "FORCE_3_PHASE"],
}

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Richtet die Select-Plattform ein."""
    data = hass.data[DOMAIN][entry.entry_id]
    local_coordinator = data["local"]

    entities = []

    # Hole Konfiguration
    beaam_config = local_coordinator.data.get("config", {}) if local_coordinator.data else {}
    
    if beaam_config:
        things = beaam_config.get("things", {})
        
        for thing_id, thing_data in things.items():
            if not thing_data: continue

            thing_type = thing_data.get("type")
            datapoints = thing_data.get("dataPoints", {})

            for dp_id, dp_data in datapoints.items():
                if not dp_data: continue

                # Suche nach steuerbaren Text-Werten ("controllable": true, dataType: STRING)
                dtype = dp_data.get("dataType")
                controllable = dp_data.get("controllable", False)
                key = dp_data.get("key")
                
                # Wir erstellen nur Select-Entitäten, wenn wir die Optionen kennen
                if dtype == "STRING" and controllable and key in KNOWN_OPTIONS:
                    entities.append(NeoomLocalSelect(
                        local_coordinator, 
                        thing_id, 
                        thing_data, 
                        dp_id, 
                        dp_data,
                        KNOWN_OPTIONS[key]
                    ))

    async_add_entities(entities)


class NeoomLocalSelect(CoordinatorEntity, SelectEntity):
    """Repräsentation einer Auswahl-Entität (Dropdown)."""

    def __init__(self, coordinator, thing_id, thing_data, dp_id, dp_data, options):
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type = thing_data.get("type", "Unknown")
        self._dp_id = dp_id
        self._key = dp_data.get("key")
        self._attr_options = options # Die Liste der erlaubten Werte
        
        friendly_thing_name = self._thing_type.replace("_", " ").title()
        friendly_dp_name = self._key.replace("_", " ").title()
        self._attr_name = f"{friendly_thing_name} {friendly_dp_name}"
        self._attr_unique_id = f"{thing_id}_{dp_id}_select"
        self._attr_icon = "mdi:form-select"

    @property
    def current_option(self):
        """Gibt die aktuell gewählte Option zurück."""
        if not self.coordinator.data: return None
        
        state_map = self.coordinator.data.get("states", {})
        data_point = state_map.get(self._dp_id)
        
        if data_point:
            val = data_point.get("value")
            if val in self._attr_options:
                return val
            # Falls der aktuelle Wert nicht in unserer Liste ist, geben wir ihn trotzdem zurück (oder None)
            return val
        return None

    async def async_select_option(self, option: str) -> None:
        """Sendet die gewählte Option an die API."""
        LOGGER.info(f"Setze {self._key} auf {option}")
        await self.coordinator.async_send_command(self._thing_id, self._key, option)

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