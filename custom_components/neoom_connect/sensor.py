"""Sensor Plattform für neoom Connect."""
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfPower,
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    PERCENTAGE,
    UnitOfFrequency,
    UnitOfTime
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Richtet die Sensor-Plattform ein."""
    data = hass.data[DOMAIN][entry.entry_id]
    cloud_coordinator = data["cloud"]
    local_coordinator = data["local"]

    entities = []

    # --- CLOUD SENSOREN ---
    # Statische Sensoren für Cloud-Daten
    entities.append(NeoomCloudSensor(
        cloud_coordinator, "electricity_price", "Electricity Price", "EUR/kWh", "mdi:currency-eur"
    ))
    entities.append(NeoomCloudSensor(
        cloud_coordinator, "feed_in_tariff", "Feed-in Tariff", "ct/kWh", "mdi:cash-plus"
    ))

    # --- LOKALE SENSOREN (Dynamisch) ---
    # Versuche die Konfiguration zu laden (kann beim Start leer sein, wenn offline)
    beaam_config = local_coordinator.data.get("config", {}) if local_coordinator.data else {}
    
    if beaam_config:
        things = beaam_config.get("things", {})
        
        for thing_id, thing_data in things.items():
            if not thing_data: continue

            thing_type = thing_data.get("type")
            datapoints = thing_data.get("dataPoints", {})

            for dp_id, dp_data in datapoints.items():
                if not dp_data: continue

                # Wir erstellen Sensoren nur für numerische Typen
                dtype = dp_data.get("dataType")
                
                # Check dataType (manchmal Arrays, wir nehmen vorerst einfache NUMBER)
                if dtype == "NUMBER":
                    entities.append(NeoomLocalSensor(
                        local_coordinator, 
                        thing_id, 
                        thing_data, 
                        dp_id, 
                        dp_data
                    ))

    async_add_entities(entities)


class NeoomCloudSensor(CoordinatorEntity, SensorEntity):
    """Repräsentation eines generischen Cloud-Sensors."""

    def __init__(self, coordinator, key, name, unit, icon):
        super().__init__(coordinator)
        self._key = key
        self._name = name
        self._unit = unit
        self._icon = icon
        # Eindeutige ID basierend auf Site-ID und Schlüssel
        self._attr_unique_id = f"{coordinator.site_id}_{key}"

    @property
    def name(self):
        return f"neoom Cloud {self._name}"

    @property
    def state(self):
        """Gibt den aktuellen Wert aus den Koordinator-Daten zurück."""
        if not self.coordinator.data: return None
        return self.coordinator.data.get("site", {}).get(self._key)

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def icon(self):
        return self._icon
    
    @property
    def device_info(self):
        """Verknüpft den Sensor mit dem Cloud-Dienst Device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.site_id)},
            name="Ntuity Cloud Site",
            manufacturer="neoom",
            model="Cloud API",
        )


class NeoomLocalSensor(CoordinatorEntity, SensorEntity):
    """Repräsentation eines lokalen BEAAM Sensors."""

    def __init__(self, coordinator, thing_id, thing_data, dp_id, dp_data):
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type = thing_data.get("type", "Unknown")
        self._dp_id = dp_id
        self._key = dp_data.get("key")
        self._uom_raw = dp_data.get("unitOfMeasure")
        
        # Erstelle lesbare Namen (z.B. aus "INVERTER" wird "Inverter")
        friendly_thing_name = self._thing_type.replace("_", " ").title()
        friendly_dp_name = self._key.replace("_", " ").title()
        self._attr_name = f"{friendly_thing_name} {friendly_dp_name}"
        self._attr_unique_id = f"{thing_id}_{dp_id}"

        # Mappe Einheiten und Device Classes für Home Assistant
        self._attr_native_unit_of_measurement = self._map_unit(self._uom_raw)
        self._attr_device_class = self._map_device_class(self._key, self._uom_raw)
        self._attr_state_class = self._map_state_class(self._key)

    @property
    def native_value(self):
        """Holt den Wert aus der zusammengeführten State-Map."""
        if not self.coordinator.data: return None
        
        state_map = self.coordinator.data.get("states", {})
        data_point = state_map.get(self._dp_id)
        
        if data_point:
            return data_point.get("value")
        return None

    @property
    def device_info(self):
        """Verknüpft den Sensor mit dem physischen Gerät (z.B. Wechselrichter)."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_id)},
            name=f"neoom {self._thing_type}",
            manufacturer="neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway")
        )

    def _map_unit(self, raw_unit):
        """Konvertiert API-Einheiten in HA-Konstanten."""
        if raw_unit == "W": return UnitOfPower.WATT
        if raw_unit == "Wh": return UnitOfEnergy.WATT_HOUR
        if raw_unit == "V": return UnitOfElectricPotential.VOLT
        if raw_unit == "A": return UnitOfElectricCurrent.AMPERE
        if raw_unit == "%": return PERCENTAGE
        if raw_unit == "Hz": return UnitOfFrequency.HERTZ
        if raw_unit == "s": return UnitOfTime.SECONDS
        return None

    def _map_device_class(self, key, unit):
        """Bestimmt die Klasse des Sensors (für Icons und Darstellung)."""
        if unit == "W": return SensorDeviceClass.POWER
        if unit == "Wh": return SensorDeviceClass.ENERGY
        if unit == "V": return SensorDeviceClass.VOLTAGE
        if unit == "A": return SensorDeviceClass.CURRENT
        if unit == "%" and "SOC" in key: return SensorDeviceClass.BATTERY
        return None

    def _map_state_class(self, key):
        """Bestimmt, wie Statistiken aufgezeichnet werden."""
        if "ENERGY" in key:
            return SensorStateClass.TOTAL_INCREASING
        return SensorStateClass.MEASUREMENT