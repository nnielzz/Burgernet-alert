DOMAIN = "nl_alert"
PLATFORMS = ["sensor", "binary_sensor"]

# Burgernet API (location-filtered alerts)
BURGERNET_API = "https://services.burgernet.nl/landactiehost/api/v1/alerts"
# NL-Alert API (national alerts; no location data)
NL_ALERT_API = "https://api.public-warning.app/api/v1/providers/nl-alert/alerts"

# (reuse the same poster URL for Burgernet/AMBER)
STATIC_POSTER_URL = "https://www.burgernet.nl/static/posters/landelijk/1920x1080.jpg"
