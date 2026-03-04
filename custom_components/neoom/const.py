"""Konstanten für die neoom AI Integration."""

from logging import Logger, getLogger

# Zentraler Logger für die gesamte Integration, erleichtert das Debugging.
LOGGER: Logger = getLogger(__package__)

# Der eindeutige Bezeichner (Domain) der Integration in Home Assistant.
DOMAIN: str = "neoom"

# Der Anzeigename der Integration in der Benutzeroberfläche.
NAME: str = "neoom AI"

# --- Konfigurations-Schlüssel ---
# Diese Schlüssel werden im Config Flow (`config_flow.py`) abgefragt
# und in den Eintragsdaten (`entry.data` in `__init__.py`) gespeichert.

# Die eindeutige ID des Standorts (Site) in der neoom AI Cloud.
CONF_SITE_ID: str = "site_id"

# Das Bearer-Token für die Authentifizierung an der neoom AI Cloud API.
CONF_CLOUD_TOKEN: str = "cloud_token"

# Die lokale IP-Adresse des BEAAM Gateways in Ihrem Netzwerk.
CONF_BEAAM_IP: str = "beaam_ip"

# Der API-Schlüssel (Token) für den lokalen Zugriff auf das BEAAM Gateway.
CONF_BEAAM_KEY: str = "beaam_key"


# --- API Endpunkte und Ports ---

# Die Basis-URL für die neoom AI Cloud API (Version 1).
CLOUD_API_URL: str = "https://api.ntuity.io/v1"

# Der Standard-Port für HTTP-Anfragen an das lokale BEAAM Gateway.
# Wird aktuell nicht explizit in den URLs verwendet (da 80 implizit ist),
# dient aber der Dokumentation.
LOCAL_API_PORT: int = 80


# --- Standard Aktualisierungsintervalle ---

# Das Intervall in Sekunden, in dem Daten aus der Cloud abgerufen werden.
# Da sich diese Daten (wie Preise oder Tarife) selten ändern, genügen 5 Minuten.
DEFAULT_SCAN_INTERVAL_CLOUD: int = 300  

# Das Intervall in Sekunden, in dem Live-Daten vom lokalen BEAAM Gateway
# abgerufen werden. Ein kurzer Intervall ist wichtig für Live-Energieflüsse.
DEFAULT_SCAN_INTERVAL_LOCAL: int = 15
