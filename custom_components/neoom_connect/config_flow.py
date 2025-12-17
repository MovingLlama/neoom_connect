"""Config flow for Neoom Connect integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_SITE_ID, CONF_CLOUD_TOKEN, CONF_BEAAM_IP, CONF_BEAAM_KEY

class NeoomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Neoom Connect."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate input here if needed (e.g. check if IP is reachable)
            # For now, we trust the user and just create the entry
            return self.async_create_entry(title="Neoom System", data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_CLOUD_TOKEN): str,
            vol.Required(CONF_SITE_ID): str,
            vol.Required(CONF_BEAAM_IP): str,
            vol.Required(CONF_BEAAM_KEY): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )