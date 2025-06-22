import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_ENTITY_ID
from homeassistant.helpers.selector import (
    SelectSelector, SelectSelectorConfig,
    EntitySelector, EntitySelectorConfig,
    NumberSelector, NumberSelectorConfig,
)
from .const import DOMAIN

# Schema for both the initial setup and options
STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default="NL-Alert & Burgernet"): str,
    vol.Required(
        "location_source",
        default="home"
    ): SelectSelector(
        config=SelectSelectorConfig(
            mode="dropdown",
            options=[
                {"value": "home",   "label": "Use Home location"},
                {"value": "entity", "label": "Use a device_tracker entity"},
            ]
        )
    ),
    vol.Optional(
        CONF_ENTITY_ID
    ): EntitySelector(
        config=EntitySelectorConfig(domain="device_tracker")
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


class NLAlertConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow for NL-Alert & Burgernet integration."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Show the initial form to set up the integration."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
            )

        # Validate: if user chose entity-based location, an entity_id is required
        if (
            user_input["location_source"] == "entity"
            and not user_input.get(CONF_ENTITY_ID)
        ):
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={CONF_ENTITY_ID: "required"},
            )

        # Setup entry with provided data
        return self.async_create_entry(
            title=user_input[CONF_NAME],
            data=user_input,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler so users can edit settings."""
        return NLAlertOptionsFlowHandler(config_entry)


class NLAlertOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle updating the integration options after setup."""

    def __init__(self, config_entry):
        """Initialize with the existing config entry."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """
        Show a form to update settings.
        Defaults are loaded from entry.options if present, otherwise from entry.data.
        """
        # Use previously saved options, or fall back to initial data
        current = self.config_entry.options or self.config_entry.data

        if user_input is None:
            # Build the same schema but prefill with current values
            schema = vol.Schema({
                vol.Required(
                    "location_source",
                    default=current.get("location_source", "home")
                ): SelectSelector(
                    config=SelectSelectorConfig(
                        mode="dropdown",
                        options=[
                            {"value": "home",   "label": "Use Home location"},
                            {"value": "entity", "label": "Use a device_tracker entity"},
                        ]
                    )
                ),
                vol.Optional(
                    CONF_ENTITY_ID,
                    default=current.get(CONF_ENTITY_ID)
                ): EntitySelector(
                    config=EntitySelectorConfig(domain="device_tracker")
                ),
                vol.Optional(
                    "max_radius",
                    default=current.get("max_radius", 5)
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
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
            )

        # Validate again: if entity-based, entity_id must be set
        if (
            user_input["location_source"] == "entity"
            and not user_input.get(CONF_ENTITY_ID)
        ):
            return self.async_show_form(
                step_id="init",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={CONF_ENTITY_ID: "required"},
            )

        # Create the options entry with updated values
        return self.async_create_entry(
            title="",
            data=user_input,
        )
