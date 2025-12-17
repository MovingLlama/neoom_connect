"""Constants for Neoom Connect."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "neoom_connect"
NAME = "neoom Connect"

# Configuration Keys
CONF_SITE_ID = "site_id"
CONF_BEAAM_IP = "beaam_ip"
CONF_BEAAM_KEY = "beaam_key"
CONF_CLOUD_TOKEN = "cloud_token"

# API Endpoints
CLOUD_API_URL = "https://api.ntuity.io/v1"
LOCAL_API_PORT = 80 # Assuming port 80 based on standard HTTP

# Defaults
DEFAULT_SCAN_INTERVAL_CLOUD = 300  # 5 Minutes
DEFAULT_SCAN_INTERVAL_LOCAL = 30   # 30 Seconds