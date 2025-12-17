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
from homeassistant.core import HomeAssistant, callback
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
    entities.append(NeoomCloudSensor(
        cloud_coordinator, "electricity_price", "Electricity Price", "EUR/kWh", "mdi:currency-eur"
    ))
    entities.append(NeoomCloudSensor(
        cloud_coordinator, "feed_in_tariff", "Feed-in Tariff", "ct/kWh", "mdi:cash-plus"
    ))

    # --- LOKALE SENSOREN (Dynamisch) ---
    beaam_config = local_coordinator.data.get("config", {}) if local_coordinator.data else {}
    
    if beaam_config:
        things = beaam_config.get("things", {})
        
        for thing_id, thing_data in things.items():
            if not thing_data: continue

            thing_type = thing_data.get("type")
            datapoints = thing_data.get("dataPoints", {})

            for dp_id, dp_data in datapoints.items():
                if not dp_data: continue

                dtype = dp_data.get("dataType")
                
                # Wir erlauben jetzt auch STRING (z.B. für PHASE_SWITCHING_MODE)
                if dtype in ["NUMBER", "STRING"]:
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
        self._attr_unique_id = f"{coordinator.site_id}_{key}"

    @property
    def name(self):
        return f"neoom Cloud {self._name}"

    @property
    def state(self):
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
        
        friendly_thing_name = self._thing_type.replace("_", " ").title()
        friendly_dp_name = self._key.replace("_", " ").title()
        self._attr_name = f"{friendly_thing_name} {friendly_dp_name}"
        self._attr_unique_id = f"{thing_id}_{dp_id}"

        self._attr_device_class = self._map_device_class(self._key, self._uom_raw)
        self._attr_state_class = self._map_state_class(self._key)
        
        self._update_state_and_unit()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Wird aufgerufen, wenn neue Daten vom Coordinator kommen."""
        self._update_state_and_unit()
        super()._handle_coordinator_update()

    def _update_state_and_unit(self):
        """Berechnet Wert und Einheit."""
        if not self.coordinator.data:
            self._attr_native_value = None
            self._attr_native_unit_of_measurement = self._map_unit(self._uom_raw)
            return

        state_map = self.coordinator.data.get("states", {})
        data_point = state_map.get(self._dp_id)
        
        if data_point:
            raw_value = data_point.get("value")
            
            # Smart Scaling nur für Zahlen
            if raw_value is not None and isinstance(raw_value, (int, float)):
                scaled_val, scaled_unit_str = self._smart_scale(float(raw_value), self._uom_raw)
                self._attr_native_value = scaled_val
                self._attr_native_unit_of_measurement = self._map_unit(scaled_unit_str)
            else:
                # Strings (z.B. Mode) einfach durchreichen
                self._attr_native_value = raw_value
                # Bei Strings ist unit oft "None", wir mappen das zu None (leer)
                self._attr_native_unit_of_measurement = self._map_unit(self._uom_raw)
        else:
            self._attr_native_value = None

    def _smart_scale(self, value, unit):
        """Skaliert Werte automatisch in k, M, G Einheiten."""
        if unit not in ["W", "Wh"]:
            return value, unit
            
        abs_value = abs(value)
        if abs_value >= 1_000_000_000:
            return round(value / 1_000_000_000, 2), "G" + unit
        elif abs_value >= 1_000_000:
            return round(value / 1_000_000, 2), "M" + unit
        elif abs_value >= 1_000:
            return round(value / 1_000, 2), "k" + unit
        
        return round(value, 2), unit

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._thing_id)},
            name=f"neoom {self._thing_type}",
            manufacturer="neoom",
            model=self._thing_type,
            via_device=(DOMAIN, "BEAAM Gateway")
        )

    def _map_unit(self, unit_str):
        # Wenn Einheit "None" ist (bei Strings üblich), geben wir None zurück (keine Einheit in UI)
        if unit_str == "None": return None
        
        # Power
        if unit_str == "W": return UnitOfPower.WATT
        if unit_str == "kW": return UnitOfPower.KILO_WATT
        if unit_str == "MW": return UnitOfPower.MEGA_WATT
        if unit_str == "GW": return UnitOfPower.GIGA_WATT
        
        # Energy
        if unit_str == "Wh": return UnitOfEnergy.WATT_HOUR
        if unit_str == "kWh": return UnitOfEnergy.KILO_WATT_HOUR
        if unit_str == "MWh": return UnitOfEnergy.MEGA_WATT_HOUR
        if unit_str == "GWh": return UnitOfEnergy.GIGA_WATT_HOUR
        
        # Others
        if unit_str == "V": return UnitOfElectricPotential.VOLT
        if unit_str == "A": return UnitOfElectricCurrent.AMPERE
        if unit_str == "%": return PERCENTAGE
        if unit_str == "Hz": return UnitOfFrequency.HERTZ
        if unit_str == "s": return UnitOfTime.SECONDS
        
        return unit_str

    def _map_device_class(self, key, unit):
        if unit in ["W", "kW", "MW", "GW"]: return SensorDeviceClass.POWER
        if unit in ["Wh", "kWh", "MWh", "GWh"]: return SensorDeviceClass.ENERGY
        if unit == "V": return SensorDeviceClass.VOLTAGE
        if unit == "A": return SensorDeviceClass.CURRENT
        if unit == "%" and "SOC" in key: return SensorDeviceClass.BATTERY
        return None

    def _map_state_class(self, key):
        if "ENERGY" in key:
            return SensorStateClass.TOTAL_INCREASING
        # Keine State Class für Strings (Modes)
        if isinstance(self._uom_raw, str) and self._uom_raw == "None":
            return None
        return SensorStateClass.MEASUREMENT