"""The Neoom Connect integration."""
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_CLOUD_TOKEN, CONF_SITE_ID, CONF_BEAAM_IP, CONF_BEAAM_KEY
from .coordinator import NeoomCloudCoordinator, NeoomLocalCoordinator

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Neoom Connect from a config entry."""
    
    # 1. Setup Cloud Coordinator
    cloud_coordinator = NeoomCloudCoordinator(
        hass, 
        token=entry.data[CONF_CLOUD_TOKEN], 
        site_id=entry.data[CONF_SITE_ID]
    )
    
    # 2. Setup Local Coordinator
    local_coordinator = NeoomLocalCoordinator(
        hass,
        ip=entry.data[CONF_BEAAM_IP],
        key=entry.data[CONF_BEAAM_KEY]
    )

    # Initial Refresh
    await cloud_coordinator.async_config_entry_first_refresh()
    # For local, we accept it might fail initially if device is offline, but we try
    try:
        await local_coordinator.async_config_entry_first_refresh()
    except Exception:
        pass # Allow setup to continue even if local is momentarily down

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "cloud": cloud_coordinator,
        "local": local_coordinator
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["cloud"].close()
        await data["local"].close()

    return unload_ok