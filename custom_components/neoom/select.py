"""Select Plattform für neoom AI.

Diese Datei definiert Dropdown-Menüs (Select-Entitäten),
mit denen vordefinierte Text-Werte (z.B. Betriebsmodi) an das 
lokale BEAAM Gateway gesendet werden können.
"""

from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import NeoomLocalCoordinator

# Bekannte Optionen für spezifische Schlüssel.
# Da die API uns leider keine Liste der erlaubten Werte in der Konfiguration 
# mitliefert, müssen wir diese hier ("hardcoded") definieren. 
# Neue umschaltbare Parameter müssen hier ergänzt werden.
KNOWN_OPTIONS: Dict[str, List[str]] = {
    "PHASE_SWITCHING_MODE": ["AUTO", "FORCE_1_PHASE", "FORCE_3_PHASE"],
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[SelectEntity]], None],
) -> None:
    """Richtet die Select-Plattform basierend auf dem Konfigurationseintrag ein.
    
    Durchsucht die BEAAM Konfiguration nach steuerbaren Text-Datenpunkten,
    für die wir eine vordefinierte Liste an Optionen kennen.
    """
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    local_coordinator: NeoomLocalCoordinator = data["local"]

    entities: List[SelectEntity] = []

    # Hole die statische Konfiguration
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

                # Suche nach steuerbaren Text-Werten ("controllable": true, dataType: STRING)
                dtype: str = dp_data.get("dataType", "")
                controllable: bool = dp_data.get("controllable", False)
                key: str = dp_data.get("key", "")
                
                # Wir erstellen nur Select-Entitäten für Schlüssel, deren Optionen wir kennen
                if dtype == "STRING" and controllable and key in KNOWN_OPTIONS:
                    entities.append(
                        NeoomLocalSelect(
                            coordinator=local_coordinator, 
                            thing_id=thing_id, 
                            thing_data=thing_data, 
                            dp_id=dp_id, 
                            dp_data=dp_data,
                            options=KNOWN_OPTIONS[key]
                        )
                    )

    # Entitäten in Home Assistant registrieren
    async_add_entities(entities)


class NeoomLocalSelect(CoordinatorEntity, SelectEntity):
    """Repräsentation einer Auswahl-Entität (Dropdown-Menü)."""

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        dp_id: str,
        dp_data: Dict[str, Any],
        options: List[str],
    ) -> None:
        """Initialisiert die Select-Entität."""
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type: str = thing_data.get("type", "Unknown")
        self._dp_id = dp_id
        self._key: str = dp_data.get("key", "")
        
        # Weist Home Assistant die verfügbaren Dropdown-Optionen zu
        self._attr_options: List[str] = options
        
        # Mache den Namen benutzerfreundlich
        friendly_thing_name = self._thing_type.replace("_", " ").title()
        friendly_dp_name = self._key.replace("_", " ").title()
        
        self._attr_name = f"{friendly_thing_name} {friendly_dp_name}"
        self._attr_unique_id = f"{thing_id}_{dp_id}_select"
        self._attr_icon = "mdi:form-select"

    @property
    def current_option(self) -> Optional[str]:
        """Gibt die aktuell im Gateway gesetzte (oder vom Gateway empfangene) Option zurück."""
        if not self.coordinator.data:
            return None
        
        state_map: Dict[str, Any] = self.coordinator.data.get("states", {})
        data_point: Optional[Dict[str, Any]] = state_map.get(self._dp_id)
        
        if data_point:
            val = data_point.get("value")
            
            # Überprüfe, ob der Empfangene Wert in unserer Optionen-Liste ist.
            # Aber auch wenn nicht, geben wir ihn zurück, um Inkonsistenzen zu signalisieren.
            if val is not None:
                return str(val)
        return None

    async def async_select_option(self, option: str) -> None:
        """Wird aufgerufen, wenn der Benutzer einen neuen Eintrag im Dropdown wählt.
        
        Sendet den neuen Text-Wert via API an das BEAAM Gateway.
        """
        LOGGER.info("Setze %s auf %s", self._key, option)
        await self.coordinator.async_send_command(self._thing_id, self._key, option)

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
