"""Die neoom AI Integration.

Diese Integration verbindet Home Assistant mit den Systemen von neoom.
Sie stellt eine hybride Verbindung her:
1. Eine Cloud-Verbindung zur neoom AI API für z.B. Tarifdaten (selten aktualisiert).
2. Eine lokale Netzwerkverbindung zum BEAAM Gateway für Live-Energiedaten (oft aktualisiert).
"""

from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_CLOUD_TOKEN,
    CONF_SITE_ID,
    CONF_BEAAM_IP,
    CONF_BEAAM_KEY,
    CONF_SCAN_INTERVAL_CLOUD,
    CONF_SCAN_INTERVAL_LOCAL,
    DEFAULT_SCAN_INTERVAL_CLOUD,
    DEFAULT_SCAN_INTERVAL_LOCAL,
    LOGGER,
)
from .coordinator import NeoomCloudCoordinator, NeoomLocalCoordinator

# Definiere die unterstützten Plattformen, die von dieser Integration geladen werden.
# Wir unterstützen Sensoren (nur-lesen), Number-Entitäten (Zahleneingabe/Slider),
# Select-Entitäten (Dropdown-Menüs), Switch-Entitäten (Schalter) und Time-Entitäten (Uhrzeiten).
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SWITCH, Platform.TIME]


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

    # Lese Zugangsdaten und Optionen aus entry.options (Fallback auf entry.data)
    cloud_token = entry.options.get(CONF_CLOUD_TOKEN, entry.data.get(CONF_CLOUD_TOKEN, ""))
    site_id = entry.data.get(CONF_SITE_ID, "")
    beaam_ip = entry.options.get(CONF_BEAAM_IP, entry.data.get(CONF_BEAAM_IP, ""))
    beaam_key = entry.options.get(CONF_BEAAM_KEY, entry.data.get(CONF_BEAAM_KEY, ""))
    scan_interval_cloud = entry.options.get(CONF_SCAN_INTERVAL_CLOUD, DEFAULT_SCAN_INTERVAL_CLOUD)
    scan_interval_local = entry.options.get(CONF_SCAN_INTERVAL_LOCAL, DEFAULT_SCAN_INTERVAL_LOCAL)

    # 1. Cloud Coordinator instanziieren
    # Der Cloud-Coordinator holt Daten von der neoom AI API.
    cloud_coordinator = NeoomCloudCoordinator(
        hass,
        token=cloud_token,
        site_id=site_id,
        scan_interval=scan_interval_cloud,
    )

    # 2. Local Coordinator instanziieren
    # Der Local-Coordinator holt Echtzeit-Daten direkt vom lokalen BEAAM Gateway im Netzwerk.
    local_coordinator = NeoomLocalCoordinator(
        hass,
        ip=beaam_ip,
        key=beaam_key,
        scan_interval=scan_interval_local,
    )

    # Initiale Datenabfrage (Refresh) für beide Coordinators anstoßen
    # Wir rufen async_config_entry_first_refresh auf, um sicherzustellen,
    # dass beim Start von Home Assistant erste Daten vorhanden sind.
    await cloud_coordinator.async_config_entry_first_refresh()

    try:
        await local_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        LOGGER.warning(
            "Fehler beim initialen Abruf der lokalen BEAAM Daten (%s). "
            "Setze Einrichtung aus: Home Assistant unternimmt automatische Wiederholungsversuche.",
            err,
        )
        raise ConfigEntryNotReady(f"BEAAM Gateway unter {beaam_ip} nicht erreichbar: {err}") from err

    # Bereite den Speicherort in hass.data für unsere Domain vor, falls noch nicht geschehen.
    hass.data.setdefault(DOMAIN, {})

    # Speichere unsere Coordinators unter der Eintrags-ID, damit die Plattformen (Sensor, Number)
    # später darauf zugreifen können.
    hass.data[DOMAIN][entry.entry_id] = {
        "cloud": cloud_coordinator,
        "local": local_coordinator,
    }

    # Listener für Optionen-Updates registrieren (z.B. geänderte Intervalle über das Zahnrad-Menü)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # --- EXPLIZITE GERÄTE-REGISTRIERUNG ---
    # Wir registrieren das BEAAM Gateway vorab im Device Registry von Home Assistant.
    # Dies ist wichtig, da spätere Geräte (z.B. Wechselrichter, Batterie) über das Attribut
    # 'via_device' eine Verbindung aufbauen, um anzuzeigen, dass sie *über* das BEAAM Gerät kommunizieren.
    # Wenn das BEAAM-Gerät hier nicht existiert, warnt Home Assistant, dass ein ungültiges via_device
    # angegeben wurde.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "BEAAM Gateway"), (DOMAIN, f"beaam_{entry.data.get(CONF_SITE_ID, entry.entry_id)}")},
        manufacturer="neoom",
        name="BEAAM Gateway",
        model="BEAAM Edge Controller",
        configuration_url=f"http://{beaam_ip}",
    )
    LOGGER.debug("BEAAM Gateway im Device Registry angelegt oder abgerufen.")

    # Weist Home Assistant an, die in PLATFORMS definierten Komponenten (Sensor, Number, Select)
    # asynchron für diesen Eintrag einzurichten.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- SERVICE REGISTRIERUNG ---
    async def handle_ingest_state(call: ServiceCall) -> None:
        """Behandelt den Aufruf des ingest_state Dienstes."""
        thing_id = call.data.get("thing_id")
        key = call.data.get("key")
        value = call.data.get("value")
        
        # Sende den Wert an das zuständige BEAAM Gateway
        sent = False
        for entry_id, coordinators in hass.data.get(DOMAIN, {}).items():
            loc_coord = coordinators.get("local")
            if loc_coord:
                # Prüfe, ob das Thing diesem Gateway bekannt ist, oder sende wenn nur 1 Gateway existiert
                known_things = (loc_coord.beaam_config or {}).get("things", {})
                if thing_id in known_things or len(hass.data.get(DOMAIN, {})) == 1:
                    try:
                        await loc_coord.async_ingest_state(thing_id, key, value)
                        sent = True
                    except Exception as err:
                        LOGGER.error("Fehler beim Senden von State-Ingest für Eintrag %s: %s", entry_id, err)
        
        if not sent:
            LOGGER.warning("Thing '%s' wurde in keinem konfigurierten BEAAM Gateway gefunden.", thing_id)

    if not hass.services.has_service(DOMAIN, "ingest_state"):
        hass.services.async_register(
            DOMAIN,
            "ingest_state",
            handle_ingest_state,
            schema=vol.Schema({
                vol.Required("thing_id"): cv.string,
                vol.Required("key"): cv.string,
                vol.Required("value"): vol.Any(cv.string, vol.Coerce(float)),
            })
        )

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
        
        # Entferne den Service, wenn kein weiterer neoom-Eintrag mehr existiert
        if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, "ingest_state"):
            hass.services.async_remove(DOMAIN, "ingest_state")

        LOGGER.info("neoom AI Eintrag %s erfolgreich entladen.", entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Lädt den Konfigurationseintrag neu, wenn Optionen geändert wurden."""
    await hass.config_entries.async_reload(entry.entry_id)

