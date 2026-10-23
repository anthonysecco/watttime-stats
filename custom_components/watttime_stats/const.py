"""Constants for the WattTime Status integration."""

from datetime import timedelta

DOMAIN = "watttime_stats"
ATTRIBUTION = "Data provided by WattTime"
API_URL = "https://api.watttime.org"

SIGNAL_MOER = "co2_moer"
SIGNAL_HEALTH = "health_damage"
SIGNAL_AOER = "co2_aoer"  # average emissions; paid plans, published for parent regions (e.g. CAISO)
ENDPOINT_FORECAST = "v3/forecast"
ENDPOINT_HISTORICAL = "v3/historical"

CONF_REGION = "region"
CONF_REGION_NAME = "region_name"
CONF_EMAIL = "email"
CONF_ORG = "org"

CONF_UNIT = "unit"
CONF_CLEAN_PERCENTILE = "clean_percentile"
CONF_CLEAN_MAX = "clean_max"
CONF_WINDOW_HOURS = "window_hours"
CONF_LOOKAHEAD_HOURS = "lookahead_hours"

UNIT_G_KWH = "g/kWh"
UNIT_LBS_MWH = "lbs/MWh"
UNIT_HEALTH = "USD/MWh"
# Option values (lowercase keys, as Home Assistant requires) -> displayed unit
UNIT_OPTIONS = {"g_kwh": UNIT_G_KWH, "lbs_mwh": UNIT_LBS_MWH}

# WattTime reports CO2 in lbs/MWh; 1 lb/MWh = 0.453592 g/kWh.
G_KWH_PER_LBS_MWH = 0.453592

DEFAULT_UNIT = "g_kwh"
DEFAULT_CLEAN_PERCENTILE = 25  # "clean" = the cleanest 25% of the look-ahead...
DEFAULT_CLEAN_MAX = 227  # ...and never above 227 g/kWh (gas plants run ~385-470)
DEFAULT_WINDOW_HOURS = 2.0
DEFAULT_LOOKAHEAD_HOURS = 24

UPDATE_INTERVAL = timedelta(minutes=5)
ACCESS_RECHECK = timedelta(hours=6)
LIVE_LOOKBACK = timedelta(hours=1)
AOER_LOOKBACK = timedelta(hours=24)  # average emissions are published with a delay
AOER_REFRESH = timedelta(minutes=30)

SERVICE_GET_FORECAST = "get_forecast"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
