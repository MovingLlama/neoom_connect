"""Switch Plattform für neoom AI.

Diese Datei definiert Schalter (Switch-Entitäten) für boolesche Einstellparameter
des lokalen BEAAM Gateways (z.B. Erlaubnis zum Laden/Entladen der Batterie aus dem Netz).
"""

from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import NeoomLocalCoordinator
from .helpers import get_friendly_thing_name

# Bekannte boolesche Einstellungen und deren freundliche Bezeichnungen
BOOLEAN_SETTINGS = {
    "BATTERY_CHARGE_FROM_GRID_ALLOWED": "Allow battery charging from grid",
    "BATTERY_DISCHARGE_TO_GRID_ALLOWED": "Allow battery discharging to grid",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[SwitchEntity]], None],
) -> None:
    """Richtet die Switch-Plattform basierend auf dem Konfigurationseintrag ein.
    
    Erstellt Switch-Entitäten für alle erkannten booleschen Einstellungen der Things
    und überwacht spätere Coordinator-Updates für neu erkannte Entitäten.
    """
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    local_coordinator: NeoomLocalCoordinator = data["local"]

    known_switch_ids: set[str] = set()

    @callback
    def _async_check_entities() -> None:
        """Prüft auf neu verfügbare Einstellungen und legt entsprechende Switch-Entitäten an."""
        if not local_coordinator.data:
            return

        beaam_config = local_coordinator.data.get("config", {})
        settings_map = local_coordinator.data.get("settings", {})

        if not beaam_config or not settings_map:
            return

        things = beaam_config.get("things", {})
        if not isinstance(things, dict):
            return

        new_entities: List[SwitchEntity] = []

        for thing_id, thing_data in things.items():
            if not thing_data or not isinstance(thing_data, dict):
                continue

            thing_settings = settings_map.get(thing_id)
            if not thing_settings or not isinstance(thing_settings, dict):
                continue

            for key, val in thing_settings.items():
                # Prüfe, ob es eine bekannte boolesche Einstellung ist,
                # oder ob der Wert "true"/"false" ist (case-insensitive)
                is_bool = key in BOOLEAN_SETTINGS
                if not is_bool and isinstance(val, str) and val.lower() in ["true", "false"]:
                    is_bool = True

                if is_bool:
                    unique_id = f"{thing_id}_{key}_switch"
                    if unique_id not in known_switch_ids:
                        known_switch_ids.add(unique_id)
                        new_entities.append(
                            NeoomSettingSwitch(
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


class NeoomSettingSwitch(CoordinatorEntity, SwitchEntity):
    """Repräsentation eines steuerbaren Einstellungs-Schalters."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        setting_key: str,
    ) -> None:
        """Initialisiert die Switch-Entität."""
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type: str = thing_data.get("type", "Unknown")
        self._setting_key = setting_key
        
        beaam_config = coordinator.data.get("config", {}) if coordinator.data else {}
        self._friendly_thing_name = get_friendly_thing_name(beaam_config, thing_id, self._thing_type)
        
        friendly_dp_name = BOOLEAN_SETTINGS.get(setting_key, setting_key.replace("_", " ").title())
        self._attr_name = friendly_dp_name
        self._attr_translation_key = setting_key.lower()
        self._attr_unique_id = f"{thing_id}_{setting_key}_switch"
        self._attr_icon = "mdi:toggle-switch"

    @property
    def is_on(self) -> Optional[bool]:
        """Gibt True zurück, wenn der Schalter eingeschaltet ist."""
        if not self.coordinator.data:
            return None
        
        settings_map = self.coordinator.data.get("settings", {})
        thing_settings = settings_map.get(self._thing_id, {})
        val = thing_settings.get(self._setting_key)
        
        if val is not None:
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() == "true"
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Schaltet den Schalter ein."""
        LOGGER.info("Schalte Einstellung %s am Gerät %s EIN", self._setting_key, self._thing_id)
        # Sende den String "true" an die API
        await self.coordinator.async_send_setting(self._thing_id, self._setting_key, "true")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Schaltet den Schalter aus."""
        LOGGER.info("Schalte Einstellung %s am Gerät %s AUS", self._setting_key, self._thing_id)
        await self.coordinator.async_send_setting(self._thing_id, self._setting_key, "false")

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
