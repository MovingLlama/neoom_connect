"""DataUpdateCoordinators für neoom Connect."""
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
    """Koordinator für Ntuity Cloud Daten."""

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
        """Ruft Daten von der Ntuity Cloud ab."""
        try:
            # Timeout von 10 Sekunden für Cloud-Anfragen
            async with async_timeout.timeout(10):
                headers = {"Authorization": f"Bearer {self.token}"}
                
                # 1. Allgemeine Site-Informationen abrufen (Adresse, Tarife, etc.)
                url_site = f"{CLOUD_API_URL}/sites/{self.site_id}"
                async with self.session.get(url_site, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Cloud Token ist ungültig")
                    resp.raise_for_status()
                    site_data = await resp.json()

                # 2. Letzten Energiefluss abrufen (Übersichtswerte)
                url_flow = f"{CLOUD_API_URL}/sites/{self.site_id}/energy-flow/latest"
                async with self.session.get(url_flow, headers=headers) as resp:
                    resp.raise_for_status()
                    flow_data = await resp.json()

            return {
                "site": site_data,
                "flow": flow_data
            }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Fehler bei der Kommunikation mit Ntuity API: {err}")

    async def close(self):
        """Schließt die HTTP-Session."""
        await self.session.close()


class NeoomLocalCoordinator(DataUpdateCoordinator):
    """Koordinator für BEAAM lokale Daten."""

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
        # Wir speichern die Konfiguration separat, da sie sich selten ändert
        self.beaam_config = None 

    async def _ensure_config_loaded(self):
        """Lädt die Konfiguration einmalig, um die Gerätestruktur zu verstehen."""
        if self.beaam_config:
            return

        url = f"http://{self.ip}/api/v1/site/configuration"
        headers = {"Authorization": f"Bearer {self.key}"} 
        
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(url, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Lokaler API Key ist ungültig")
                    resp.raise_for_status()
                    self.beaam_config = await resp.json()
                    LOGGER.info("BEAAM Konfiguration erfolgreich geladen")
        except Exception as err:
             raise UpdateFailed(f"Konnte BEAAM Konfiguration nicht laden: {err}")

    async def _fetch_thing_state(self, thing_id, headers):
        """Hilfsfunktion: Ruft den Status eines einzelnen Geräts ('Thing') ab."""
        url = f"http://{self.ip}/api/v1/things/{thing_id}/states"
        try:
            # Kurzer Timeout pro Gerät, damit ein einzelnes langsames Gerät nicht alles blockiert
            async with self.session.get(url, headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            LOGGER.debug(f"Konnte Status für Thing {thing_id} nicht abrufen")
        return None

    async def _async_update_data(self):
        """Ruft Echtzeit-Status vom BEAAM ab (Site + alle Geräte)."""
        await self._ensure_config_loaded()

        headers = {"Authorization": f"Bearer {self.key}"}
        state_map = {} # Hier sammeln wir alle Datenpunkte

        try:
            async with async_timeout.timeout(20):
                # 1. Globalen Site-Status abrufen
                url_site = f"http://{self.ip}/api/v1/site/state"
                async with self.session.get(url_site, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Lokaler API Key ist ungültig")
                    resp.raise_for_status()
                    site_data = await resp.json()
                    
                    # Site-Daten mappen
                    if "energyFlow" in site_data and "states" in site_data["energyFlow"]:
                        for item in site_data["energyFlow"]["states"]:
                            state_map[item["dataPointId"]] = item

                # 2. Status für einzelne Geräte abrufen (parallel für Geschwindigkeit)
                if self.beaam_config and "things" in self.beaam_config:
                    tasks = []
                    for thing_id in self.beaam_config["things"]:
                        tasks.append(self._fetch_thing_state(thing_id, headers))
                    
                    if tasks:
                        results = await asyncio.gather(*tasks)
                        for res in results:
                            if res and "states" in res:
                                for item in res["states"]:
                                    # Datenpunkte in die gemeinsame Map einfügen
                                    state_map[item["dataPointId"]] = item

                return {
                    "config": self.beaam_config,
                    "states": state_map
                }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Fehler bei der Kommunikation mit BEAAM: {err}")

    async def async_send_command(self, thing_id, key, value):
        """Sendet einen Befehl an die BEAAM API (z.B. Setzen eines Werts)."""
        url = f"http://{self.ip}/api/v1/things/{thing_id}/commands"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }
        # Payload Struktur: Liste von Befehlsobjekten
        payload = [
            {
                "key": key,
                "value": value
            }
        ]
        
        LOGGER.debug(f"Sende Befehl an {thing_id}: {key} = {value}")
        
        try:
            async with async_timeout.timeout(10):
                async with self.session.post(url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    LOGGER.info(f"Befehl erfolgreich gesendet: {key} -> {value}")
                    # Erzwinge eine sofortige Aktualisierung, damit die UI den neuen Wert anzeigt
                    await self.async_request_refresh()
        except Exception as err:
            LOGGER.error(f"Fehler beim Senden des Befehls: {err}")
            raise

    async def close(self):
        """Schließt die HTTP-Session."""
        await self.session.close()