"""Konfigurationsfluss (Config Flow) für die neoom Connect Integration.

Diese Datei steuert den Einrichtungsassistenten, der dem Benutzer in der
Home Assistant Oberfläche angezeigt wird, wenn er die Integration hinzufügt.
"""

from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_SITE_ID,
    CONF_CLOUD_TOKEN,
    CONF_BEAAM_IP,
    CONF_BEAAM_KEY,
    LOGGER,
)


class NeoomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Behandelt den Konfigurationsfluss für neoom Connect.
    
    Diese Klasse erbt von ConfigFlow und definiert die Schritte, die der User
    durchlaufen muss, um die Integration zu konfigurieren.
    """

    # Version des Konfigurationsschemas. Nützlich für zukünftige Migrationen.
    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Behandelt den ersten Schritt der Einrichtung (Benutzereingabe).
        
        Wenn `user_input` None ist, wird das leere Formular angezeigt.
        Wenn `user_input` Daten enthält, werden diese verarbeitet und
        der Konfigurationseintrag erstellt.
        
        Args:
            user_input: Die vom Benutzer im Formular eingegebenen Daten.
            
        Returns:
            Ein FlowResult, das entweder das Formular anzeigt oder den Eintrag erstellt.
        """
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Hier könnten wir theoretisch die Verbindung testen (z.B. einen Test-API-Aufruf machen),
            # bevor wir die Daten speichern. Im Moment vertrauen wir den Eingaben
            # und speichern sie direkt ab.
            try:
                LOGGER.info(
                    "Erstelle neoom Connect Eintrag für Site ID: %s",
                    user_input[CONF_SITE_ID],
                )
                
                # Erstellt den Eintrag in der Home Assistant Registry.
                # 'title' ist der Name, der in der Integrationsübersicht angezeigt wird.
                return self.async_create_entry(
                    title="neoom System", 
                    data=user_input
                )
            except Exception as e:
                LOGGER.exception("Unerwarteter Fehler im Config Flow: %s", e)
                # 'base' bezieht sich auf das Formular als Ganzes, nicht auf ein spezielles Feld.
                errors["base"] = "unknown"

        # Schema für das Eingabeformular in der UI definieren.
        # vol.Required bedeutet, dass das Feld ausgefüllt werden muss.
        # Der Typ 'str' gibt an, dass es sich um einen Text handelt.
        data_schema = vol.Schema(
            {
                vol.Required(CONF_CLOUD_TOKEN): str,  # Ntuity Bearer Token
                vol.Required(CONF_SITE_ID): str,      # UUID der Site
                vol.Required(CONF_BEAAM_IP): str,     # IP-Adresse des lokalen Gateways
                vol.Required(CONF_BEAAM_KEY): str,    # API Key für lokales Gateway
            }
        )

        # Zeigt das Formular mit dem definierten Schema und eventuellen Fehlern an.
        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors
        )
