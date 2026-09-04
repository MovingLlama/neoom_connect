"""Konfigurationsfluss (Config Flow) & Optionen-Fluss für die neoom AI Integration.

Diese Datei steuert den Einrichtungsassistenten, der dem Benutzer in der
Home Assistant Oberfläche angezeigt wird, wenn er die Integration hinzufügt,
über das Zahnrad konfiguriert oder reauthentifiziert.
"""

import asyncio
from collections.abc import Mapping
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_SITE_ID,
    CONF_CLOUD_TOKEN,
    CONF_BEAAM_IP,
    CONF_BEAAM_KEY,
    CONF_SCAN_INTERVAL_CLOUD,
    CONF_SCAN_INTERVAL_LOCAL,
    DEFAULT_SCAN_INTERVAL_CLOUD,
    DEFAULT_SCAN_INTERVAL_LOCAL,
    CLOUD_API_URL,
    LOGGER,
)


def _clean_ip(ip_str: str) -> str:
    """Bereinigt eine eingegebene IP-Adresse oder Hostnamen von Präfixen und Slashes."""
    return ip_str.strip().removeprefix("http://").removeprefix("https://").rstrip("/")


class NeoomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Behandelt den Konfigurationsfluss für neoom AI.
    
    Diese Klasse erbt von ConfigFlow und definiert die Schritte, die der User
    durchlaufen muss, um die Integration zu konfigurieren oder zu reauthentifizieren.
    """

    # Version des Konfigurationsschemas. Nützlich für zukünftige Migrationen.
    VERSION = 1

    def __init__(self) -> None:
        """Initialisierung des Config Flows."""
        self.user_data: Dict[str, Any] = {}
        self.sites_dict: Dict[str, str] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Aktiviert das Zahnrad (Optionen-Menü) in der Home Assistant UI."""
        return NeoomOptionsFlowHandler()

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Behandelt den ersten Schritt der Einrichtung (Benutzereingabe)."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Bereinige die IP-Adresse
            user_input[CONF_BEAAM_IP] = _clean_ip(user_input[CONF_BEAAM_IP])
            self.user_data = user_input
            
            token = user_input[CONF_CLOUD_TOKEN]
            beaam_ip = user_input[CONF_BEAAM_IP]
            beaam_key = user_input[CONF_BEAAM_KEY]
            session = async_get_clientsession(self.hass)

            # 1. Cloud API aufrufen und Sites abfragen
            url_cloud = f"{CLOUD_API_URL}/sites"
            headers_cloud = {"Authorization": f"Bearer {token}"}
            
            try:
                async with asyncio.timeout(10):
                    async with session.get(url_cloud, headers=headers_cloud) as resp:
                        if resp.status == 401:
                            errors["base"] = "invalid_auth"
                        else:
                            resp.raise_for_status()
                            data = await resp.json()
                            
                            if isinstance(data, dict):
                                sites_list = data.get("items") or data.get("data") or data.get("sites", [])
                            else:
                                sites_list = data
                                
                            self.sites_dict = {}
                            if isinstance(sites_list, list):
                                for site in sites_list:
                                    if isinstance(site, dict):
                                        site_id = site.get("id") or site.get("siteId")
                                        site_name = site.get("name") or site.get("siteName", site_id)
                                        if site_id:
                                            self.sites_dict[str(site_id)] = str(site_name)
                            
                            if not self.sites_dict:
                                errors["base"] = "cannot_connect"
                                LOGGER.error("Keine Sites in der API-Antwort gefunden oder falsches Format.")
            except Exception as e:
                LOGGER.warning("Fehler beim Abrufen der Sites im Config Flow: %s", e)
                if "base" not in errors:
                    errors["base"] = "cannot_connect"

            # 2. Lokales BEAAM Gateway validieren
            if not errors:
                url_beaam = f"http://{beaam_ip}/api/v1/site/configuration"
                headers_beaam = {"Authorization": f"Bearer {beaam_key}"}
                try:
                    async with asyncio.timeout(10):
                        async with session.get(url_beaam, headers=headers_beaam) as resp:
                            if resp.status == 401:
                                errors["base"] = "invalid_auth"
                            else:
                                resp.raise_for_status()
                except Exception as e:
                    LOGGER.warning("Fehler bei der Verbindung zum lokalen BEAAM Gateway (%s): %s", beaam_ip, e)
                    if "base" not in errors:
                        errors["base"] = "cannot_connect"

            if not errors and self.sites_dict:
                return await self.async_step_site_selection()

        # Schema für das Eingabeformular in der UI definieren.
        data_schema = vol.Schema(
            {
                vol.Required(CONF_CLOUD_TOKEN, default=self.user_data.get(CONF_CLOUD_TOKEN, "")): str,
                vol.Required(CONF_BEAAM_IP, default=self.user_data.get(CONF_BEAAM_IP, "")): str,
                vol.Required(CONF_BEAAM_KEY, default=self.user_data.get(CONF_BEAAM_KEY, "")): str,
            }
        )

        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors
        )

    async def async_step_site_selection(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Zweiter Schritt: Auswahl des Standorts (Site)."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            site_id = str(user_input[CONF_SITE_ID])
            
            # Eindeutige ID für den Eintrag setzen, um doppelte Instanzen derselben Site zu verhindern
            await self.async_set_unique_id(site_id)
            self._abort_if_unique_id_configured()

            self.user_data[CONF_SITE_ID] = site_id
            site_name = self.sites_dict.get(site_id, "neoom System")
            
            return self.async_create_entry(
                title=site_name, 
                data=self.user_data
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SITE_ID): vol.In(self.sites_dict)
            }
        )

        return self.async_show_form(
            step_id="site_selection",
            data_schema=data_schema,
            errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Behandelt den Start des Re-Authentifizierungs-Flusses bei Authentifizierungsfehlern."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Behandelt die erneute Eingabe und Überprüfung der Zugangsdaten."""
        errors: Dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_CLOUD_TOKEN]
            ip = _clean_ip(user_input[CONF_BEAAM_IP])
            key = user_input[CONF_BEAAM_KEY]
            site_id = reauth_entry.data.get(CONF_SITE_ID)

            session = async_get_clientsession(self.hass)

            # 1. Cloud Token validieren
            try:
                url_site = f"{CLOUD_API_URL}/sites/{site_id}" if site_id else f"{CLOUD_API_URL}/sites"
                async with asyncio.timeout(10):
                    async with session.get(url_site, headers={"Authorization": f"Bearer {token}"}) as resp:
                        if resp.status == 401:
                            errors["base"] = "invalid_auth"
                        else:
                            resp.raise_for_status()
            except Exception as e:
                LOGGER.warning("Reauth Cloud-Prüfung fehlgeschlagen: %s", e)
                if "base" not in errors:
                    errors["base"] = "cannot_connect"

            # 2. BEAAM IP und API Key validieren
            if not errors:
                try:
                    url_beaam = f"http://{ip}/api/v1/site/configuration"
                    async with asyncio.timeout(10):
                        async with session.get(url_beaam, headers={"Authorization": f"Bearer {key}"}) as resp:
                            if resp.status == 401:
                                errors["base"] = "invalid_auth"
                            else:
                                resp.raise_for_status()
                except Exception as e:
                    LOGGER.warning("Reauth BEAAM-Prüfung fehlgeschlagen: %s", e)
                    if "base" not in errors:
                        errors["base"] = "cannot_connect"

            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_CLOUD_TOKEN: token,
                        CONF_BEAAM_IP: ip,
                        CONF_BEAAM_KEY: key,
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CLOUD_TOKEN, default=reauth_entry.data.get(CONF_CLOUD_TOKEN, "")): str,
                vol.Required(CONF_BEAAM_IP, default=reauth_entry.data.get(CONF_BEAAM_IP, "")): str,
                vol.Required(CONF_BEAAM_KEY, default=reauth_entry.data.get(CONF_BEAAM_KEY, "")): str,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Behandelt die Neu-Konfiguration über das 3-Punkte-Menü."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: Dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_CLOUD_TOKEN]
            ip = _clean_ip(user_input[CONF_BEAAM_IP])
            key = user_input[CONF_BEAAM_KEY]
            site_id = reconfigure_entry.data.get(CONF_SITE_ID)

            session = async_get_clientsession(self.hass)

            # 1. Cloud Validierung
            try:
                url_site = f"{CLOUD_API_URL}/sites/{site_id}" if site_id else f"{CLOUD_API_URL}/sites"
                async with asyncio.timeout(10):
                    async with session.get(url_site, headers={"Authorization": f"Bearer {token}"}) as resp:
                        if resp.status == 401:
                            errors["base"] = "invalid_auth"
                        else:
                            resp.raise_for_status()
            except Exception as e:
                LOGGER.warning("Reconfigure Cloud-Prüfung fehlgeschlagen: %s", e)
                errors["base"] = "cannot_connect"

            # 2. BEAAM Validierung
            if not errors:
                try:
                    url_beaam = f"http://{ip}/api/v1/site/configuration"
                    async with asyncio.timeout(10):
                        async with session.get(url_beaam, headers={"Authorization": f"Bearer {key}"}) as resp:
                            if resp.status == 401:
                                errors["base"] = "invalid_auth"
                            else:
                                resp.raise_for_status()
                except Exception as e:
                    LOGGER.warning("Reconfigure BEAAM-Prüfung fehlgeschlagen: %s", e)
                    errors["base"] = "cannot_connect"

            if not errors:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data={
                        **reconfigure_entry.data,
                        CONF_CLOUD_TOKEN: token,
                        CONF_BEAAM_IP: ip,
                        CONF_BEAAM_KEY: key,
                    },
                )

        current_token = reconfigure_entry.options.get(CONF_CLOUD_TOKEN, reconfigure_entry.data.get(CONF_CLOUD_TOKEN, ""))
        current_ip = reconfigure_entry.options.get(CONF_BEAAM_IP, reconfigure_entry.data.get(CONF_BEAAM_IP, ""))
        current_key = reconfigure_entry.options.get(CONF_BEAAM_KEY, reconfigure_entry.data.get(CONF_BEAAM_KEY, ""))

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CLOUD_TOKEN, default=current_token): str,
                vol.Required(CONF_BEAAM_IP, default=current_ip): str,
                vol.Required(CONF_BEAAM_KEY, default=current_key): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )


