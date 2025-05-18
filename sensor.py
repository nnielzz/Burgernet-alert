import math
import logging
from datetime import timedelta

import aiohttp
import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.const import CONF_ENTITY_ID

from .const import DOMAIN, API_ENDPOINT, STATIC_POSTER_URL

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=10)

def haversine(lat1, lon1, lat2, lon2):
    """Return distance in meters between two lat/lon points."""
    R = 6371000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Burgernet sensor from a config entry."""
    location_source = entry.data["location_source"]
    tracker_entity_id = entry.data.get(CONF_ENTITY_ID)
    max_radius_km = entry.data.get("max_radius", 5)
    max_radius_m = max_radius_km * 1000

    async def _async_fetch():
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
        update_method=_async_fetch,
    )

    # First fetch
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([
        BurgerNetSensor(coordinator, hass, location_source, tracker_entity_id, max_radius_m)
    ], update_before_add=True)

class BurgerNetSensor(CoordinatorEntity, SensorEntity):
    """A sensor to report the latest Burgernet/AMBER alert."""

    def __init__(self, coordinator, hass, location_source, tracker_entity_id, max_radius_m):
        super().__init__(coordinator)
        self.hass = hass
        self.location_source = location_source
        self.tracker_entity_id = tracker_entity_id
        self.max_radius_m = max_radius_m

        # Fixed name and unique_id → sensor.burgernet_alert
        self._attr_name = "Burgernet Alert"
        self._attr_unique_id = "burgernet_alert"

    @property
    def state(self):
        alerts = self.coordinator.data or []
        return "active" if self._filtered_alert(alerts) else "none"

    @property
    def extra_state_attributes(self):
        alerts = self.coordinator.data or []
        alert = self._filtered_alert(alerts)
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

    def _filtered_alert(self, alerts):
        """Return first matching alert, or None."""
        # 1) Determine user coords
        if self.location_source == "entity" and self.tracker_entity_id:
            state = self.hass.states.get(self.tracker_entity_id)
            if state and state.attributes.get("latitude") is not None:
                lat = state.attributes["latitude"]
                lon = state.attributes["longitude"]
            else:
                _LOGGER.warning(
                    "Tracker %s unavailable; using home location",
                    self.tracker_entity_id,
                )
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude
        else:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude

        # 2) Scan alerts
        for alert in alerts:
            level = int(alert.get("AlertLevel", 0))
            # Always trigger on national Amber Alerts
            if level == 10:
                return alert

            # For regional, check distance to alert center ≤ max_radius_m
            circle = alert.get("Area", {}).get("Circle")
            if circle:
                centre_str, _api_radius = circle.split()
                clat, clon = [float(x) for x in centre_str.split(",")]
                distance = haversine(lat, lon, clat, clon)
                if distance <= self.max_radius_m:
                    return alert

        return None
