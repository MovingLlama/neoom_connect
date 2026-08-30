"""Sensor Plattform für neoom AI.

Diese Datei definiert die "nur-lesen" Sensoren, die Daten aus der neoom AI Cloud 
und dem lokalen BEAAM Gateway in Home Assistant anzeigen.
"""

from typing import Any, Callable, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NeoomCloudCoordinator, NeoomLocalCoordinator
from .helpers import get_friendly_thing_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[SensorEntity]], None],
) -> None:
    """Richtet die Sensor-Plattform basierend auf dem Konfigurationseintrag ein.
    
    Diese Methode wird von Home Assistant aufgerufen, um Entitäten zu registrieren.
    """
    
    # Hole die Koordinatoren, die wir in __init__.py gespeichert haben
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    cloud_coordinator: NeoomCloudCoordinator = data["cloud"]
    local_coordinator: NeoomLocalCoordinator = data["local"]

    entities: List[SensorEntity] = []

    # --- CLOUD SENSOREN ---
    # Diese Sensoren werden manuell erstellt, da wir wissen, 
    # welche Tarifdaten die Cloud standardmäßig zurückgibt.
    entities.append(
        NeoomCloudSensor(
            coordinator=cloud_coordinator,
            key="electricity_price",
            name="Electricity Price",
            unit="ct/kWh",
            icon="mdi:currency-eur",
            data_path="site",
        )
    )
    entities.append(
        NeoomCloudSensor(
            coordinator=cloud_coordinator,
            key="feed_in_tariff",
            name="Feed-in Tariff",
            unit="ct/kWh",
            icon="mdi:cash-plus",
            data_path="site",
        )
    )
    entities.append(
        NeoomCloudSensor(
            coordinator=cloud_coordinator,
            key="gateways_online_state",
            name="Gateway Status",
            unit=None,
            icon="mdi:router-network",
            data_path="flow",
        )
    )

    async_add_entities(entities)

    # --- LOKALE SENSOREN (Dynamisch) ---
    # Da das BEAAM Gateway je nach Standort unterschiedliche Geräte 
    # (Wechselrichter, Speicher, E-Ladestation) angebunden hat,
    # generieren wir diese Sensoren dynamisch anhand der BEAAM Konfiguration
    # und überwachen spätere Updates.
    known_sensor_ids: set[str] = set()

    @callback
    def _async_check_entities() -> None:
        """Prüft auf neu verfügbare Datenpunkte und legt Sensor-Entitäten an."""
        if not local_coordinator.data:
            return

        beaam_config = local_coordinator.data.get("config", {})
        if not beaam_config or not isinstance(beaam_config, dict):
            return

        things = beaam_config.get("things", {})
        if not isinstance(things, dict):
            return

        new_entities: List[SensorEntity] = []

        for thing_id, thing_data in things.items():
            if not thing_data or not isinstance(thing_data, dict):
                continue

            datapoints: Dict[str, Any] = thing_data.get("dataPoints", {})
            if not isinstance(datapoints, dict):
                continue

            for dp_id, dp_data in datapoints.items():
                if not dp_data or not isinstance(dp_data, dict):
                    continue

                dtype: str = dp_data.get("dataType", "")

                # Wir erstellen Sensoren für Zahlen (Leistung, Prozente) und Strings (Betriebsmodi)
                if dtype in ["NUMBER", "STRING"]:
                    unique_id = f"{thing_id}_{dp_id}"
                    if unique_id not in known_sensor_ids:
                        known_sensor_ids.add(unique_id)
                        new_entities.append(
                            NeoomLocalSensor(
                                coordinator=local_coordinator,
                                thing_id=thing_id,
                                thing_data=thing_data,
                                dp_id=dp_id,
                                dp_data=dp_data,
                            )
                        )

        if new_entities:
            async_add_entities(new_entities)

    _async_check_entities()
    entry.async_on_unload(
        local_coordinator.async_add_listener(_async_check_entities)
    )


class NeoomCloudSensor(CoordinatorEntity, SensorEntity):
    """Repräsentation eines generischen Cloud-Sensors (z.B. Tarifdaten).
    
    Erbt von CoordinatorEntity, damit der Sensor automatisch aktualisiert wird,
    wenn der Koordinator neue Daten aus dem Internet lädt.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NeoomCloudCoordinator,
        key: str,
        name: str,
        unit: Optional[str],
        icon: str,
        data_path: str = "site",
    ) -> None:
        """Initialisiert den Cloud-Sensor."""
        super().__init__(coordinator)
        self._key = key
        self._name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._data_path = data_path
        self._attr_translation_key = key
        self._attr_name = name
        
        # Eindeutige ID ist entscheidend für Home Assistant, um die Entität wiederzuerkennen
        self._attr_unique_id = f"{coordinator.site_id}_{key}"

    @property
    def native_value(self) -> Any:
        """Gibt den aktuellen Zustand/Wert des Sensors zurück."""
        if not self.coordinator.data:
            return None
        
        # Holt den Wert aus dem vom Coordinator bereitgestellten Dictionary
        # Entweder unter 'site' oder 'flow', je nach data_path
        return self.coordinator.data.get(self._data_path, {}).get(self._key)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Gibt zusätzliche Attribute für den Cloud-Sensor zurück."""
        return {
            "key": self._key,
            "data_path": self._data_path,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Gibt Informationen zum virtuellen Cloud-Gerät zurück.
        
        Gruppiert die Cloud-Sensoren zusammen unter einem "Gerät" in der UI.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.site_id)},
            name="neoom AI Cloud Site",
            manufacturer="neoom",
            model="Cloud API",
        )


