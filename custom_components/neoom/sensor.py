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
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NeoomCloudCoordinator, NeoomLocalCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[SensorEntity]], None],
) -> None:
    """Richtet die Sensor-Plattform basierend auf dem Konfigurationseintrag ein.
    
    Diese Methode wird von Home Assistant aufgerufen, um Entitäten zu registrieren.

    Args:
        hass: Die Home Assistant Instanz.
        entry: Der Konfigurationseintrag.
        async_add_entities: Die Methode zum Registrieren der neuen Entitäten.
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
            unit="EUR/kWh",
            icon="mdi:currency-eur",
        )
    )
    entities.append(
        NeoomCloudSensor(
            coordinator=cloud_coordinator,
            key="feed_in_tariff",
            name="Feed-in Tariff",
            unit="ct/kWh",
            icon="mdi:cash-plus",
        )
    )

    # --- LOKALE SENSOREN (Dynamisch) ---
    # Da das BEAAM Gateway je nach Standort unterschiedliche Geräte 
    # (Wechselrichter, Speicher, E-Ladestation) angebunden hat,
    # generieren wir diese Sensoren dynamisch anhand der BEAAM Konfiguration.
    beaam_config: Dict[str, Any] = (
        local_coordinator.data.get("config", {}) if local_coordinator.data else {}
    )

    if beaam_config:
        things: Dict[str, Any] = beaam_config.get("things", {})

        for thing_id, thing_data in things.items():
            if not thing_data:
                continue

            # Jeder Datenpunkt (DP) eines Geräts (Thing) wird zu einem eigenen Home Assistant Sensor
            datapoints: Dict[str, Any] = thing_data.get("dataPoints", {})

            for dp_id, dp_data in datapoints.items():
                if not dp_data:
                    continue

                dtype: str = dp_data.get("dataType", "")

                # Wir erstellen Sensoren für Zahlen (Leistung, Prozente) und Strings (Betriebsmodi)
                if dtype in ["NUMBER", "STRING"]:
                    entities.append(
                        NeoomLocalSensor(
                            coordinator=local_coordinator,
                            thing_id=thing_id,
                            thing_data=thing_data,
                            dp_id=dp_id,
                            dp_data=dp_data,
                        )
                    )

    # Füge alle generierten Sensoren zu Home Assistant hinzu
    async_add_entities(entities)


class NeoomCloudSensor(CoordinatorEntity, SensorEntity):
    """Repräsentation eines generischen Cloud-Sensors (z.B. Tarifdaten).
    
    Erbt von CoordinatorEntity, damit der Sensor automatisch aktualisiert wird,
    wenn der Koordinator neue Daten aus dem Internet lädt.
    """

    def __init__(
        self,
        coordinator: NeoomCloudCoordinator,
        key: str,
        name: str,
        unit: str,
        icon: str,
    ) -> None:
        """Initialisiert den Cloud-Sensor."""
        super().__init__(coordinator)
        self._key = key
        self._name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        
        # Eindeutige ID ist entscheidend für Home Assistant, um die Entität wiederzuerkennen
        self._attr_unique_id = f"{coordinator.site_id}_{key}"

    @property
    def name(self) -> str:
        """Gibt den Anzeigenamen des Sensors zurück."""
        return f"neoom Cloud {self._name}"

    @property
    def native_value(self) -> Any:
        """Gibt den aktuellen Zustand/Wert des Sensors zurück."""
        if not self.coordinator.data:
            return None
        
        # Holt den Wert aus dem vom Coordinator bereitgestellten Dictionary
        return self.coordinator.data.get("site", {}).get(self._key)

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

        # Mache den Namen benutzerfreundlich (z.B. BATT_INVERTER -> Batt Inverter)
        friendly_thing_name = self._thing_type.replace("_", " ").title()
        friendly_dp_name = self._key.replace("_", " ").title()
        
        self._attr_name = f"{friendly_thing_name} {friendly_dp_name}"
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
        data_point: Optional[Dict[str, Any]] = state_map.get(self._dp_id)

        if data_point:
            raw_value = data_point.get("value")

            # Gib Nummern als float, Texte als string zurück.
            # Wir verzichten hier bewusst auf manuelle Skalierungs-Magie (wie Kilo/Mega präfixe).
            # Home Assistant handhabt natives Skalieren in der UI automatisch viel besser,
            # wenn die Einheit und Device Class stimmen.
            if raw_value is not None and isinstance(raw_value, (int, float)):
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
            name=f"neoom {self._thing_type}",
            manufacturer="neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway"),
        )

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
            
        # Sonstiges
        if unit_str == "%":
            return PERCENTAGE
        if unit_str == "s":
            return UnitOfTime.SECONDS

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
        if unit == "%" and "SOC" in key:
            # SOC steht in der Branche für "State of Charge" (Batteriestand)
            return SensorDeviceClass.BATTERY
            
        return None

    def _map_state_class(self, key: str, unit: str) -> Optional[SensorStateClass]:
        """Bestimmt das Langzeit-Aufzeichnungsverhalten (Statistics) des Sensors in HA."""
        # Energiemengen (produziert/verbraucht) steigen kontinuierlich an
        if "ENERGY" in key or unit in ["Wh", "kWh", "MWh", "GWh"]:
            return SensorStateClass.TOTAL_INCREASING
            
        # Wenn es sich um eine Zahl ohne Einheit (None) handelt oder einen Text-Status
        if not unit or unit.lower() in ["none", "null"]:
            return None
            
        # Normalfall für Messwerte wie Leistung, Spannung, Temperatur
        return SensorStateClass.MEASUREMENT
