"""Die neoom Connect Integration."""
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr  # <-- NEU: Import für Device Registry

from .const import DOMAIN, CONF_CLOUD_TOKEN, CONF_SITE_ID, CONF_BEAAM_IP, CONF_BEAAM_KEY
from .coordinator import NeoomCloudCoordinator, NeoomLocalCoordinator

# Füge "select" zu den unterstützten Plattformen hinzu
PLATFORMS = ["sensor", "number", "select"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Richtet neoom Connect basierend auf einem Konfigurationseintrag ein."""
    
    # 1. Cloud Coordinator einrichten
    cloud_coordinator = NeoomCloudCoordinator(
        hass, 
        token=entry.data[CONF_CLOUD_TOKEN], 
        site_id=entry.data[CONF_SITE_ID]
    )
    
    # 2. Local Coordinator einrichten
    local_coordinator = NeoomLocalCoordinator(
        hass,
        ip=entry.data[CONF_BEAAM_IP],
        key=entry.data[CONF_BEAAM_KEY]
    )

    # Erste Datenabfrage durchführen
    await cloud_coordinator.async_config_entry_first_refresh()
    
    try:
        await local_coordinator.async_config_entry_first_refresh()
    except Exception:
        pass 

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "cloud": cloud_coordinator,
        "local": local_coordinator
    }

    # --- FIX START: Gateway Device explizit registrieren ---
    # Wir müssen das BEAAM Gateway im Device Registry anlegen, bevor die Sensoren
    # darauf verweisen können ('via_device'), um den Fehler zu vermeiden.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "BEAAM Gateway")},
        manufacturer="neoom",
        name="BEAAM Gateway",
        model="BEAAM",
        configuration_url=f"http://{entry.data[CONF_BEAAM_IP]}"
    )
    # --- FIX END ---

    # Lade alle Plattformen (jetzt auch Select)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entlädt einen Konfigurationseintrag."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["cloud"].close()
        await data["local"].close()

    return unload_ok
