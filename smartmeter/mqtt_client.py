"""MQTT client wrapper with persistent connection and automatic reconnection."""

import logging
import threading
import time
from typing import Optional

from .config import Config
from .models import MeterReading

logger = logging.getLogger(__name__)

# (MQTT topic, MeterReading attribute name)
_TOPIC_MAP = [
    ("Smartmeter/WirkenergieBezug",    "wirkenergie_bezug"),
    ("Smartmeter/WirkenergieLieferung","wirkenergie_lieferung"),
    ("Smartmeter/WirkleistungBezug",   "wirkleistung_bezug"),
    ("Smartmeter/WirkleistungLieferung","wirkleistung_lieferung"),
    ("Smartmeter/Wirkleistunggesamt",  "wirkleistung_gesamt"),
    ("Smartmeter/SpannungL1",          "spannung_l1"),
    ("Smartmeter/SpannungL2",          "spannung_l2"),
    ("Smartmeter/SpannungL3",          "spannung_l3"),
    ("Smartmeter/StromL1",             "strom_l1"),
    ("Smartmeter/StromL2",             "strom_l2"),
    ("Smartmeter/StromL3",             "strom_l3"),
    ("Smartmeter/Leistungsfaktor",     "leistungsfaktor"),
]

_CONNECT_TIMEOUT = 10.0   # seconds to wait for initial connection
_RECONNECT_DELAY = 5.0    # seconds to wait before a reconnect attempt


class MQTTClient:
    """Persistent MQTT client that publishes meter readings.

    Uses paho-mqtt's background network loop (loop_start) so that
    publish() calls are dispatched without blocking the main thread.
    Reconnects automatically when the broker drops the connection.
    """

    def __init__(self, config: Config) -> None:
        import paho.mqtt.client as mqtt

        self._config = config
        self._connected = False
        self._lock = threading.Lock()

        self._client = mqtt.Client(client_id="SmartMeter", clean_session=True)
        if config.mqtt_broker_user:
            self._client.username_pw_set(config.mqtt_broker_user, config.mqtt_broker_password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    # ------------------------------------------------------------------
    # paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            with self._lock:
                self._connected = True
            logger.info("Connected to MQTT broker %s:%d",
                        self._config.mqtt_broker_ip, self._config.mqtt_broker_port)
        else:
            logger.error("MQTT connection refused (rc=%d)", rc)

    def _on_disconnect(self, client, userdata, rc) -> None:
        with self._lock:
            self._connected = False
        if rc != 0:
            logger.warning("Unexpected MQTT disconnect (rc=%d) — will reconnect on next publish", rc)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to the broker and start the background network loop.

        Raises ConnectionError if the broker is unreachable within the timeout.
        """
        self._client.connect(
            self._config.mqtt_broker_ip,
            self._config.mqtt_broker_port,
            keepalive=60,
        )
        self._client.loop_start()

        deadline = time.monotonic() + _CONNECT_TIMEOUT
        while time.monotonic() < deadline:
            with self._lock:
                if self._connected:
                    return
            time.sleep(0.1)

        raise ConnectionError(
            f"Could not connect to MQTT broker at "
            f"{self._config.mqtt_broker_ip}:{self._config.mqtt_broker_port} "
            f"within {_CONNECT_TIMEOUT}s"
        )

    def publish(self, reading: MeterReading) -> None:
        """Publish all non-None values from *reading* to their MQTT topics.

        QoS 1 ensures at-least-once delivery.
        retain=True ensures Home Assistant receives the last value immediately
        after any reconnect.
        Silently skips publish if the broker is unreachable.
        """
        if not self._ensure_connected():
            logger.warning("Skipping MQTT publish — broker not reachable")
            return

        for topic, attr in _TOPIC_MAP:
            value = getattr(reading, attr, None)
            if value is not None:
                self._client.publish(topic, payload=value, qos=1, retain=True)

    def disconnect(self) -> None:
        """Stop the network loop and cleanly disconnect from the broker."""
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("MQTT client disconnected")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> bool:
        with self._lock:
            if self._connected:
                return True

        logger.info("MQTT not connected — attempting reconnect")
        try:
            self._client.reconnect()
        except Exception as exc:
            logger.warning("MQTT reconnect failed: %s", exc)
            return False

        # Give the loop a moment to process the reconnect acknowledgement
        deadline = time.monotonic() + _RECONNECT_DELAY
        while time.monotonic() < deadline:
            with self._lock:
                if self._connected:
                    return True
            time.sleep(0.2)

        logger.warning("MQTT reconnect timed out after %.1fs", _RECONNECT_DELAY)
        return False