class NeoomOptionsFlowHandler(config_entries.OptionsFlow):
    """Behandelt das Optionen-Menü (Zahnrad / 'Konfigurieren'-Button) in Home Assistant."""

    def __init__(self, config_entry: Optional[config_entries.ConfigEntry] = None) -> None:
        """Initialisiert den Optionen-Fluss."""
        # Hinweis: self.config_entry ist eine schreibgeschützte Property der Basisklasse OptionsFlow
        # und wird von Home Assistant automatisch über die ConfigEntry bereitgestellt.
        super().__init__()

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Verwaltet die Optionen für Aktualisierungsintervalle und Verbindungsdaten."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Bereinige die IP-Adresse
            ip = _clean_ip(user_input.get(CONF_BEAAM_IP, ""))
            user_input[CONF_BEAAM_IP] = ip
            
            token = user_input.get(CONF_CLOUD_TOKEN, "")
            key = user_input.get(CONF_BEAAM_KEY, "")
            site_id = self.config_entry.data.get(CONF_SITE_ID)

            session = async_get_clientsession(self.hass)

            # Optionale Validierung bei geänderten Zugangsdaten
            if token and (token != self.config_entry.options.get(CONF_CLOUD_TOKEN, self.config_entry.data.get(CONF_CLOUD_TOKEN))):
                try:
                    url_site = f"{CLOUD_API_URL}/sites/{site_id}" if site_id else f"{CLOUD_API_URL}/sites"
                    async with asyncio.timeout(10):
                        async with session.get(url_site, headers={"Authorization": f"Bearer {token}"}) as resp:
                            if resp.status == 401:
                                errors["base"] = "invalid_auth"
                            else:
                                resp.raise_for_status()
                except Exception as e:
                    LOGGER.warning("Optionen-Validierung Cloud fehlgeschlagen: %s", e)
                    errors["base"] = "cannot_connect"

            if not errors and (ip or key):
                check_ip = ip or self.config_entry.options.get(CONF_BEAAM_IP, self.config_entry.data.get(CONF_BEAAM_IP))
                check_key = key or self.config_entry.options.get(CONF_BEAAM_KEY, self.config_entry.data.get(CONF_BEAAM_KEY))
                try:
                    url_beaam = f"http://{check_ip}/api/v1/site/configuration"
                    async with asyncio.timeout(10):
                        async with session.get(url_beaam, headers={"Authorization": f"Bearer {check_key}"}) as resp:
                            if resp.status == 401:
                                errors["base"] = "invalid_auth"
                            else:
                                resp.raise_for_status()
                except Exception as e:
                    LOGGER.warning("Optionen-Validierung BEAAM (%s) fehlgeschlagen: %s", check_ip, e)
                    errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Aktuelle Werte aus options (mit Fallback auf data bzw. Defaults) laden
        curr_local_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_LOCAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL_LOCAL, DEFAULT_SCAN_INTERVAL_LOCAL),
        )
        curr_cloud_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_CLOUD,
            self.config_entry.data.get(CONF_SCAN_INTERVAL_CLOUD, DEFAULT_SCAN_INTERVAL_CLOUD),
        )
        curr_beaam_ip = self.config_entry.options.get(
            CONF_BEAAM_IP,
            self.config_entry.data.get(CONF_BEAAM_IP, ""),
        )
        curr_beaam_key = self.config_entry.options.get(
            CONF_BEAAM_KEY,
            self.config_entry.data.get(CONF_BEAAM_KEY, ""),
        )
        curr_cloud_token = self.config_entry.options.get(
            CONF_CLOUD_TOKEN,
            self.config_entry.data.get(CONF_CLOUD_TOKEN, ""),
        )

        options_schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL_LOCAL, default=curr_local_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
                vol.Required(CONF_SCAN_INTERVAL_CLOUD, default=curr_cloud_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=30, max=3600)
                ),
                vol.Required(CONF_BEAAM_IP, default=curr_beaam_ip): str,
                vol.Required(CONF_BEAAM_KEY, default=curr_beaam_key): str,
                vol.Required(CONF_CLOUD_TOKEN, default=curr_cloud_token): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )
