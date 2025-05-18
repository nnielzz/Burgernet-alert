import math
import logging
from datetime import timedelta

import aiohttp
import async_timeout

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.const import CONF_ENTITY_ID

from .const import DOMAIN, API_ENDPOINT

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=10)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Burgernet binary sensor from a config entry."""
    location_source = entry.data["location_source"]
    tracker_entity_id = entry.data.get(CONF_ENTITY_ID)
    max_radius_km = entry.data.get("max_radius", 5)
    max_radius_m = max_radius_km * 1000

    async def _async_fetch():
        headers = {"Accept": "application/json"}
        async with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                r = await session.get(API_ENDPOINT, headers=headers)
                r.raise_for_status()
                return await r.json()

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN + "_binary",
        update_interval=SCAN_INTERVAL,
        update_method=_async_fetch,
    )

    await coordinator.async_config_entry_first_refresh()
    async_add_entities([
        BurgerNetBinarySensor(coordinator, hass, location_source, tracker_entity_id, max_radius_m)
    ], update_before_add=True)

class BurgerNetBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor which is ON when there is an active alert."""

    def __init__(self, coordinator, hass, location_source, tracker_entity_id, max_radius_m):
        super().__init__(coordinator)
        self.hass = hass
        self.location_source = location_source
        self.tracker_entity_id = tracker_entity_id
        self.max_radius_m = max_radius_m

        self._attr_name = "Burgernet Alert"          # entity_id: binary_sensor.burgernet_alert
        self._attr_unique_id = "burgernet_alert"     # stable unique_id
        self._attr_device_class = "safety"           # choose appropriate class

    @property
    def is_on(self) -> bool:
        """Return True if there is a matching alert."""
        alerts = self.coordinator.data or []

        # determine user coords
        if self.location_source == "entity" and self.tracker_entity_id:
            state = self.hass.states.get(self.tracker_entity_id)
            if state and state.attributes.get("latitude") is not None:
                lat = state.attributes["latitude"]
                lon = state.attributes["longitude"]
            else:
                _LOGGER.warning("Tracker %s unavailable; using home coords",
                                self.tracker_entity_id)
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude
        else:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude

        for alert in alerts:
            lvl = int(alert.get("AlertLevel", 0))
            if lvl == 10:
                return True  # Amber alert always on
            circle = alert.get("Area", {}).get("Circle")
            if circle:
                centre_str, _ = circle.split()
                clat, clon = [float(x) for x in centre_str.split(",")]
                if haversine(lat, lon, clat, clon) <= self.max_radius_m:
                    return True

        return False
