"""Configuration loading and validation."""

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Path to config.json relative to this file (one directory up)
_DEFAULT_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config.json")
)


@dataclass
class Config:
    # Serial port
    port: str
    baudrate: int

    # Decryption
    key: str

    # General
    print_value: bool
    log_level: str

    # MQTT
    use_mqtt: bool
    mqtt_broker_ip: str
    mqtt_broker_port: int
    mqtt_broker_user: str
    mqtt_broker_password: str

    # InfluxDB
    use_influxdb: bool
    influxdb_ip: str
    influxdb_port: int
    influxdb_database: str

    # Rate limiting: minimum seconds between writes (0 = write every frame)
    min_interval_seconds: float


def load_config(path: Optional[str] = None) -> Config:
    """Load, validate, and return a Config from the given JSON file path.

    Exits the process with a descriptive message if the file is missing,
    unreadable, or contains invalid values.
    """
    config_path = path or _DEFAULT_CONFIG_PATH

    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    if not os.access(config_path, os.R_OK):
        print(f"Config file not readable: {config_path}")
        sys.exit(2)

    with open(config_path) as f:
        raw = json.load(f)

    # Check all required keys are present
    required = [
        "port", "baudrate", "key", "printValue",
        "useMQTT", "mqttbrokerip", "mqttbrokerport",
        "mqttbrokeruser", "mqttbrokerpasswort",
        "useInfluxdb", "influxdbip", "influxdbport",
    ]
    missing = [k for k in required if k not in raw]
    if missing:
        print(f"Missing required config keys: {', '.join(missing)}")
        sys.exit(3)

    # Coerce types (JSON may have ports as strings)
    def _int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _float(value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    cfg = Config(
        port=str(raw["port"]),
        baudrate=_int(raw["baudrate"], 2400),
        key=str(raw["key"]).upper(),
        print_value=bool(raw["printValue"]),
        log_level=str(raw.get("logLevel", "INFO")).upper(),
        use_mqtt=bool(raw["useMQTT"]),
        mqtt_broker_ip=str(raw["mqttbrokerip"]),
        mqtt_broker_port=_int(raw["mqttbrokerport"], 1883),
        mqtt_broker_user=str(raw["mqttbrokeruser"]),
        mqtt_broker_password=str(raw["mqttbrokerpasswort"]),
        use_influxdb=bool(raw["useInfluxdb"]),
        influxdb_ip=str(raw["influxdbip"]),
        influxdb_port=_int(raw["influxdbport"], 8086),
        influxdb_database=str(raw.get("influxdbdatenbank", "SmartMeter")),
        min_interval_seconds=_float(raw.get("minIntervalSeconds", 0.0), 0.0),
    )

    # Semantic validation
    errors = []

    if len(cfg.key) != 32:
        errors.append(f"'key' must be exactly 32 hex characters (got {len(cfg.key)})")

    try:
        int(cfg.key, 16)
    except ValueError:
        errors.append("'key' must be a valid hex string")

    if cfg.use_mqtt and not cfg.mqtt_broker_ip:
        errors.append("'mqttbrokerip' must not be empty when useMQTT is true")

    if cfg.use_influxdb and not cfg.influxdb_ip:
        errors.append("'influxdbip' must not be empty when useInfluxdb is true")

    if cfg.baudrate <= 0:
        errors.append(f"'baudrate' must be positive (got {cfg.baudrate})")

    if cfg.min_interval_seconds < 0:
        errors.append(f"'minIntervalSeconds' must not be negative (got {cfg.min_interval_seconds})")

    if errors:
        for e in errors:
            print(f"Config error: {e}")
        sys.exit(4)

    return cfg
