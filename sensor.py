# custom_components/nl_alert/sensor.py

import asyncio
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

from .const import (
    DOMAIN,
    BURGERNET_API,
    NL_ALERT_API,
    STATIC_POSTER_URL,
)

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=10)


def haversine(lat1, lon1, lat2, lon2):
    """Return distance in meters between two lat/lon points."""
    R = 6371000  # Earth radius in meters
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def point_in_polygon(lat, lon, polygon):
    """
    Ray-casting algorithm to check if (lat, lon) is inside `polygon`.
    `polygon` is a list of (lat, lon) tuples. Returns True if inside or on edge.
    """
    inside = False
    n = len(polygon)
    for i in range(n):
        j = (i + n - 1) % n
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        # Check if the ray crosses the edge
        intersect = ((xi > lon) != (xj > lon)) and (
            lat < (yj - yi) * (lon - xi) / (xj - xi + 1e-12) + yi
        )
        if intersect:
            inside = not inside
    return inside


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the combined NL-Alert sensor from a config entry."""
    location_source = entry.data["location_source"]
    tracker_entity_id = entry.data.get(CONF_ENTITY_ID)
    max_radius_km = entry.data.get("max_radius", 5)
    max_radius_m = max_radius_km * 1000

    async def _async_fetch():
        """Fetch both Burgernet and NL-Alert APIs concurrently."""
        async with async_timeout.timeout(15):
            async with aiohttp.ClientSession() as session:
                burger_task = session.get(BURGERNET_API, headers={"Accept": "application/json"})
                nl_task = session.get(NL_ALERT_API, headers={"Accept": "application/json"})

                resp_burgernet, resp_nlalert = await asyncio.gather(burger_task, nl_task)
                resp_burgernet.raise_for_status()
                resp_nlalert.raise_for_status()

                data_burgernet = await resp_burgernet.json()
                data_nlalert = await resp_nlalert.json()

                return {
                    "burgernet": data_burgernet,
                    "nl_alert": data_nlalert,
                }

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_interval=SCAN_INTERVAL,
        update_method=_async_fetch,
    )

    # First fetch to populate coordinator.data
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([
        NLAlertSensor(coordinator, hass, location_source, tracker_entity_id, max_radius_m)
    ], update_before_add=True)


class NLAlertSensor(CoordinatorEntity, SensorEntity):
    """Combined sensor for Burgernet (location-filtered) + NL-Alert (polygon-filtered)."""

    def __init__(self, coordinator, hass, location_source, tracker_entity_id, max_radius_m):
        super().__init__(coordinator)
        self.hass = hass
        self.location_source = location_source
        self.tracker_entity_id = tracker_entity_id
        self.max_radius_m = max_radius_m

        # This will produce entity_id: sensor.nl_alert
        self._attr_name = "NL-Alert"
        self._attr_unique_id = "nl_alert"

    @property
    def state(self):
        """Return 'active' if either source has an applicable alert, else 'none'."""
        combined = self.coordinator.data or {}
        burgernet_data = combined.get("burgernet", [])
        nlalert_data = combined.get("nl_alert", {}).get("data", [])

        burgernet_match = self._filter_burgernet(burgernet_data)
        nlalert_match = self._filter_nl_alert(nlalert_data)

        return "active" if (burgernet_match or nlalert_match) else "none"

    @property
    def extra_state_attributes(self):
        """
        Return combined attributes, including which source(s) fired,
        plus the raw alert details under separate keys.
        """
        combined = self.coordinator.data or {}
        burgernet_data = combined.get("burgernet", [])
        nlalert_data = combined.get("nl_alert", {}).get("data", [])

        attrs = {"poster_url": STATIC_POSTER_URL, "sources": []}

        # Check Burgernet
        burgernet_match = self._filter_burgernet(burgernet_data)
        if burgernet_match:
            attrs["sources"].append("burgernet")
            msg = burgernet_match["Message"]
            area = burgernet_match.get("Area", {})
            attrs["burgernet_alert"] = {
                "alert_id": burgernet_match["AlertId"],
                "level": burgernet_match["AlertLevel"],
                "title": msg["Title"],
                "description": msg["Description"],
                "type": msg["DescriptionExt"],
                "readmore_url": msg.get("Readmore_URL"),
                "image": msg["Media"]["Image"],
                "small_image": msg["Media"]["SmallImage"],
                "area_description": area.get("Description"),
                "area_circle": area.get("Circle"),
            }

        # Check NL-Alert
        nl_item = self._filter_nl_alert(nlalert_data)
        if nl_item:
            attrs["sources"].append("nl_alert")
            attrs["nl_alert_id"] = nl_item.get("id")
            attrs["nl_alert_message"] = nl_item.get("message")

        if not attrs["sources"]:
            attrs["sources"] = ["none"]

        return attrs

    def _filter_burgernet(self, alerts):
        """Return the first Burgernet alert matching our location, or None."""
        # Determine our coordinates:
        if self.location_source == "entity" and self.tracker_entity_id:
            state = self.hass.states.get(self.tracker_entity_id)
            if state and (state.attributes.get("latitude") is not None):
                lat = state.attributes["latitude"]
                lon = state.attributes["longitude"]
            else:
                _LOGGER.warning(
                    "Tracker %s unavailable or has no coords; using home location",
                    self.tracker_entity_id,
                )
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude
        else:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude

        for alert in alerts:
            lvl = int(alert.get("AlertLevel", 0))
            # Always include national Amber (level 10)
            if lvl == 10:
                return alert

            # Regional: check Area.Circle (lat,lon radius_m)
            area = alert.get("Area", {})
            circle = area.get("Circle")
            if circle:
                centre_str, radius_str = circle.split()
                clat, clon = [float(x) for x in centre_str.split(",")]
                if haversine(lat, lon, clat, clon) <= float(radius_str):
                    return alert

        return None

    def _filter_nl_alert(self, data_list):
        """
        Return the first NL-Alert item whose `stop_at` is None
        AND whose polygon contains our location. Else None.
        """
        # Determine our coordinates (same code as above)
        if self.location_source == "entity" and self.tracker_entity_id:
            state = self.hass.states.get(self.tracker_entity_id)
            if state and state.attributes.get("latitude") is not None:
                lat = state.attributes["latitude"]
                lon = state.attributes["longitude"]
            else:
                _LOGGER.warning(
                    "Tracker %s unavailable; using home location", self.tracker_entity_id
                )
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude
        else:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude

        for item in data_list:
            # Only consider currently active alerts
            if item.get("stop_at") is not None:
                continue

            # "area" is a list of polygon-strings
            area_list = item.get("area", [])
            for poly_str in area_list:
                # Parse "52.40124,4.86918 52.40224,4.83122 …"
                coords = []
                for pair in poly_str.strip().split():
                    lat_str, lon_str = pair.split(",")
                    coords.append((float(lat_str), float(lon_str)))

                # If our (lat, lon) is inside this polygon => return this item
                if point_in_polygon(lat, lon, coords):
                    return item

        return None
