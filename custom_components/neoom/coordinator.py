"""Daten-Aktualisierungs-Koordinatoren (DataUpdateCoordinators) für neoom AI.

Diese Koordinatoren sind dafür verantwortlich, in regelmäßigen Abständen Daten
von den jeweiligen APIs (neoom AI Cloud und lokales BEAAM Gateway) abzurufen 
und diese dann den Sensoren und anderen Entitäten in Home Assistant zur Verfügung zu stellen.
Das verhindert, dass jede Entität eigene Netzwerk-Anfragen stellt, was die Systeme überlasten würde.
"""

import asyncio
from datetime import timedelta
from typing import Any, Dict, List, Optional

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CLOUD_API_URL,
    DEFAULT_SCAN_INTERVAL_CLOUD,
    DEFAULT_SCAN_INTERVAL_LOCAL,
    DOMAIN,
    LOGGER,
)


class NeoomCloudCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Koordinator für den Abruf von Daten aus der neoom AI Cloud."""

    def __init__(self, hass: HomeAssistant, token: str, site_id: str) -> None:
        """Initialisiert den Cloud-Koordinator.

        Args:
            hass: Die Home Assistant Instanz.
            token: Das Authentifizierungs-Token (Bearer Token) für die Cloud.
            site_id: Die eindeutige ID des Standorts (Site).
        """
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_cloud",
            # Aktualisierungsintervall für Cloud-Daten (seltenere Änderungen wie Tarife)
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_CLOUD),
        )
        self.token = token
        self.site_id = site_id
        # ClientSession wird von Home Assistant zentral verwaltet
        self.session = async_get_clientsession(hass)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Ruft die neuesten Daten von der neoom AI Cloud ab.

        Wird vom DataUpdateCoordinator in den konfigurierten Intervallen (DEFAULT_SCAN_INTERVAL_CLOUD) aufgerufen.

        Returns:
            Ein Dictionary mit den gesammelten Daten (z.B. 'site' und 'flow').
            
        Raises:
            UpdateFailed: Wenn beim Abruf der Daten ein Netzwerkfehler aufgetreten ist.
            ConfigEntryAuthFailed: Wenn das Token ungültig ist (Status 401).
        """
        try:
            # Setze ein asynchrones Timeout von 10 Sekunden für alle Cloud-Anfragen,
            # um zu verhindern, dass die Update-Schleife blockiert wird, wenn die Server langsam antworten.
            async with asyncio.timeout(10):
                headers = {"Authorization": f"Bearer {self.token}"}
                
                # 1. Allgemeine Site-Informationen abrufen (enthält u.a. Tarife, Adressen, etc.)
                url_site = f"{CLOUD_API_URL}/sites/{self.site_id}"
                async with self.session.get(url_site, headers=headers) as resp:
                    if resp.status == 401:
                        # Ein 401-Fehler deutet auf ein ungültiges Token hin.
                        # Wir werfen ConfigEntryAuthFailed, damit HA den Benutzer zur erneuten Anmeldung auffordert.
                        raise ConfigEntryAuthFailed("neoom AI Cloud Token ist ungültig oder abgelaufen.")
                    
                    # Bei anderen HTTP-Fehlern (4xx, 5xx) wirft raise_for_status eine Exception.
                    resp.raise_for_status()
                    site_data: Dict[str, Any] = await resp.json()

                # 2. Den letzten Energiefluss abrufen (aktuelle Übersichtswerte wie Gesamtverbrauch etc.)
                url_flow = f"{CLOUD_API_URL}/sites/{self.site_id}/energy-flow/latest"
                async with self.session.get(url_flow, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("neoom AI Cloud Token ist ungültig oder abgelaufen.")
                    resp.raise_for_status()
                    flow_data: Dict[str, Any] = await resp.json()

            # Wir bündeln beide API-Antworten in einem einzigen Dictionary,
            # das dann unseren Entitäten über `coordinator.data` zur Verfügung steht.
            return {
                "site": site_data,
                "flow": flow_data
            }

        except ConfigEntryAuthFailed:
            raise
        except aiohttp.ClientError as err:
            # Fängt alle Fehler ab, die während der HTTP-Kommunikation auftreten
            # (z.B. Verbindungsabbrüche, DNS-Probleme).
            raise UpdateFailed(f"Fehler bei der Kommunikation mit der neoom AI API: {err}") from err
        except TimeoutError as err:
            # Fängt Überschreitungen des asyncio.timeout ab
            raise UpdateFailed("Timeout bei der Verbindung zur neoom AI API.") from err

    async def close(self) -> None:
        """Schließen-Methode (Session wird von Home Assistant verwaltet)."""
        pass


class NeoomLocalCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Koordinator für den Abruf von lokalen Live-Daten vom BEAAM Gateway."""

    def __init__(self, hass: HomeAssistant, ip: str, key: str) -> None:
        """Initialisiert den lokalen Koordinator.

        Args:
            hass: Die Home Assistant Instanz.
            ip: Die IP-Adresse des lokalen BEAAM Gateways.
            key: Der Local-API-Key für die Authentifizierung.
        """
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_local",
            # Häufigeres Update-Intervall für echtzeitnahe Energiedaten.
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_LOCAL),
        )
        self.ip = ip
        self.key = key
        self.session = async_get_clientsession(hass)
        
        # Speichert die statische Konfiguration des Gateways,
        # da sich die Struktur der angebundenen Geräte (Wechselrichter, Speicher) 
        # selten ändert und nicht bei jedem Zyklus neu geladen werden muss.
        self.beaam_config: Optional[Dict[str, Any]] = None

    async def _ensure_config_loaded(self) -> None:
        """Stellt sicher, dass die Gerätestruktur ("Konfiguration") vom Gateway geladen wurde.
        
        Diese Konfiguration enhält Informationen über alle verbundenden Geräte ("Things")
        und ihre verfügbaren Datenpunkte ("DataPoints").
        Diese Methode ruft die API nur dann auf, wenn `self.beaam_config` noch leer (None) ist.
        """
        if self.beaam_config is not None:
            return  # Konfiguration is bereits geladen

        url = f"http://{self.ip}/api/v1/site/configuration"
        headers = {"Authorization": f"Bearer {self.key}"}
        
        try:
            # Längeres Timeout für den initialen Konfigurationsabruf
            async with asyncio.timeout(10):
                async with self.session.get(url, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Lokaler BEAAM API Key ist ungültig oder abgewiesen.")
                    
                    resp.raise_for_status()
                    config = await resp.json()
                    
                    # Inject virtual OPERATING_MODE_SG_READY datapoint for HEAT_PUMP things if missing
                    if config and "things" in config:
                        for thing_id, thing_data in config["things"].items():
                            if thing_data and thing_data.get("type") == "HEAT_PUMP":
                                datapoints = thing_data.setdefault("dataPoints", {})
                                sg_ready_exists = any(dp.get("key") == "OPERATING_MODE_SG_READY" for dp in datapoints.values())
                                if not sg_ready_exists:
                                    virtual_dp_id = f"{thing_id}_operating_mode_sg_ready"
                                    datapoints[virtual_dp_id] = {
                                        "key": "OPERATING_MODE_SG_READY",
                                        "dataType": "STRING",
                                        "unitOfMeasure": "None",
                                        "controllable": True
                                    }
                                    LOGGER.warning("Injected virtual OPERATING_MODE_SG_READY for HEAT_PUMP: %s", thing_id)
                    
                    self.beaam_config = config
                    LOGGER.debug("BEAAM Konfiguration (Gerätestruktur) erfolgreich geladen.")
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            # Wird an die aufrufende Methode (_async_update_data) weitergereicht.
            raise UpdateFailed(f"Konnte BEAAM Konfiguration nicht laden: {err}") from err

    async def _fetch_thing_state(self, thing_id: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Hilfsfunktion: Ruft den detaillierten Status eines einzelnen Geräts ('Thing') auf dem BEAAM ab."""
        url = f"http://{self.ip}/api/v1/things/{thing_id}/states"
        try:
            async with asyncio.timeout(5):
                async with self.session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as err:
            LOGGER.debug("Konnte Status für Thing '%s' nicht abrufen: %s", thing_id, err)
        return None

    async def _fetch_thing_settings(self, thing_id: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Hilfsfunktion: Ruft die Einstellungen eines einzelnen Geräts ('Thing') auf dem BEAAM ab."""
        url = f"http://{self.ip}/api/v1/things/{thing_id}/settings"
        try:
            async with asyncio.timeout(5):
                async with self.session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as err:
            LOGGER.debug("Konnte Einstellungen für Thing '%s' nicht abrufen: %s", thing_id, err)
        return None

    async def _async_update_data(self) -> Dict[str, Any]:
        """Ruft die Echtzeit-Statusdaten vom BEAAM Gateway ab."""
        await self._ensure_config_loaded()

        headers = {"Authorization": f"Bearer {self.key}"}
        state_map: Dict[str, Any] = {}
        settings_map: Dict[str, Dict[str, Any]] = {}

        try:
            async with asyncio.timeout(20):
                # 1. Globalen Site-Status abrufen
                url_site = f"http://{self.ip}/api/v1/site/state"
                try:
                    async with self.session.get(url_site, headers=headers) as resp:
                        if resp.status == 401:
                            raise ConfigEntryAuthFailed("Lokaler BEAAM API Key ist ungültig.")
                        resp.raise_for_status()
                        site_data: Dict[str, Any] = await resp.json()
                        
                        if isinstance(site_data, dict) and "energyFlow" in site_data:
                            energy_flow = site_data.get("energyFlow")
                            if isinstance(energy_flow, dict) and "states" in energy_flow:
                                states_list = energy_flow.get("states")
                                if isinstance(states_list, list):
                                    for item in states_list:
                                        if isinstance(item, dict):
                                            dp_id = item.get("dataPointId")
                                            key = item.get("key")
                                            if dp_id is not None:
                                                state_map[str(dp_id)] = item
                                            if key is not None:
                                                state_map[f"energyFlow_{key}"] = item
                except ConfigEntryAuthFailed:
                    raise
                except Exception as err:
                    LOGGER.warning("Fehler beim Abrufen des globalen Site-Status (site/state): %s. Versuche dennoch, den Status der einzelnen Geräte abzurufen.", err)

                # 2. Detail-Status und Einstellungen für einzelne Geräte ("Things") abrufen
                if self.beaam_config and "things" in self.beaam_config and isinstance(self.beaam_config["things"], dict):
                    tasks_states: List[asyncio.Task[Optional[Dict[str, Any]]]] = []
                    tasks_settings: List[asyncio.Task[Optional[Dict[str, Any]]]] = []
                    thing_ids = list(self.beaam_config["things"].keys())
                    
                    for thing_id in thing_ids:
                        tasks_states.append(
                            asyncio.create_task(
                                self._fetch_thing_state(thing_id, headers)
                            )
                        )
                        tasks_settings.append(
                            asyncio.create_task(
                                self._fetch_thing_settings(thing_id, headers)
                            )
                        )
                    
                    if thing_ids:
                        results_states = await asyncio.gather(*tasks_states, return_exceptions=True)
                        results_settings = await asyncio.gather(*tasks_settings, return_exceptions=True)
                        
                        for thing_id, res in zip(thing_ids, results_states):
                            if isinstance(res, dict) and "states" in res:
                                states_list = res.get("states")
                                if isinstance(states_list, list):
                                    for item in states_list:
                                        if isinstance(item, dict):
                                            dp_id = item.get("dataPointId")
                                            key = item.get("key")
                                            if dp_id is not None:
                                                state_map[str(dp_id)] = item
                                            if key is not None:
                                                state_map[f"{thing_id}_{key}"] = item
                        
                        for thing_id, res in zip(thing_ids, results_settings):
                            if isinstance(res, dict) and "settings" in res:
                                settings_list = res.get("settings")
                                if isinstance(settings_list, list):
                                    settings_map[thing_id] = {
                                        s["key"]: s["value"]
                                        for s in settings_list
                                        if isinstance(s, dict) and s.get("key") is not None and "value" in s
                                    }

                return {
                    "config": self.beaam_config,
                    "states": state_map,
                    "settings": settings_map
                }

        except ConfigEntryAuthFailed:
            raise
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Kommunikationsfehler (Netzwerk/HTTP) mit BEAAM Gateway: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed("Timeout beim Erfassen lokaler Daten via BEAAM.") from err


    async def async_send_command(self, thing_id: str, key: str, value: Any) -> None:
        """Sendet einen Steuerungsbefehl an die BEAAM API."""
        url = f"http://{self.ip}/api/v1/things/{thing_id}/commands"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }
        
        payload = [
            {
                "key": key,
                "value": value
            }
        ]
        
        LOGGER.debug("Sende Befehl an lokales BEAAM Gerät '%s': '%s' = '%s'", thing_id, key, value)
        
        try:
            async with asyncio.timeout(10):
                async with self.session.post(url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    LOGGER.info("Befehl an BEAAM erfolgreich gesendet: %s -> %s", key, value)
                    await self.async_request_refresh()
        except Exception as err:
            LOGGER.error("Schwerwiegender Fehler beim Senden des Befehls an '%s': %s", thing_id, err)
            raise

    async def async_ingest_state(self, thing_id: str, key: str, value: Any) -> None:
        """Sendet (ingests) einen Sensorwert an ein generisches Gerät im BEAAM Gateway."""
        url = f"http://{self.ip}/api/v1/things/{thing_id}/states"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }
        
        payload = [
            {
                "key": key,
                "value": value
            }
        ]
        
        LOGGER.debug("Sende State-Ingest an lokales BEAAM Gerät '%s': '%s' = '%s'", thing_id, key, value)
        
        try:
            async with asyncio.timeout(10):
                async with self.session.post(url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    LOGGER.info("State-Ingest an BEAAM erfolgreich gesendet: %s -> %s", key, value)
                    await self.async_request_refresh()
        except Exception as err:
            LOGGER.error("Schwerwiegender Fehler beim Senden des States an '%s': %s", thing_id, err)
            raise

    async def async_send_setting(self, thing_id: str, key: str, value: Any) -> None:
        """Sendet eine Einstellungsänderung an die BEAAM API."""
        url = f"http://{self.ip}/api/v1/things/{thing_id}/settings"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }
        
        api_value = value
        if isinstance(value, bool):
            api_value = "true" if value else "false"
        elif isinstance(value, (int, float)):
            if value == int(value):
                api_value = str(int(value))
            else:
                api_value = str(value)
        elif isinstance(value, str):
            if value.lower() == "true":
                api_value = "true"
            elif value.lower() == "false":
                api_value = "false"
            else:
                api_value = value
        else:
            api_value = str(value)

        payload = [
            {
                "key": key,
                "value": api_value
            }
        ]
        
        LOGGER.info("Sende Einstellung an lokales BEAAM Gerät '%s': '%s' = '%s' (Roh: %s)", thing_id, key, api_value, value)
        
        try:
            async with asyncio.timeout(10):
                async with self.session.put(url, headers=headers, json=payload) as resp:
                    response_text = await resp.text()
                    LOGGER.info("BEAAM Antwort erhalten (Status: %s): %s", resp.status, response_text)
                    resp.raise_for_status()
                    LOGGER.info("Einstellung an BEAAM erfolgreich gesendet: %s -> %s", key, api_value)
                    
                    if self.data:
                        if "settings" not in self.data:
                            self.data["settings"] = {}
                        if thing_id not in self.data["settings"]:
                            self.data["settings"][thing_id] = {}
                        self.data["settings"][thing_id][key] = api_value

                    self.async_update_listeners()
                    await asyncio.sleep(1.5)
                    await self.async_request_refresh()
        except Exception as err:
            LOGGER.error("Schwerwiegender Fehler beim Senden der Einstellung an '%s': %s", thing_id, err)
            raise

    async def close(self) -> None:
        """Schließen-Methode (Session wird von Home Assistant verwaltet)."""
        pass
