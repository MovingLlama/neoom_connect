"""Konfigurationsfluss für die neoom Connect Integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_SITE_ID, CONF_CLOUD_TOKEN, CONF_BEAAM_IP, CONF_BEAAM_KEY

_LOGGER = logging.getLogger(__name__)

class NeoomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Behandelt den Konfigurationsfluss für neoom Connect."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Behandelt den ersten Schritt der Einrichtung (Benutzereingabe)."""
        errors = {}

        if user_input is not None:
            try:
                # Hier könnten wir theoretisch die Verbindung testen.
                # Wir loggen die Erstellung und speichern die Daten.
                _LOGGER.info("Erstelle neoom Connect Eintrag für Site %s", user_input[CONF_SITE_ID])
                return self.async_create_entry(title="neoom System", data=user_input)
            except Exception:
                _LOGGER.exception("Unerwarteter Fehler im Config Flow")
                errors["base"] = "unknown"

        # Schema für das Eingabeformular in der UI
        data_schema = vol.Schema({
            vol.Required(CONF_CLOUD_TOKEN): str, # Ntuity Bearer Token
            vol.Required(CONF_SITE_ID): str,     # UUID der Site
            vol.Required(CONF_BEAAM_IP): str,    # IP-Adresse des lokalen Gateways
            vol.Required(CONF_BEAAM_KEY): str,   # API Key für lokales Gateway
        })

        # Zeige das Formular an
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )