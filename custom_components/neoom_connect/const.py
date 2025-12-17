"""Konstanten für neoom Connect."""

from logging import Logger, getLogger

# Logger Initialisierung für Debug-Zwecke
LOGGER: Logger = getLogger(__package__)

DOMAIN = "neoom_connect"
NAME = "neoom Connect"

# Konfigurations-Schlüssel (werden in der config_flow.py und __init__.py verwendet)
CONF_SITE_ID = "site_id"
CONF_BEAAM_IP = "beaam_ip"
CONF_BEAAM_KEY = "beaam_key"
CONF_CLOUD_TOKEN = "cloud_token"

# API Endpunkte
CLOUD_API_URL = "https://api.ntuity.io/v1"
LOCAL_API_PORT = 80 # Standard HTTP Port für das BEAAM Gateway

# Standard Aktualisierungsintervalle
DEFAULT_SCAN_INTERVAL_CLOUD = 300  # Alle 5 Minuten (Cloud-Daten ändern sich selten)
DEFAULT_SCAN_INTERVAL_LOCAL = 30   # Alle 30 Sekunden (für Live-Werte vom Gateway)