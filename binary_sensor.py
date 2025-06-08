# custom_components/nl_alert/binary_sensor.py

import asyncio
import math
import logging
from datetime import timedelta

import aiohttp
import async_timeout

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.const import CONF_ENTITY_ID

from .const import DOMAIN, BURGERNET_API, NL_ALERT_API

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


def point_in_polygon(lat, lon, polygon):
    """
    Ray-casting to check if (lat, lon) is inside `polygon` (list of (lat, lon)).
    """
    inside = False
    n = len(polygon)
    for i in range(n):
        j = (i + n - 1) % n
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        intersect = ((xi > lon) != (xj > lon)) and (
            lat < (yj - yi) * (lon - xi) / (xj - xi + 1e-12) + yi
        )
        if intersect:
            inside = not inside
    return inside


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the combined NL-Alert binary sensor from a config entry."""
    location_source = entry.data["location_source"]
    tracker_entity_id = entry.data.get(CONF_ENTITY_ID)
    max_radius_km = entry.data.get("max_radius", 5)
    max_radius_m = max_radius_km * 1000

    async def _async_fetch():
        """Fetch both APIs concurrently."""
        async with async_timeout.timeout(15):
            async with aiohttp.ClientSession() as session:
                b_task = session.get(BURGERNET_API, headers={"Accept": "application/json"})
                n_task = session.get(NL_ALERT_API, headers={"Accept": "application/json"})

                resp_burger, resp_nl = await asyncio.gather(b_task, n_task)
                resp_burger.raise_for_status()
                resp_nl.raise_for_status()

                return {
                    "burgernet": await resp_burger.json(),
                    "nl_alert": await resp_nl.json(),
                }

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN + "_binary",
        update_interval=SCAN_INTERVAL,
        update_method=_async_fetch,
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities([
        NLAlertBinarySensor(coordinator, hass, location_source, tracker_entity_id, max_radius_m)
    ], update_before_add=True)


class NLAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor: On = an active alert (Burgernet in-range or NL-Alert in-polygon)."""

    def __init__(self, coordinator, hass, location_source, tracker_entity_id, max_radius_m):
        super().__init__(coordinator)
        self.hass = hass
        self.location_source = location_source
        self.tracker_entity_id = tracker_entity_id
        self.max_radius_m = max_radius_m

        self._attr_name = "NL-Alert"
        self._attr_unique_id = "nl_alert"
        self._attr_device_class = "safety"

    @property
    def is_on(self) -> bool:
        """
        True if either:
          - A Burgernet alert matches our location+radius, OR
          - An NL-Alert item (with stop_at=None) whose polygon covers us.
        """
        data = self.coordinator.data or {}
        burgernet_list = data.get("burgernet", [])
        nlalert_list = data.get("nl_alert", {}).get("data", [])

        # 1) Check Burgernet
        if self._burgernet_active(burgernet_list):
            return True

        # 2) Check NL-Alert polygons
        if self._nl_alert_active(nlalert_list):
            return True

        return False

    def _burgernet_active(self, alerts):
        """Return True if any Burgernet alert applies based on our coords."""
        if self.location_source == "entity" and self.tracker_entity_id:
            state = self.hass.states.get(self.tracker_entity_id)
            if state and state.attributes.get("latitude") is not None:
                lat = state.attributes["latitude"]
                lon = state.attributes["longitude"]
            else:
                _LOGGER.warning(
                    "Tracker %s unavailable; using home coords", self.tracker_entity_id
                )
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude
        else:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude

        for alert in alerts:
            lvl = int(alert.get("AlertLevel", 0))
            if lvl == 10:
                return True
            area = alert.get("Area", {})
            circle = area.get("Circle")
            if circle:
                centre_str, radius_str = circle.split()
                clat, clon = [float(x) for x in centre_str.split(",")]
                distance = haversine(lat, lon, clat, clon)
                if (
                    distance <= float(radius_str)
                    and distance <= self.max_radius_m
                ):
                    return True
        return False

    def _nl_alert_active(self, data_list):
        """Return True if any NL-Alert polygon (stop_at=None) contains our location."""
        if self.location_source == "entity" and self.tracker_entity_id:
            state = self.hass.states.get(self.tracker_entity_id)
            if state and state.attributes.get("latitude") is not None:
                lat = state.attributes["latitude"]
                lon = state.attributes["longitude"]
            else:
                _LOGGER.warning(
                    "Tracker %s unavailable; using home coords", self.tracker_entity_id
                )
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude
        else:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude

        for item in data_list:
            # Only active items (stop_at == None)
            if item.get("stop_at") is not None:
                continue

            area_list = item.get("area", [])
            for poly_str in area_list:
                polygon = []
                for pair in poly_str.strip().split():
                    lat_str, lon_str = pair.split(",")
                    polygon.append((float(lat_str), float(lon_str)))

                if point_in_polygon(lat, lon, polygon):
                    return True

        return False
