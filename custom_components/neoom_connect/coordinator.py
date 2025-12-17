"""DataUpdateCoordinators for Neoom Connect."""
import aiohttp
import async_timeout
import asyncio
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
        # We store the configuration (metadata) separately
        self.beaam_config = None 

    async def _ensure_config_loaded(self):
        """Fetch the configuration map once to understand the device structure."""
        if self.beaam_config:
            return

        url = f"http://{self.ip}/api/v1/site/configuration"
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

    async def _fetch_thing_state(self, thing_id, headers):
        """Helper to fetch state for a single thing (safe against partial failures)."""
        url = f"http://{self.ip}/api/v1/things/{thing_id}/states"
        try:
            # We use a short timeout for individual things so one slow device doesn't block everything
            async with self.session.get(url, headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            # Log debug but don't fail the whole update if one thing is offline
            LOGGER.debug(f"Could not fetch state for thing {thing_id}")
        return None

    async def _async_update_data(self):
        """Fetch real-time state from BEAAM (Site + All Things)."""
        await self._ensure_config_loaded()

        headers = {"Authorization": f"Bearer {self.key}"}
        state_map = {}

        try:
            async with async_timeout.timeout(20): # Increased timeout for multiple requests
                
                # 1. Fetch Global Site State
                url_site = f"http://{self.ip}/api/v1/site/state"
                async with self.session.get(url_site, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Local API Key Invalid")
                    resp.raise_for_status()
                    site_data = await resp.json()
                    
                    # Map Site Data
                    if "energyFlow" in site_data and "states" in site_data["energyFlow"]:
                        for item in site_data["energyFlow"]["states"]:
                            state_map[item["dataPointId"]] = item

                # 2. Fetch Individual Things States (Parallel)
                if self.beaam_config and "things" in self.beaam_config:
                    tasks = []
                    for thing_id in self.beaam_config["things"]:
                        tasks.append(self._fetch_thing_state(thing_id, headers))
                    
                    if tasks:
                        results = await asyncio.gather(*tasks)
                        for res in results:
                            if res and "states" in res:
                                for item in res["states"]:
                                    # Merge into the main map
                                    state_map[item["dataPointId"]] = item

                return {
                    "config": self.beaam_config,
                    "states": state_map
                }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with BEAAM: {err}")

    async def close(self):
        await self.session.close()