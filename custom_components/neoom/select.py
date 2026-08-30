"""Select Plattform für neoom AI.

Diese Datei definiert Dropdown-Menüs (Select-Entitäten),
mit denen vordefinierte Text-Werte (z.B. Betriebsmodi) an das 
lokale BEAAM Gateway gesendet werden können.
"""

from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import NeoomLocalCoordinator
from .helpers import get_friendly_thing_name

# Bekannte Optionen für spezifische Schlüssel.
# Da die API uns leider keine Liste der erlaubten Werte in der Konfiguration 
# mitliefert, müssen wir diese hier ("hardcoded") definieren. 
# Neue umschaltbare Parameter müssen hier ergänzt werden.
KNOWN_OPTIONS: Dict[str, List[str]] = {
    "PHASE_SWITCHING_MODE": ["automatic", "force_1_phase", "force_3_phase"],
    "OPERATING_MODE_SG_READY": ["1", "2", "3", "4"],
}

# Bekannte Optionen für Einstellungen (Settings)
KNOWN_SETTINGS_OPTIONS: Dict[str, List[str]] = {
    "OPERATING_MODE_EMS": ["griid_controlled", "excess_consumption", "fast_charging", "device_controlled"],
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[SelectEntity]], None],
) -> None:
    """Richtet die Select-Plattform basierend auf dem Konfigurationseintrag ein.
    
    Durchsucht die BEAAM Konfiguration nach steuerbaren Text-Datenpunkten und Einstellungen,
    und überwacht spätere Coordinator-Updates für neu erkannte Entitäten.
    """
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    local_coordinator: NeoomLocalCoordinator = data["local"]

    known_select_ids: set[str] = set()

    @callback
    def _async_check_entities() -> None:
        """Prüft auf neu verfügbare Datenpunkte/Einstellungen und legt Select-Entitäten an."""
        if not local_coordinator.data:
            return

        # Hole die statische Konfiguration
        beaam_config = local_coordinator.data.get("config", {})
        if not beaam_config or not isinstance(beaam_config, dict):
            return

        things = beaam_config.get("things", {})
        if not isinstance(things, dict):
            return

        new_entities: List[SelectEntity] = []

        # 1. Datenpunkte durchsuchen
        for thing_id, thing_data in things.items():
            if not thing_data or not isinstance(thing_data, dict):
                continue

            datapoints: Dict[str, Any] = thing_data.get("dataPoints", {})
            if not isinstance(datapoints, dict):
                continue

            for dp_id, dp_data in datapoints.items():
                if not dp_data or not isinstance(dp_data, dict):
                    continue

                # Suche nach Text-Werten (dataType: STRING) in KNOWN_OPTIONS
                dtype: str = dp_data.get("dataType", "")
                controllable: bool = dp_data.get("controllable", False)
                key: str = dp_data.get("key", "")
                
                if dtype == "STRING" and key in KNOWN_OPTIONS:
                    if controllable:
                        uid = f"{thing_id}_{dp_id}_select"
                        if uid not in known_select_ids:
                            known_select_ids.add(uid)
                            new_entities.append(
                                NeoomLocalSelect(
                                    coordinator=local_coordinator, 
                                    thing_id=thing_id, 
                                    thing_data=thing_data, 
                                    dp_id=dp_id, 
                                    dp_data=dp_data,
                                    options=KNOWN_OPTIONS[key]
                                )
                            )
                    else:
                        # Wenn nicht steuerbar (z.B. Generic Device), legen wir eine Ingest-Entität an (standardmäßig deaktiviert)
                        uid = f"{thing_id}_{dp_id}_ingest_select"
                        if uid not in known_select_ids:
                            known_select_ids.add(uid)
                            new_entities.append(
                                NeoomIngestSelect(
                                    coordinator=local_coordinator, 
                                    thing_id=thing_id, 
                                    thing_data=thing_data, 
                                    dp_id=dp_id, 
                                    dp_data=dp_data,
                                    options=KNOWN_OPTIONS[key]
                                )
                            )

        # 2. Einstellungen (Settings) dynamisch durchsuchen
        settings_map: Dict[str, Dict[str, Any]] = local_coordinator.data.get("settings", {})
        if settings_map and isinstance(settings_map, dict):
            for thing_id, thing_data in things.items():
                if not thing_data or not isinstance(thing_data, dict):
                    continue

                thing_settings = settings_map.get(thing_id)
                if not thing_settings or not isinstance(thing_settings, dict):
                    continue

                for key, val in thing_settings.items():
                    if key in KNOWN_SETTINGS_OPTIONS:
                        thing_type = thing_data.get("type") or ""
                        options = KNOWN_SETTINGS_OPTIONS[key]
                        if key == "OPERATING_MODE_EMS":
                            if thing_type == "BATTERY":
                                options = ["griid_controlled", "excess_consumption"]
                            elif thing_type == "CHARGING_POINT_AC":
                                options = ["griid_controlled", "excess_consumption", "fast_charging", "device_controlled"]
                            elif thing_type == "HEAT_PUMP" or thing_type.startswith("HEAT_PUMP"):
                                options = ["excess_consumption", "device_controlled"]

                        uid = f"{thing_id}_{key}_select"
                        if uid not in known_select_ids:
                            known_select_ids.add(uid)
                            new_entities.append(
                                NeoomSettingSelect(
                                    coordinator=local_coordinator,
                                    thing_id=thing_id,
                                    thing_data=thing_data,
                                    setting_key=key,
                                    options=options,
                                )
                            )

        if new_entities:
            async_add_entities(new_entities)

    _async_check_entities()
    entry.async_on_unload(
        local_coordinator.async_add_listener(_async_check_entities)
    )


