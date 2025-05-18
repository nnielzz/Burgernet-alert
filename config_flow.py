import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from .const import DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default="Burgernet Alerts"): str,
    vol.Required("location_source", default="home"): selector.SelectSelector(
        selector={"select": {"options": ["home", "entity"], "mode": "dropdown"}}
    ),
    vol.Optional("entity_id"): selector.EntitySelector(
        selector={"domain": "device_tracker"}
    ),
})

class BurgerNetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)
