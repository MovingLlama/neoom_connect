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
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import NeoomLocalCoordinator
from .helpers import get_friendly_thing_name

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
    Konfiguration nach steuerbaren, numerischen Datenpunkten durchsucht und auf spätere Updates reagiert.
    """
    
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    # Number-Entitäten steuern nur das lokale Gateway, daher brauchen wir nur den lokalen Coordinator
    local_coordinator: NeoomLocalCoordinator = data["local"]

    known_number_ids: set[str] = set()

    @callback
    def _async_check_entities() -> None:
        """Prüft auf neu verfügbare Datenpunkte/Einstellungen und legt entsprechende Number-Entitäten an."""
        if not local_coordinator.data:
            return

        # Hole die statische Konfiguration (enthält alle bekannten Geräte)
        beaam_config = local_coordinator.data.get("config", {})
        if not beaam_config or not isinstance(beaam_config, dict):
            return

        things = beaam_config.get("things", {})
        if not isinstance(things, dict):
            return

        new_entities: List[NumberEntity] = []

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

                # Wir interessieren uns nur für steuerbare ("controllable": true) Zahlen ("NUMBER")
                dtype: str = dp_data.get("dataType", "")
                controllable: bool = dp_data.get("controllable", False)
                key: str = dp_data.get("key", "")
                
                # Filtern von unerwünschten Schlüsseln
                if dtype == "NUMBER" and key not in IGNORE_KEYS:
                    if controllable:
                        uid = f"{thing_id}_{dp_id}_number"
                        if uid not in known_number_ids:
                            known_number_ids.add(uid)
                            new_entities.append(
                                NeoomLocalNumber(
                                    coordinator=local_coordinator, 
                                    thing_id=thing_id, 
                                    thing_data=thing_data, 
                                    dp_id=dp_id, 
                                    dp_data=dp_data
                                )
                            )
                    else:
                        # Wenn nicht steuerbar, legen wir eine Ingest-Entität an (standardmäßig deaktiviert)
                        uid = f"{thing_id}_{dp_id}_ingest"
                        if uid not in known_number_ids:
                            known_number_ids.add(uid)
                            new_entities.append(
                                NeoomIngestNumber(
                                    coordinator=local_coordinator, 
                                    thing_id=thing_id, 
                                    thing_data=thing_data, 
                                    dp_id=dp_id, 
                                    dp_data=dp_data
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
                    # Erkennt numerische Einstellungen
                    is_num = False
                    if "ENERGY" in key or "POWER" in key:
                        is_num = True
                    elif isinstance(val, (int, float)):
                        is_num = True
                    elif isinstance(val, str):
                        try:
                            float(val)
                            if ":" not in val and ("." in val or val.isdigit()):
                                is_num = True
                        except (ValueError, TypeError):
                            pass
                    
                    if is_num:
                        uid = f"{thing_id}_{key}_number"
                        if uid not in known_number_ids:
                            known_number_ids.add(uid)
                            new_entities.append(
                                NeoomSettingNumber(
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
        
        beaam_config = coordinator.data.get("config", {}) if coordinator.data else {}
        self._friendly_thing_name = get_friendly_thing_name(beaam_config, thing_id, self._thing_type)
        friendly_dp_name = self._key.replace("_", " ").title()
        
        self._attr_name = f"{self._friendly_thing_name} {friendly_dp_name}"
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
        elif self._uom_raw in ["Wh", "kWh"]:
            # Energiewerte in kWh für HA (wird von Wh in der API konvertiert)
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_device_class = NumberDeviceClass.ENERGY
            self._attr_native_min_value = 0
            self._attr_native_max_value = 1000000
            self._attr_native_step = 0.1
            self._attr_mode = NumberMode.BOX
        elif self._uom_raw == "A":
            # Stromstärke (z.B. Ladestromgrenzen)
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
            self._attr_device_class = NumberDeviceClass.CURRENT
            self._attr_native_min_value = 0
            self._attr_native_max_value = 63
            self._attr_native_step = 1
            self._attr_mode = NumberMode.BOX
        elif self._uom_raw in ["C", "°C"]:
            # Temperaturwerte
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100
            self._attr_native_step = 0.5
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
        data_point: Optional[Dict[str, Any]] = state_map.get(self._dp_id) or state_map.get(f"{self._thing_id}_{self._key}")
        
        if data_point:
            val = data_point.get("value")
            if val is not None:
                try:
                    float_val = float(val)
                    # Konvertiere Wh der API in kWh für Home Assistant
                    if self._uom_raw == "Wh":
                        return float_val / 1000.0
                    return float_val
                except (ValueError, TypeError):
                    pass
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Wird aufgerufen, wenn der Benutzer einen neuen Wert in der HA-Oberfläche eingibt.
        
        Sendet den neuen Wert via API an das BEAAM Gateway.
        """
        api_value = value
        # Konvertiere die kWh aus HA zurück in Wh für die API
        if self._uom_raw == "Wh":
            api_value = value * 1000.0
            
        LOGGER.info("Setze %s auf %s", self._key, api_value)
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

