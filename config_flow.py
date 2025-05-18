import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_ENTITY_ID
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
)

from .const import DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default="Burgernet Alert"): str,
    vol.Required(
        "location_source",
        default="home"
    ): SelectSelector(
        config=SelectSelectorConfig(
            mode="dropdown",
            options=[
                {"value": "home", "label": "Use Home location"},
                {"value": "entity", "label": "Use a device_tracker entity"},
            ]
        )
    ),
    vol.Optional(
        CONF_ENTITY_ID
    ): EntitySelector(
        config=EntitySelectorConfig(
            domain="device_tracker"
        )
    ),
    vol.Optional(
        "max_radius",
        default=5
    ): NumberSelector(
        config=NumberSelectorConfig(
            min=0,
            max=100,
            step=1,
            mode="box",
            unit_of_measurement="km",
        )
    ),
})


class BurgerNetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Burgernet Alert integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
            )

        # Ensure entity_id if they chose entity mode
        if (
            user_input["location_source"] == "entity"
            and not user_input.get(CONF_ENTITY_ID)
        ):
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={CONF_ENTITY_ID: "required"},
            )

        return self.async_create_entry(
            title=user_input[CONF_NAME],
            data=user_input,
        )
