"""Config flow for Neoom Connect integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_SITE_ID, CONF_CLOUD_TOKEN, CONF_BEAAM_IP, CONF_BEAAM_KEY

_LOGGER = logging.getLogger(__name__)

class NeoomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Neoom Connect."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                # Hier könnten wir noch die Verbindung testen, bevor wir speichern.
                # Fürs erste speichern wir direkt, um Installationsprobleme zu vermeiden.
                _LOGGER.info("Creating Neoom Connect entry for site %s", user_input[CONF_SITE_ID])
                return self.async_create_entry(title="Neoom System", data=user_input)
            except Exception:
                _LOGGER.exception("Unexpected exception during config flow")
                errors["base"] = "unknown"

        data_schema = vol.Schema({
            vol.Required(CONF_CLOUD_TOKEN): str,
            vol.Required(CONF_SITE_ID): str,
            vol.Required(CONF_BEAAM_IP): str,
            vol.Required(CONF_BEAAM_KEY): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )