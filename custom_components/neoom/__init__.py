"""Die neoom AI Integration.

Diese Integration verbindet Home Assistant mit den Systemen von neoom.
Sie stellt eine hybride Verbindung her:
1. Eine Cloud-Verbindung zur neoom AI API für z.B. Tarifdaten (selten aktualisiert).
2. Eine lokale Netzwerkverbindung zum BEAAM Gateway für Live-Energiedaten (oft aktualisiert).
"""

from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_CLOUD_TOKEN,
    CONF_SITE_ID,
    CONF_BEAAM_IP,
    CONF_BEAAM_KEY,
    LOGGER,
)
from .coordinator import NeoomCloudCoordinator, NeoomLocalCoordinator

# Definiere die unterstützten Plattformen, die von dieser Integration geladen werden.
# Wir unterstützen Sensoren (nur-lesen), Number-Entitäten (Zahleneingabe/Slider)
# und Select-Entitäten (Dropdown-Menüs).
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Richtet eine neoom AI Instanz basierend auf einem Konfigurationseintrag ein.

    Diese Funktion wird aufgerufen, wenn der Benutzer die Integration über die UI
    hinzufügt (Config Flow abgeschlossen) oder wenn Home Assistant startet und
    die Integration bereits konfiguriert ist.

    Args:
        hass: Die Home Assistant Instanz.
        entry: Der Konfigurationseintrag (enthält die Zugangsdaten).

    Returns:
        True, wenn die Einrichtung erfolgreich war, sonst False.
    """

    LOGGER.debug("Starte das Setup für den neoom AI Eintrag: %s", entry.entry_id)

    # 1. Cloud Coordinator instanziieren
    # Der Cloud-Coordinator holt Daten von der neoom AI API.
    cloud_coordinator = NeoomCloudCoordinator(
        hass,
        token=entry.data[CONF_CLOUD_TOKEN],
        site_id=entry.data[CONF_SITE_ID],
    )

    # 2. Local Coordinator instanziieren
    # Der Local-Coordinator holt Echtzeit-Daten direkt vom lokalen BEAAM Gateway im Netzwerk.
    local_coordinator = NeoomLocalCoordinator(
        hass,
        ip=entry.data[CONF_BEAAM_IP],
        key=entry.data[CONF_BEAAM_KEY],
    )

    # Initiale Datenabfrage (Refresh) für beide Coordinators anstoßen
    # Wir rufen async_config_entry_first_refresh auf, um sicherzustellen,
    # dass beim Start von Home Assistant erste Daten vorhanden sind.
    await cloud_coordinator.async_config_entry_first_refresh()

    try:
        # Die lokale Abfrage könnte fehlschlagen, wenn das Gateway gerade offline ist.
        # Wir loggen den Fehler, lassen den Start aber nicht komplett scheitern.
        await local_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        LOGGER.warning(
            "Fehler beim initialen Abruf der lokalen BEAAM Daten: %s. "
            "Die Integration wird weiterhin mit den Cloud-Daten gestartet und versucht später einen Neuaufbau der Verbindung.",
            err,
        )

    # Bereite den Speicherort in hass.data für unsere Domain vor, falls noch nicht geschehen.
    hass.data.setdefault(DOMAIN, {})

    # Speichere unsere Coordinators unter der Eintrags-ID, damit die Plattformen (Sensor, Number)
    # später darauf zugreifen können.
    hass.data[DOMAIN][entry.entry_id] = {
        "cloud": cloud_coordinator,
        "local": local_coordinator,
    }

    # --- EXPLIZITE GERÄTE-REGISTRIERUNG ---
    # Wir registrieren das BEAAM Gateway vorab im Device Registry von Home Assistant.
    # Dies ist wichtig, da spätere Geräte (z.B. Wechselrichter, Batterie) über das Attribut
    # 'via_device' eine Verbindung aufbauen, um anzuzeigen, dass sie *über* das BEAAM Gerät kommunizieren.
    # Wenn das BEAAM-Gerät hier nicht existiert, warnt Home Assistant, dass ein ungültiges via_device
    # angegeben wurde.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "BEAAM Gateway")},  # Eindeutige ID für dieses Gerät.
        manufacturer="neoom",
        name="BEAAM Gateway",
        model="BEAAM Edge Controller",
        configuration_url=f"http://{entry.data[CONF_BEAAM_IP]}",
    )
    LOGGER.debug("BEAAM Gateway im Device Registry angelegt oder abgerufen.")

    # Weist Home Assistant an, die in PLATFORMS definierten Komponenten (Sensor, Number, Select)
    # asynchron für diesen Eintrag einzurichten.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    LOGGER.info("neoom AI Einrichtung erfolgreich abgeschlossen.")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entlädt einen Konfigurationseintrag.
    
    Wird aufgerufen, wenn der Benutzer die Integration über die UI löscht
    oder neu lädt. Räumt die verwendeten Ressourcen (z.B. HTTP-Sessions) auf.
    
    Args:
        hass: Die Home Assistant Instanz.
        entry: Der zu entladende Konfigurationseintrag.
        
    Returns:
        True, wenn das Entladen erfolgreich war.
    """
    
    # Entlade zuerst alle Plattformen (Sensor, Number, Select)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Wenn erfolgreich, entferne unsere gespeicherten Coordinators aus hass.data
        data: Dict[str, Any] = hass.data[DOMAIN].pop(entry.entry_id)
        
        # Schließe die HTTP-Sessions sauber
        await data["cloud"].close()
        await data["local"].close()
        
        LOGGER.info("neoom AI Eintrag %s erfolgreich entladen.", entry.entry_id)

    return unload_ok
