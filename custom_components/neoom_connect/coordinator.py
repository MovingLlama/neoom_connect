"""Daten-Aktualisierungs-Koordinatoren (DataUpdateCoordinators) für neoom Connect.

Diese Koordinatoren sind dafür verantwortlich, in regelmäßigen Abständen Daten
von den jeweiligen APIs (Ntuity Cloud und lokales BEAAM Gateway) abzurufen 
und diese dann den Sensoren und anderen Entitäten in Home Assistant zur Verfügung zu stellen.
Das verhindert, dass jede Entität eigene Netzwerk-Anfragen stellt, was die Systeme überlasten würde.
"""

import asyncio
from datetime import timedelta
from typing import Any, Dict, List, Optional

import aiohttp
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
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
    """Koordinator für den Abruf von Daten aus der Ntuity Cloud."""

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
        # ClientSession für asynchrone HTTP-Anfragen. Muss später geschlossen werden.
        self.session = aiohttp.ClientSession()

    async def _async_update_data(self) -> Dict[str, Any]:
        """Ruft die neuesten Daten von der Ntuity Cloud ab.

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
            async with async_timeout.timeout(10):
                headers = {"Authorization": f"Bearer {self.token}"}
                
                # 1. Allgemeine Site-Informationen abrufen (enthält u.a. Tarife, Adressen, etc.)
                url_site = f"{CLOUD_API_URL}/sites/{self.site_id}"
                async with self.session.get(url_site, headers=headers) as resp:
                    if resp.status == 401:
                        # Ein 401-Fehler deutet auf ein ungültiges Token hin.
                        # Wir werfen ConfigEntryAuthFailed, damit HA den Benutzer zur erneuten Anmeldung auffordert.
                        raise ConfigEntryAuthFailed("Ntuity Cloud Token ist ungültig oder abgelaufen.")
                    
                    # Bei anderen HTTP-Fehlern (4xx, 5xx) wirft raise_for_status eine Exception.
                    resp.raise_for_status()
                    site_data: Dict[str, Any] = await resp.json()

                # 2. Den letzten Energiefluss abrufen (aktuelle Übersichtswerte wie Gesamtverbrauch etc.)
                url_flow = f"{CLOUD_API_URL}/sites/{self.site_id}/energy-flow/latest"
                async with self.session.get(url_flow, headers=headers) as resp:
                    resp.raise_for_status()
                    flow_data: Dict[str, Any] = await resp.json()

            # Wir bündeln beide API-Antworten in einem einzigen Dictionary,
            # das dann unseren Entitäten über `coordinator.data` zur Verfügung steht.
            return {
                "site": site_data,
                "flow": flow_data
            }

        except aiohttp.ClientError as err:
            # Fängt alle Fehler ab, die während der HTTP-Kommunikation auftreten
            # (z.B. Verbindungsabbrüche, DNS-Probleme).
            raise UpdateFailed(f"Fehler bei der Kommunikation mit der Ntuity API: {err}") from err
        except asyncio.TimeoutError as err:
            # Fängt Überschreitungen des async_timeout ab
            raise UpdateFailed("Timeout bei der Verbindung zur Ntuity API.") from err

    async def close(self) -> None:
        """Schließt die aufrechterhaltene HTTP-Session.
        
        Sollte aufgerufen werden, wenn die Integration entladen wird,
        um Verbindungslecks (Resource Leaks) zu verhindern.
        """
        await self.session.close()


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
        self.session = aiohttp.ClientSession()
        
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
            return  # Konfiguration ist bereits geladen

        url = f"http://{self.ip}/api/v1/site/configuration"
        headers = {"Authorization": f"Bearer {self.key}"}
        
        try:
            # Längeres Timeout für den initialen Konfigurationsabruf
            async with async_timeout.timeout(10):
                async with self.session.get(url, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Lokaler BEAAM API Key ist ungültig oder abgewiesen.")
                    
                    resp.raise_for_status()
                    self.beaam_config = await resp.json()
                    LOGGER.info("BEAAM Konfiguration (Gerätestruktur) erfolgreich geladen.")
        except Exception as err:
            # Wird an die aufrufende Methode (_async_update_data) weitergereicht.
            raise UpdateFailed(f"Konnte BEAAM Konfiguration nicht laden: {err}") from err

    async def _fetch_thing_state(self, thing_id: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Hilfsfunktion: Ruft den detaillierten Status eines einzelnen Geräts ('Thing') auf dem BEAAM ab.

        Args:
            thing_id: Die eindeutige ID des Geräts (aus der Konfiguration).
            headers: Authorization-Header für die API.

        Returns:
            Das vom Gateway zurückgegebene Dictionary mit den Gerätestatusdaten,
            oder None, wenn der Aufruf fehlschlägt.
        """
        url = f"http://{self.ip}/api/v1/things/{thing_id}/states"
        try:
            # Wir geben einzelnen Geräten einen kurzen Timeout (5 Sekunden).
            # Wenn ein Gerät im rs485 Bus hängt, soll es nicht den Rest blockieren.
            async with async_timeout.timeout(5):
                async with self.session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as err:
            # Wir loggen den Fehler nur als DEBUG, um das Log nicht mit Fehlern unzugänglicher Geräte zu fluten.
            # Das Gerät wird in diesem Update-Zyklus ignoriert.
            LOGGER.debug("Konnte Status für Thing '%s' nicht abrufen: %s", thing_id, err)
        return None

    async def _async_update_data(self) -> Dict[str, Any]:
        """Ruft die Echtzeit-Statusdaten vom BEAAM Gateway ab.

        Der Ablauf ist:
        1. Stelle sicher, dass wir wissen, welche Geräte es gibt (Konfiguration laden).
        2. Hole den globalen "Site-State" (Zusammenfassung der Energieflüsse).
        3. Parallel: Hole detaillierte Statusdaten für alle bekannten Geräte einzeln.
        
        Returns:
            Ein Dictionary enthaltend die statische Konfiguration und
            eine Map (Wörterbuch) aller aktuellen Sensorwerte:
            {"config": {...}, "states": { "dataPointId": state_object, ... }}
            
        Raises:
            UpdateFailed: Bei allgemeinen Kommunikationsproblemen.
            ConfigEntryAuthFailed: Wenn die Zugangsdaten falsch sind.
        """
        # Stelle sicher, dass die Gerätestruktur im Speicher ist
        await self._ensure_config_loaded()

        headers = {"Authorization": f"Bearer {self.key}"}
        
        # In diesem Dictionary sammeln wir aggregiert alle Datenpunkte 
        # (egal ob sie von der Site-Übersicht oder von Detail-Abfragen stammen).
        # Key: dataPointId (die interne Sensor-ID), Value: Das komplette Objekt des Werts
        state_map: Dict[str, Any] = {}

        try:
            # Gesamt-Timeout für den gesamten Refresh-Zyklus
            async with async_timeout.timeout(20):
                
                # 1. Globalen Site-Status abrufen
                url_site = f"http://{self.ip}/api/v1/site/state"
                async with self.session.get(url_site, headers=headers) as resp:
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Lokaler BEAAM API Key ist ungültig.")
                    resp.raise_for_status()
                    site_data: Dict[str, Any] = await resp.json()
                    
                    # Extrahiere die übergeordneten Datenpunkte (Energy-Flow) aus der Antwort
                    if "energyFlow" in site_data and "states" in site_data["energyFlow"]:
                        for item in site_data["energyFlow"]["states"]:
                            state_map[item["dataPointId"]] = item

                # 2. Detail-Status für einzelne Geräte ("Things") abrufen
                # Wir sammeln alle API-Aufrufe als "Tasks" und starten sie dann gleichzeitig (parallel),
                # anstatt darauf zu warten, dass jedes Gerät nacheinander antwortet.
                if self.beaam_config and "things" in self.beaam_config:
                    tasks: List[asyncio.Task[Optional[Dict[str, Any]]]] = []
                    
                    for thing_id in self.beaam_config["things"]:
                        # Erstellt ein asynchrones Task-Objekt
                        tasks.append(
                            asyncio.create_task(
                                self._fetch_thing_state(thing_id, headers)
                            )
                        )
                    
                    if tasks:
                        # asyncio.gather wartet, bis alle Tasks beendet sind.
                        # Rückgabe ist eine Liste der Resultate jedes Tasks (Gleiche Reihenfolge wie in `tasks`).
                        results = await asyncio.gather(*tasks)
                        
                        # Verarbeite die Ergebnisse und mittle sie in die state_map ein
                        for res in results:
                            if res and "states" in res:
                                for item in res["states"]:
                                    state_map[item["dataPointId"]] = item

                # Returniere die fertige Datenstruktur für unsere Entitäts-Klassen
                return {
                    "config": self.beaam_config,
                    "states": state_map
                }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Kommunikationsfehler (Netzwerk/HTTP) mit BEAAM Gateway: {err}") from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed("Timeout beim Erfassen lokaler Daten via BEAAM.") from err


    async def async_send_command(self, thing_id: str, key: str, value: Any) -> None:
        """Sendet einen Steuerungsbefehl an die BEAAM API (ändert z.B. einen Wert am Wechselrichter).
        
        Wird beispielsweise von Number- (Slider) oder Select-Entitäten aufgerufen.

        Args:
            thing_id: Die eindeutige ID des Zielgeräts.
            key: Der Name (Key) des Parameters, der geändert werden soll (z.B. "TARGET_POWER").
            value: Der neue Zielwert. Kann numerisch oder Text sein, je nach Parameter.
            
        Raises:
            Exception: Wenn der der HTTP-Aufruf nicht erfolgreich ist (Statuscode ungleich 2xx) oder ein Timeout auftritt.
        """
        url = f"http://{self.ip}/api/v1/things/{thing_id}/commands"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }
        
        # Die BEAAM API erwartet eine Liste von Befehlen als JSON Array
        payload = [
            {
                "key": key,
                "value": value
            }
        ]
        
        LOGGER.debug("Sende Befehl an lokales BEAAM Gerät '%s': '%s' = '%s'", thing_id, key, value)
        
        try:
            async with async_timeout.timeout(10):
                async with self.session.post(url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    LOGGER.info("Befehl an BEAAM erfolgreich gesendet: %s -> %s", key, value)
                    
                    # Wenn wir einen Wert erfolgreich geschrieben haben, signalisieren wir 
                    # dem Koordinator, dass er sofort frische Daten vom Gateway holen soll.
                    # Dadurch kann die Home Assistant Oberfläche den geänderten Wert ohne
                    # große Verzögerung anziegen.
                    await self.async_request_refresh()
        except Exception as err:
            LOGGER.error("Schwerwiegender Fehler beim Senden des Befehls an '%s': %s", thing_id, err)
            raise

    async def close(self) -> None:
        """Schließt die aufrechterhaltene HTTP-Session."""
        await self.session.close()
