"""Time Plattform für neoom AI.

Diese Datei definiert Entitäten zur Uhrzeit-Eingabe,
mit denen Einstellungen am lokalen BEAAM Gateway vorgenommen werden können
(z. B. die Abfahrtszeit für das intelligente Laden).
"""

from datetime import time
import datetime
from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import NeoomLocalCoordinator
from .helpers import get_friendly_thing_name

# Bekannte Uhrzeit-Einstellungen
TIME_SETTINGS = {
    "GRIID_EV_DEPARTURE_TIME": "Departure time",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[TimeEntity]], None],
) -> None:
    """Richtet die Time-Plattform basierend auf dem Konfigurationseintrag ein.
    
    Erstellt Time-Entitäten für alle erkannten Uhrzeit-Einstellungen der Things
    und überwacht spätere Coordinator-Updates für neu erkannte Entitäten.
    """
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    local_coordinator: NeoomLocalCoordinator = data["local"]

    known_time_ids: set[str] = set()

    @callback
    def _async_check_entities() -> None:
        """Prüft auf neu verfügbare Einstellungen und legt entsprechende Time-Entitäten an."""
        if not local_coordinator.data:
            return

        beaam_config = local_coordinator.data.get("config", {})
        settings_map = local_coordinator.data.get("settings", {})

        if not beaam_config or not settings_map:
            return

        things = beaam_config.get("things", {})
        if not isinstance(things, dict):
            return

        new_entities: List[TimeEntity] = []

        for thing_id, thing_data in things.items():
            if not thing_data or not isinstance(thing_data, dict):
                continue

            thing_settings = settings_map.get(thing_id)
            if not thing_settings or not isinstance(thing_settings, dict):
                continue

            for key, val in thing_settings.items():
                # Prüfe, ob es eine bekannte Uhrzeit-Einstellung ist,
                # oder der Schlüssel mit _TIME endet und der Wert im Format HH:MM vorliegt
                is_time = key in TIME_SETTINGS
                if not is_time and key.endswith("_TIME") and isinstance(val, str) and ":" in val:
                    is_time = True

                if is_time:
                    unique_id = f"{thing_id}_{key}_time"
                    if unique_id not in known_time_ids:
                        known_time_ids.add(unique_id)
                        new_entities.append(
                            NeoomSettingTime(
                                coordinator=local_coordinator,
                                thing_id=thing_id,
                                thing_data=thing_data,
                                setting_key=key,
                            )
                        )

        if new_entities:
            async_add_entities(new_entities)

    _async_check_entities()
    entry.async_on_unload(
        local_coordinator.async_add_listener(_async_check_entities)
    )


class NeoomSettingTime(CoordinatorEntity, TimeEntity):
    """Repräsentation einer steuerbaren Einstellungs-Uhrzeit (Time Entity)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        setting_key: str,
    ) -> None:
        """Initialisiert die Time-Entität."""
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type: str = thing_data.get("type", "Unknown")
        self._setting_key = setting_key
        
        beaam_config = coordinator.data.get("config", {}) if coordinator.data else {}
        self._friendly_thing_name = get_friendly_thing_name(beaam_config, thing_id, self._thing_type)
        
        friendly_dp_name = TIME_SETTINGS.get(setting_key, setting_key.replace("_", " ").title())
        self._attr_name = friendly_dp_name
        self._attr_translation_key = setting_key.lower()
        self._attr_unique_id = f"{thing_id}_{setting_key}_time"
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> Optional[time]:
        """Gibt die aktuell im Gateway gesetzte Uhrzeit zurück."""
        if not self.coordinator.data:
            return None
        
        settings_map = self.coordinator.data.get("settings", {})
        thing_settings = settings_map.get(self._thing_id, {})
        val = thing_settings.get(self._setting_key)
        
        if val is not None:
            val_str = str(val)
            try:
                # Erwartetes Format: "HH:MM" oder "HH:MM:SS"
                parts = [int(p) for p in val_str.split(":")]
                if len(parts) >= 2:
                    return time(hour=parts[0], minute=parts[1])
            except (ValueError, IndexError):
                LOGGER.error("Ungültiges Zeitformat für Einstellung %s: %s", self._setting_key, val)
        return None

    async def async_set_value(self, value: time) -> None:
        """Wird aufgerufen, wenn der Benutzer einen neuen Uhrzeitwert einstellt."""
        # Konvertiere time Objekt in das API Format "HH:MM"
        api_value = value.strftime("%H:%M")
        LOGGER.info("Setze Uhrzeit-Einstellung %s am Gerät %s auf %s", self._setting_key, self._thing_id, api_value)
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