class NeoomIngestNumber(NeoomLocalNumber):
    """Repräsentation eines Ingest-Werts (Number Entity) für Sensordaten.
    
    Ermöglicht das Schreiben (Ingest) von Werten für nicht-steuerbare Datenpunkte
    (z.B. für Generic Devices). Standardmäßig deaktiviert.
    """

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        dp_id: str,
        dp_data: Dict[str, Any],
    ) -> None:
        """Initialisiert die Ingest Number-Entität."""
        super().__init__(coordinator, thing_id, thing_data, dp_id, dp_data)
        
        # Ändere die eindeutige ID, damit sie nicht mit dem normalen Sensor kollidiert
        self._attr_unique_id = f"{thing_id}_{dp_id}_ingest"
        
        # Markiere den Namen als (Ingest), um ihn in der UI von normalen Werten zu unterscheiden
        self._attr_name = f"{self._attr_name} (Ingest)"

    async def async_set_native_value(self, value: float) -> None:
        """Wird aufgerufen, wenn der Benutzer einen neuen Wert eingibt.
        
        Sendet den neuen Wert via State-Ingest an das BEAAM Gateway.
        """
        api_value = value
        # Konvertiere die kWh aus HA zurück in Wh für die API
        if self._uom_raw == "Wh":
            api_value = value * 1000.0
            
        LOGGER.info("Sende State Ingest für %s auf %s", self._key, api_value)
        await self.coordinator.async_ingest_state(self._thing_id, self._key, api_value)


class NeoomSettingNumber(CoordinatorEntity, NumberEntity):
    """Repräsentation einer Einstellungs-Zahleneingabe (Slider oder Box für Settings)."""

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        setting_key: str,
    ) -> None:
        """Initialisiert die Einstellungs-Number-Entität."""
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type: str = thing_data.get("type", "Unknown")
        self._setting_key = setting_key
        
        beaam_config = coordinator.data.get("config", {}) if coordinator.data else {}
        self._friendly_thing_name = get_friendly_thing_name(beaam_config, thing_id, self._thing_type)
        
        if setting_key == "GRIID_CHARGING_ENERGY":
            friendly_dp_name = "Lademenge"
        else:
            friendly_dp_name = setting_key.replace("_", " ").title()
        
        self._attr_name = f"{self._friendly_thing_name} {friendly_dp_name}"
        self._attr_unique_id = f"{thing_id}_{setting_key}_number"
        
        # Spezifische Konfiguration für bekannte nummerische Einstellungen
        if "ENERGY" in setting_key:
            # Energiewerte in kWh für HA (wird von Wh in der API konvertiert)
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_device_class = NumberDeviceClass.ENERGY
            self._attr_native_min_value = 0
            self._attr_native_max_value = 1000
            self._attr_native_step = 0.1
            self._attr_mode = NumberMode.BOX
        else:
            self._attr_native_min_value = 0
            self._attr_native_max_value = 1000000
            self._attr_native_step = 1
            self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> Optional[float]:
        """Gibt den aktuellen Wert aus dem Koordinator zurück."""
        if not self.coordinator.data:
            return None
        
        settings_map = self.coordinator.data.get("settings", {})
        thing_settings = settings_map.get(self._thing_id, {})
        val = thing_settings.get(self._setting_key)
        
        if val is not None:
            try:
                float_val = float(val)
                if "ENERGY" in self._setting_key:
                    return float_val / 1000.0
                return float_val
            except ValueError:
                pass
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Wird aufgerufen, wenn der Benutzer einen neuen Wert in der HA-Oberfläche eingibt."""
        api_value = value
        if "ENERGY" in self._setting_key:
            api_value = value * 1000.0
            
        LOGGER.info("Setze Einstellung %s am Gerät %s auf %s", self._setting_key, self._thing_id, api_value)
        # Sende den neuen Einstellwert an das BEAAM Gateway.
        # Die settings API akzeptiert oneOf string/number/boolean. Senden wir es als float/int.
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
