"""Sensor platform for Neoom Connect."""
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
    """Setup sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    cloud_coordinator = data["cloud"]
    local_coordinator = data["local"]

    entities = []

    # --- CLOUD SENSORS ---
    # Example: Electricity Price
    entities.append(NeoomCloudSensor(
        cloud_coordinator, "electricity_price", "Electricity Price", "EUR/kWh", "mdi:currency-eur"
    ))
    entities.append(NeoomCloudSensor(
        cloud_coordinator, "feed_in_tariff", "Feed-in Tariff", "ct/kWh", "mdi:cash-plus"
    ))

    # --- LOCAL SENSORS (Dynamic) ---
    # We iterate through the 'things' in the configuration to create devices and sensors
    beaam_config = local_coordinator.data.get("config", {})
    
    if beaam_config:
        things = beaam_config.get("things", {})
        
        for thing_id, thing_data in things.items():
            thing_type = thing_data.get("type")
            datapoints = thing_data.get("dataPoints", {})

            for dp_id, dp_data in datapoints.items():
                # We only create sensors for numeric types generally
                # dataType: NUMBER, STRING, BOOLEAN
                dtype = dp_data.get("dataType")
                key = dp_data.get("key")
                
                # Filter useful sensors
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
    """Representation of a generic Cloud Sensor."""

    def __init__(self, coordinator, key, name, unit, icon):
        super().__init__(coordinator)
        self._key = key
        self._name = name
        self._unit = unit
        self._icon = icon
        self._attr_unique_id = f"{coordinator.site_id}_{key}"

    @property
    def name(self):
        return f"Neoom Cloud {self._name}"

    @property
    def state(self):
        # Data is in coordinator.data["site"]
        return self.coordinator.data.get("site", {}).get(self._key)

    @property
    def unit_of_measurement(self):
        return self._unit

    @property
    def icon(self):
        return self._icon
    
    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.site_id)},
            name="Ntuity Cloud Site",
            manufacturer="Neoom",
            model="Cloud API",
        )


class NeoomLocalSensor(CoordinatorEntity, SensorEntity):
    """Representation of a BEAAM Local Sensor."""

    def __init__(self, coordinator, thing_id, thing_data, dp_id, dp_data):
        super().__init__(coordinator)
        self._thing_id = thing_id
        self._thing_type = thing_data.get("type", "Unknown")
        self._dp_id = dp_id
        self._key = dp_data.get("key")
        self._uom_raw = dp_data.get("unitOfMeasure")
        
        # Determine readable name
        # E.g., Inverter Active Power
        friendly_thing_name = self._thing_type.replace("_", " ").title()
        friendly_dp_name = self._key.replace("_", " ").title()
        self._attr_name = f"{friendly_thing_name} {friendly_dp_name}"
        self._attr_unique_id = f"{thing_id}_{dp_id}"

        # Map Units to HA Constants
        self._attr_native_unit_of_measurement = self._map_unit(self._uom_raw)
        self._attr_device_class = self._map_device_class(self._key, self._uom_raw)
        self._attr_state_class = self._map_state_class(self._key)

    @property
    def native_value(self):
        # Look up value in the state map using dp_id
        state_map = self.coordinator.data.get("states", {})
        data_point = state_map.get(self._dp_id)
        
        if data_point:
            return data_point.get("value")
        return None

    @property
    def device_info(self):
        """Link this sensor to a device (e.g., the specific Inverter)."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_id)},
            name=f"Neoom {self._thing_type}",
            manufacturer="Neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway")
        )

    def _map_unit(self, raw_unit):
        if raw_unit == "W": return UnitOfPower.WATT
        if raw_unit == "Wh": return UnitOfEnergy.WATT_HOUR
        if raw_unit == "V": return UnitOfElectricPotential.VOLT
        if raw_unit == "A": return UnitOfElectricCurrent.AMPERE
        if raw_unit == "%": return PERCENTAGE
        if raw_unit == "Hz": return UnitOfFrequency.HERTZ
        if raw_unit == "s": return UnitOfTime.SECONDS
        return None

    def _map_device_class(self, key, unit):
        if unit == "W": return SensorDeviceClass.POWER
        if unit == "Wh": return SensorDeviceClass.ENERGY
        if unit == "V": return SensorDeviceClass.VOLTAGE
        if unit == "A": return SensorDeviceClass.CURRENT
        if unit == "%" and "SOC" in key: return SensorDeviceClass.BATTERY
        return None

    def _map_state_class(self, key):
        if "ENERGY" in key:
            return SensorStateClass.TOTAL_INCREASING
        return SensorStateClass.MEASUREMENT