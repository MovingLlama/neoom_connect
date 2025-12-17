"""DataUpdateCoordinators for Neoom Connect."""
import aiohttp
import async_timeout
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    DOMAIN,
    LOGGER,
    CLOUD_API_URL,
    DEFAULT_SCAN_INTERVAL_CLOUD,
    DEFAULT_SCAN_INTERVAL_LOCAL,
)

class NeoomCloudCoordinator(DataUpdateCoordinator):
    """Coordinator for Ntuity Cloud Data."""

    def __init__(self, hass: HomeAssistant, token: str, site_id: str):
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_cloud",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_CLOUD),
        )
        self.token = token
        self.site_id = site_id
        self.session = aiohttp.ClientSession()

    async def _async_update_data(self):
        """Fetch data from Ntuity Cloud."""
        try:
            # Fetch Site Info (Tariffs, etc.)
            async with async_timeout.timeout(10):
                headers = {"Authorization": f"Bearer {self.token}"}
                
                # 1. General Site Info
                url_site = f"{CLOUD_API_URL}/sites/{self.site_id}"
                async with self.session.get(url_site, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Cloud Token Invalid")
                    resp.raise_for_status()
                    site_data = await resp.json()

                # 2. Latest Energy Flow
                url_flow = f"{CLOUD_API_URL}/sites/{self.site_id}/energy-flow/latest"
                async with self.session.get(url_flow, headers=headers) as resp:
                    resp.raise_for_status()
                    flow_data = await resp.json()

            return {
                "site": site_data,
                "flow": flow_data
            }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with Ntuity API: {err}")

    async def close(self):
        await self.session.close()


class NeoomLocalCoordinator(DataUpdateCoordinator):
    """Coordinator for BEAAM Local Data."""

    def __init__(self, hass: HomeAssistant, ip: str, key: str):
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_local",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_LOCAL),
        )
        self.ip = ip
        self.key = key
        self.session = aiohttp.ClientSession()
        # We store the configuration (metadata) separately so we don't fetch it every poll
        self.beaam_config = None 

    async def _ensure_config_loaded(self):
        """Fetch the configuration map once to understand the device structure."""
        if self.beaam_config:
            return

        url = f"http://{self.ip}/api/v1/site/configuration"
        # Assuming Bearer token for local API as well, or just passed. 
        # Adjust header if BEAAM uses a specific custom header.
        headers = {"Authorization": f"Bearer {self.key}"} 
        
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(url, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Local API Key Invalid")
                    resp.raise_for_status()
                    self.beaam_config = await resp.json()
                    LOGGER.info("BEAAM Configuration loaded successfully")
        except Exception as err:
             raise UpdateFailed(f"Could not load BEAAM configuration: {err}")

    async def _async_update_data(self):
        """Fetch real-time state from BEAAM."""
        await self._ensure_config_loaded()

        try:
            async with async_timeout.timeout(5):
                url = f"http://{self.ip}/api/v1/site/state"
                headers = {"Authorization": f"Bearer {self.key}"}
                
                async with self.session.get(url, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Local API Key Invalid")
                    resp.raise_for_status()
                    data = await resp.json()
                    
                    # Transform list of states into a dict keyed by DataPoint ID for easy lookup O(1)
                    # The API returns { "energyFlow": { "states": [ ... ] } }
                    state_map = {}
                    if "energyFlow" in data and "states" in data["energyFlow"]:
                        for item in data["energyFlow"]["states"]:
                            state_map[item["dataPointId"]] = item
                    
                    return {
                        "config": self.beaam_config,
                        "states": state_map
                    }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with BEAAM: {err}")

    async def close(self):
        await self.session.close()