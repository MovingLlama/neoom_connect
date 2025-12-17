"""Die neoom Connect Integration."""
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_CLOUD_TOKEN, CONF_SITE_ID, CONF_BEAAM_IP, CONF_BEAAM_KEY
from .coordinator import NeoomCloudCoordinator, NeoomLocalCoordinator

# Füge "number" zu den unterstützten Plattformen hinzu (für steuerbare Werte)
PLATFORMS = ["sensor", "number"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Richtet neoom Connect basierend auf einem Konfigurationseintrag ein."""
    
    # 1. Cloud Coordinator einrichten
    # Dieser kümmert sich um API-Aufrufe zur Ntuity Cloud (z.B. Tarife)
    cloud_coordinator = NeoomCloudCoordinator(
        hass, 
        token=entry.data[CONF_CLOUD_TOKEN], 
        site_id=entry.data[CONF_SITE_ID]
    )
    
    # 2. Local Coordinator einrichten
    # Dieser kommuniziert direkt mit dem BEAAM Gateway im lokalen Netzwerk
    local_coordinator = NeoomLocalCoordinator(
        hass,
        ip=entry.data[CONF_BEAAM_IP],
        key=entry.data[CONF_BEAAM_KEY]
    )

    # Erste Datenabfrage durchführen
    # Cloud muss erfolgreich sein, sonst schlägt das Setup fehl
    await cloud_coordinator.async_config_entry_first_refresh()
    
    # Versuche lokale Daten abzurufen. Wenn das Gateway offline ist,
    # machen wir trotzdem weiter, damit zumindest die Cloud-Sensoren gehen.
    try:
        await local_coordinator.async_config_entry_first_refresh()
    except Exception:
        pass 

    # Speichere die Koordinatoren im globalen hass.data Speicher
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "cloud": cloud_coordinator,
        "local": local_coordinator
    }

    # Lade die Plattformen (Sensor, Number, etc.)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entlädt einen Konfigurationseintrag."""
    # Entferne zuerst die Plattformen
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Wenn erfolgreich, bereinige die gespeicherten Daten und schließe API-Sessions
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["cloud"].close()
        await data["local"].close()

    return unload_ok