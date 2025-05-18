import asyncio, math, logging
from datetime import timedelta
import aiohttp
import async_timeout

from homeassistant import config_entries
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator, CoordinatorEntity
)
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.helpers import entity_platform

from .const import DOMAIN, API_ENDPOINT, STATIC_POSTER_URL

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=10)

def haversine(lat1, lon1, lat2, lon2):
    # calculate distance in meters between two lat/lon points
    R = 6371000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Burgernet sensor from a config entry."""
    location_source = entry.data["location_source"]
    entity_id = entry.data.get("entity_id")

    async def async_fetch_alerts():
        headers = {"Accept": "application/json"}
        async with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                resp = await session.get(API_ENDPOINT, headers=headers)
                resp.raise_for_status()
                return await resp.json()

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_interval=SCAN_INTERVAL,
        update_method=async_fetch_alerts,
    )
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([BurgerNetSensor(coordinator, hass, location_source, entity_id)], True)

class BurgerNetSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, hass, location_source, entity_id):
        super().__init__(coordinator)
        self.hass = hass
        self.location_source = location_source
        self.entity_id = entity_id
        self._attr_name = "Burgernet Alert"
        self._attr_unique_id = DOMAIN

    @property
    def state(self):
        data = self.coordinator.data or []
        alert = self._filter_by_location(data)
        if not alert:
            return "none"
        return "active"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or []
        alert = self._filter_by_location(data)
        if not alert:
            return {"poster_url": None}
        msg = alert["Message"]
        area = alert.get("Area", {})
        return {
            "alert_id": alert["AlertId"],
            "level": alert["AlertLevel"],
            "title": msg["Title"],
            "description": msg["Description"],
            "type": msg["DescriptionExt"],
            "readmore_url": msg.get("Readmore_URL"),
            "image": msg["Media"]["Image"],
            "small_image": msg["Media"]["SmallImage"],
            "area_description": area.get("Description"),
            "area_circle": area.get("Circle"),
            "poster_url": STATIC_POSTER_URL,
        }

    def _filter_by_location(self, alerts):
        """Return the first alert matching location, or any Amber Alert."""
        # get current lat/lon
        if self.location_source == "entity" and self.entity_id:
            state = self.hass.states.get(self.entity_id)
            lat = state.attributes.get("latitude")
            lon = state.attributes.get("longitude")
        else:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude

        for alert in alerts:
            lvl = int(alert["AlertLevel"])
            if lvl == 10:
                return alert  # always include national Amber Alerts
            # Vermist Kind Alert: check area circle
            area = alert.get("Area", {})
            circle = area.get("Circle")
            if circle:
                # format "lat,lon radius_m"
                parts = circle.split()
                centre = parts[0].split(",")
                radius = float(parts[1])
                if haversine(lat, lon, float(centre[0]), float(centre[1])) <= radius:
                    return alert
        return None