class NeoomLocalSensor(CoordinatorEntity, SensorEntity):
    """Repräsentation eines lokalen BEAAM Sensors (z.B. Leistung, Temperatur)."""

    def __init__(
        self,
        coordinator: NeoomLocalCoordinator,
        thing_id: str,
        thing_data: Dict[str, Any],
        dp_id: str,
        dp_data: Dict[str, Any],
    ) -> None:
        """Initialisiert den lokalen Sensor."""
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
        self._attr_unique_id = f"{thing_id}_{dp_id}"

        # Weise HA-spezifische Device Classes (Typ des Sensors, z.B. Leistung) 
        # und State Classes (Verhalten über Zeit, z.B. kumulativ) zu
        self._attr_device_class = self._map_device_class(self._key, self._uom_raw)
        self._attr_state_class = self._map_state_class(self._key, self._uom_raw)
        
        # Leite die richtige Einheit (z.B. kW, W) aus der rohen API-Einheit ab
        self._attr_native_unit_of_measurement = self._map_unit(self._uom_raw)
        
        # Initialen Status beim Erstellen setzen
        self._update_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Wird von der CoordinatorEntity-Basisklasse aufgerufen, wenn neue Daten ankommen.
        
        Wir aktualisieren unseren internen Wert und leiten dann das Update an Home Assistant weiter.
        """
        self._update_state()
        super()._handle_coordinator_update()

    def _update_state(self) -> None:
        """Liest den aktuellen Wert aus den Coordinator-Daten aus und setzt ihn als Status."""
        if not self.coordinator.data:
            self._attr_native_value = None
            return

        state_map: Dict[str, Any] = self.coordinator.data.get("states", {})
        data_point: Optional[Dict[str, Any]] = state_map.get(self._dp_id) or state_map.get(f"{self._thing_id}_{self._key}")

        if data_point:
            raw_value = data_point.get("value")

            # Gib Nummern als float, Texte als string zurück.
            # Wir verzichten hier bewusst auf manuelle Skalierungs-Magie (wie Kilo/Mega präfixe).
            # Home Assistant handhabt natives Skalieren in der UI automatisch viel besser,
            # wenn die Einheit und Device Class stimmen.
            if self._key == "OPERATING_MODE_SG_READY":
                val_str = str(raw_value).lower() if raw_value is not None else ""
                if val_str in ["65636", "0", "100", "2"]:
                    self._attr_native_value = "Normal (Mode 2)"
                elif val_str == "1":
                    self._attr_native_value = "Sperre (Mode 1)"
                elif val_str == "3":
                    self._attr_native_value = "Empfehlung (Mode 3)"
                elif val_str == "4":
                    self._attr_native_value = "Fest EIN (Mode 4)"
                else:
                    self._attr_native_value = raw_value
            elif raw_value is not None and isinstance(raw_value, (int, float)):
                self._attr_native_value = float(raw_value)
            else:
                self._attr_native_value = raw_value
        else:
            self._attr_native_value = None


    @property
    def device_info(self) -> DeviceInfo:
        """Gibt Informationen zum zugrundeliegenden Gerät zurück.
        
        Verknüpft diesen Sensor mit dem physischen Gerät (z.B. Wechselrichter).
        'via_device' zeigt an, dass die Kommunikation über das BEAAM Gateway läuft.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_id)},
            name=f"neoom {getattr(self, '_friendly_thing_name', self._thing_type)}",
            manufacturer="neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway"),
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Gibt spezifische Attribute für diesen Datenpunkt zurück."""
        return {
            "thing_id": self._thing_id,
            "datapoint_id": self._dp_id,
            "key": self._key,
        }

    def _map_unit(self, unit_str: str) -> Optional[str]:
        """Konvertiert die BEAAM String-Einheit in die offizielle Home Assistant Konstante."""
        if not unit_str or unit_str.lower() in ["none", "null"]:
            return None

        # Leistung (Power)
        if unit_str == "W":
            return UnitOfPower.WATT
        if unit_str == "kW":
            return UnitOfPower.KILO_WATT
        if unit_str == "MW":
            return UnitOfPower.MEGA_WATT
        if unit_str == "GW":
            return UnitOfPower.GIGA_WATT

        # Energie (Energy)
        if unit_str == "Wh":
            return UnitOfEnergy.WATT_HOUR
        if unit_str == "kWh":
            return UnitOfEnergy.KILO_WATT_HOUR
        if unit_str == "MWh":
            return UnitOfEnergy.MEGA_WATT_HOUR
        if unit_str == "GWh":
            return UnitOfEnergy.GIGA_WATT_HOUR

        # Elektrische Werte
        if unit_str == "V":
            return UnitOfElectricPotential.VOLT
        if unit_str == "A":
            return UnitOfElectricCurrent.AMPERE
        if unit_str == "Hz":
            return UnitOfFrequency.HERTZ

        # Temperatur
        if unit_str == "C":
            return UnitOfTemperature.CELSIUS
        if unit_str == "K":
            return UnitOfTemperature.KELVIN
            
        # Sonstiges
        if unit_str == "%":
            return PERCENTAGE
        if unit_str == "s":
            return UnitOfTime.SECONDS
        if unit_str == "h":
            return UnitOfTime.HOURS

        # Fallback auf den rohen String, wenn unbekannt
        return unit_str

    def _map_device_class(self, key: str, unit: str) -> Optional[SensorDeviceClass]:
        """Weist basierend auf dem Datentyp / der Einheit die richtige Home Assistant Sensor-Klasse zu.
        Dies beeinflusst die Darstellung und die verfügbaren Einheitenumrechnungen in der UI.
        """
        if unit in ["W", "kW", "MW", "GW"]:
            return SensorDeviceClass.POWER
        if unit in ["Wh", "kWh", "MWh", "GWh"]:
            return SensorDeviceClass.ENERGY
        if unit == "V":
            return SensorDeviceClass.VOLTAGE
        if unit == "A":
            return SensorDeviceClass.CURRENT
        if unit == "Hz":
            return SensorDeviceClass.FREQUENCY
        if unit in ["C", "K", "°C", UnitOfTemperature.CELSIUS, UnitOfTemperature.KELVIN] or "TEMPERATURE" in key:
            return SensorDeviceClass.TEMPERATURE
        if unit in ["s", "h", UnitOfTime.SECONDS, UnitOfTime.HOURS] or "TIME" in key or "DURATION" in key:
            return SensorDeviceClass.DURATION
        if unit == "%" and "SOC" in key:
            # SOC steht in der Branche für "State of Charge" (Batteriestand)
            return SensorDeviceClass.BATTERY
            
        return None

    def _map_state_class(self, key: str, unit: str) -> Optional[SensorStateClass]:
        """Bestimmt das Langzeit-Aufzeichnungsverhalten (Statistics) des Sensors in HA."""
        # Wenn es sich um eine Zahl ohne Einheit (None) handelt oder einen Text-Status
        if not unit or unit.lower() in ["none", "null"]:
            return None

        # Ausschluss von Nicht-Energiewerten: Leistung, Spannung, Strom, Frequenz, Temperatur, Zeit, Prozent
        if unit in ["%", "W", "kW", "MW", "GW", "V", "A", "Hz", "C", "K", "°C", "s", "h", UnitOfTemperature.CELSIUS, UnitOfTemperature.KELVIN, UnitOfTime.SECONDS, UnitOfTime.HOURS]:
            return SensorStateClass.MEASUREMENT

        # Prüfung für Energiewerte (Wh, kWh, MWh, GWh oder "ENERGY" im Schlüssel)
        if unit in ["Wh", "kWh", "MWh", "GWh"] or "ENERGY" in key:
            key_upper = key.upper()
            # Nicht-kumulative Energiewerte (z.B. gespeicherte Batterieenergie, Restkapazität, Limits)
            # stellen einen aktuellen Messwert dar und dürfen NICHT als TOTAL_INCREASING markiert werden,
            # da ein Absinken des Wertes sonst als Zähler-Reset interpretiert würde und Statistiken verfälscht.
            non_cumulative_indicators = [
                "STORED",
                "STORAGE",
                "USABLE",
                "RESERVE",
                "CAPACITY",
                "REMAINING",
                "CONTENT",
                "TARGET",
                "LIMIT",
                "CURRENT",
                "LEVEL",
                "SOC",
            ]
            if any(indicator in key_upper for indicator in non_cumulative_indicators):
                return SensorStateClass.MEASUREMENT

            # Zählerstände / kumulative Energiemengen (z.B. erzeugt, verbraucht, eingespeist)
            return SensorStateClass.TOTAL_INCREASING

        # Normalfall für sonstige Messwerte
        return SensorStateClass.MEASUREMENT
