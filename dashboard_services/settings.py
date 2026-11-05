"""Original defaults and per-rerun environment configuration, without service startup."""
import os
from timestamps import CHICAGO

def read_settings():
    VERSION = "v0.26.2-live-layout-fix"
    MQTT_BROKER = os.getenv("RFID_MQTT_HOST", "localhost")
    MQTT_PORT = int(os.getenv("RFID_MQTT_PORT", "1883"))
    MQTT_TOPIC = os.getenv("RFID_MQTT_TOPIC", "rfid/readings/TC22R-01")
    MQTT_USERNAME = os.getenv("RFID_MQTT_USERNAME", "")
    MQTT_PASSWORD = os.getenv("RFID_MQTT_PASSWORD", "")
    MAX_MESSAGES = 5000
    INFLUX_HOST = os.getenv("INFLUX_HOST", "http://127.0.0.1:8181")
    INFLUX_DATABASE = os.getenv("INFLUX_DATABASE", "rfid")
    INFLUX_TOKEN = os.getenv("INFLUXDB3_AUTH_TOKEN")
    HISTORY_TIMEZONE = CHICAGO
    TAG_PALETTE = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
    ]
    TIME_RANGES = {
        "Last 5 minutes": ("5 minutes", 2000),
        "Last 15 minutes": ("15 minutes", 3500),
        "Last 1 hour": ("1 hour", 6000),
        "Last 6 hours": ("6 hours", 10000),
        "Last 24 hours": ("24 hours", 15000),
    }
    return {
        "VERSION": VERSION,
        "MQTT_BROKER": MQTT_BROKER,
        "MQTT_PORT": MQTT_PORT,
        "MQTT_TOPIC": MQTT_TOPIC,
        "MQTT_USERNAME": MQTT_USERNAME,
        "MQTT_PASSWORD": MQTT_PASSWORD,
        "MAX_MESSAGES": MAX_MESSAGES,
        "INFLUX_HOST": INFLUX_HOST,
        "INFLUX_DATABASE": INFLUX_DATABASE,
        "INFLUX_TOKEN": INFLUX_TOKEN,
        "HISTORY_TIMEZONE": HISTORY_TIMEZONE,
        "TAG_PALETTE": TAG_PALETTE,
        "TIME_RANGES": TIME_RANGES,
    }

# Defaults support direct helper imports; the entrypoint re-reads on every rerun.
_defaults = read_settings()
VERSION = _defaults["VERSION"]
MQTT_BROKER = _defaults["MQTT_BROKER"]
MQTT_PORT = _defaults["MQTT_PORT"]
MQTT_TOPIC = _defaults["MQTT_TOPIC"]
MQTT_USERNAME = _defaults["MQTT_USERNAME"]
MQTT_PASSWORD = _defaults["MQTT_PASSWORD"]
MAX_MESSAGES = _defaults["MAX_MESSAGES"]
INFLUX_HOST = _defaults["INFLUX_HOST"]
INFLUX_DATABASE = _defaults["INFLUX_DATABASE"]
INFLUX_TOKEN = _defaults["INFLUX_TOKEN"]
HISTORY_TIMEZONE = _defaults["HISTORY_TIMEZONE"]
TAG_PALETTE = _defaults["TAG_PALETTE"]
TIME_RANGES = _defaults["TIME_RANGES"]