class NeoomLocalSelect(CoordinatorEntity, SelectEntity):
    """Repräsentation einer Auswahl-Entität (Dropdown-Menü)."""

    _attr_has_entity_name = True

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
        
        beaam_config = coordinator.data.get("config", {}) if coordinator.data else {}
        self._friendly_thing_name = get_friendly_thing_name(beaam_config, thing_id, self._thing_type)
        friendly_dp_name = self._key.replace("_", " ").title()
        
        self._attr_name = friendly_dp_name
        self._attr_unique_id = f"{thing_id}_{dp_id}_select"
        self._attr_translation_key = self._key.lower()
        self._attr_icon = "mdi:form-select"

    @property
    def current_option(self) -> Optional[str]:
        """Gibt die aktuell im Gateway gesetzte (oder vom Gateway empfangene) Option zurück."""
        if not self.coordinator.data:
            return None
        
        state_map: Dict[str, Any] = self.coordinator.data.get("states", {})
        data_point: Optional[Dict[str, Any]] = state_map.get(self._dp_id) or state_map.get(f"{self._thing_id}_{self._key}")
        
        if data_point:
            val = data_point.get("value")
            
            # Überprüfe, ob der Empfangene Wert in unserer Optionen-Liste ist.
            if val is not None:
                val_str = str(val).lower()
                
                # Spezielle Zuordnung für rohe SG-Ready Werte aus Modbus/Gateway
                if self._key == "OPERATING_MODE_SG_READY":
                    if val_str in ["65636", "0", "100", "2"]:
                        return "2"
                    elif val_str == "1":
                        return "1"
                    elif val_str == "3":
                        return "3"
                    elif val_str == "4":
                        return "4"

                for opt in self._attr_options:
                    if opt.lower() == val_str:
                        return opt
                return str(val)
        return None

    async def async_select_option(self, option: str) -> None:
        """Wird aufgerufen, wenn der Benutzer einen neuen Eintrag im Dropdown wählt.
        
        Sendet den neuen Text-Wert via API an das BEAAM Gateway.
        """
        api_value = option.upper()
        LOGGER.info("Setze %s auf %s (API: %s)", self._key, option, api_value)
        await self.coordinator.async_send_command(self._thing_id, self._key, api_value)

    @property
    def device_info(self) -> DeviceInfo:
        """Verknüpfung der Entität mit dem physischen Gerät (Thing) im Device Registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_id)},
            name=f"neoom {getattr(self, '_friendly_thing_name', self._thing_type)}",
            manufacturer="neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway"),
        )


class NeoomIngestSelect(NeoomLocalSelect):
    """Repräsentation einer Ingest-Auswahl-Entität für nicht-steuerbare Text-Werte.
    
    Ermöglicht das Senden von vordefinierten Werten per State-Ingest an das BEAAM Gateway.
    Standardmäßig deaktiviert.
    """

    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        dp_id: str,
        dp_data: Dict[str, Any],
        options: List[str],
    ) -> None:
        """Initialisiert die Ingest-Select-Entität."""
        super().__init__(coordinator, thing_id, thing_data, dp_id, dp_data, options)
        self._attr_unique_id = f"{thing_id}_{dp_id}_ingest_select"
        friendly_dp_name = self._key.replace("_", " ").title()
        self._attr_name = f"{friendly_dp_name} (Ingest)"

    async def async_select_option(self, option: str) -> None:
        """Wird aufgerufen, wenn der Benutzer einen Wert im Dropdown wählt.
        
        Sendet den Wert via State-Ingest an das BEAAM Gateway.
        """
        api_value = option.upper()
        LOGGER.info("Sende State Ingest für %s auf %s (API: %s)", self._key, option, api_value)
        await self.coordinator.async_ingest_state(self._thing_id, self._key, api_value)


class NeoomSettingSelect(CoordinatorEntity, SelectEntity):
    """Repräsentation einer Einstellungs-Auswahl-Entität (Dropdown-Menü für Settings)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        setting_key: str,
        options: List[str],
    ) -> None:
        """Initialisiert die Einstellungs-Select-Entität."""
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type: str = thing_data.get("type", "Unknown")
        self._setting_key = setting_key
        self._attr_options: List[str] = options
        
        beaam_config = coordinator.data.get("config", {}) if coordinator.data else {}
        self._friendly_thing_name = get_friendly_thing_name(beaam_config, thing_id, self._thing_type)
        
        friendly_dp_name = setting_key.replace("_", " ").title()
        self._attr_name = friendly_dp_name
        self._attr_translation_key = setting_key.lower()
        self._attr_unique_id = f"{thing_id}_{setting_key}_select"
        self._attr_icon = "mdi:form-select"

    @property
    def current_option(self) -> Optional[str]:
        """Gibt die aktuell im Gateway gesetzte Option zurück."""
        if not self.coordinator.data:
            return None
        
        settings_map = self.coordinator.data.get("settings", {})
        thing_settings = settings_map.get(self._thing_id, {})
        val = thing_settings.get(self._setting_key)
        
        if val is not None:
            val_str = str(val).lower()
            # Map grid_controlled/griid_controlled fallback if necessary
            if val_str == "grid_controlled" and "griid_controlled" in self._attr_options:
                return "griid_controlled"
            return val_str
        return None

    async def async_select_option(self, option: str) -> None:
        """Wird aufgerufen, wenn der Benutzer einen neuen Eintrag im Dropdown wählt.
        
        Sendet den neuen Einstellwert an das BEAAM Gateway.
        """
        api_value = option.upper()
        LOGGER.info("Setze Einstellwert %s am Gerät %s auf %s (API: %s)", self._setting_key, self._thing_id, option, api_value)
        await self.coordinator.async_send_setting(self._thing_id, self._setting_key, api_value)

    @property
    def device_info(self) -> DeviceInfo:
        """Verknüpfung der Entität mit dem physischen Gerät (Thing) im Device Registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_id)},
            name=f"neoom {getattr(self, '_friendly_thing_name', self._thing_type)}",
            manufacturer="neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway"),
        )
