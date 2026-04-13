"""Main read/decrypt/publish loop for the SmartMeter service."""

import logging
import signal
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import serial

from .config import Config, load_config
from .decrypt import FRAME_SIZE, evn_decrypt, extract_frame_parts, validate_mbus_start
from .influx_client import InfluxClient
from .models import MeterReading
from .mqtt_client import MQTTClient
from .parser import parse_apdu

logger = logging.getLogger(__name__)

# How long ser.read() waits before giving up and looping again.
# This ensures SIGTERM is not blocked by a hanging read.
_SERIAL_TIMEOUT = 30  # seconds


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _print_reading(reading: MeterReading) -> None:
    """Print a formatted table of the current reading to stdout."""

    def fmt(value, digits: int = 2) -> str:
        return str(round(value, digits)) if value is not None else "N/A"

    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    print(f"\n\t\t*** KUNDENSCHNITTSTELLE ***\n")
    print(f"  {now}")
    print(f"  OBIS Code        Bezeichnung                    Wert")
    print(f"  1.0.32.7.0.255   Spannung L1 (V):               {fmt(reading.spannung_l1)}")
    print(f"  1.0.52.7.0.255   Spannung L2 (V):               {fmt(reading.spannung_l2)}")
    print(f"  1.0.72.7.0.255   Spannung L3 (V):               {fmt(reading.spannung_l3)}")
    print(f"  1.0.31.7.0.255   Strom L1 (A):                  {fmt(reading.strom_l1)}")
    print(f"  1.0.51.7.0.255   Strom L2 (A):                  {fmt(reading.strom_l2)}")
    print(f"  1.0.71.7.0.255   Strom L3 (A):                  {fmt(reading.strom_l3)}")
    print(f"  1.0.1.7.0.255    Wirkleistung Bezug (W):        {reading.wirkleistung_bezug}")
    print(f"  1.0.2.7.0.255    Wirkleistung Lieferung (W):    {reading.wirkleistung_lieferung}")
    print(f"  1.0.1.8.0.255    Wirkenergie Bezug (kWh):       {reading.wirkenergie_bezug}")
    print(f"  1.0.2.8.0.255    Wirkenergie Lieferung (kWh):   {reading.wirkenergie_lieferung}")
    print(f"  -------------    Leistungsfaktor:               {fmt(reading.leistungsfaktor, 3)}")
    print(f"  -------------    Wirkleistung gesamt (W):       {reading.wirkleistung_gesamt}")


def _open_serial(config: Config) -> serial.Serial:
    return serial.Serial(
        port=config.port,
        baudrate=config.baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=_SERIAL_TIMEOUT,
    )


def main() -> None:
    config = load_config()
    setup_logging(config.log_level)

    logger.info(
        "SmartMeter starting — port=%s  baudrate=%d  MQTT=%s  InfluxDB=%s",
        config.port, config.baudrate, config.use_mqtt, config.use_influxdb,
    )
    if config.min_interval_seconds > 0:
        logger.info("Minimum write interval: %.1f s", config.min_interval_seconds)

    # ------------------------------------------------------------------ #
    # Graceful shutdown via SIGTERM / Ctrl-C                              #
    # ------------------------------------------------------------------ #
    stop_event = threading.Event()

    def _shutdown(signum, _frame) -> None:
        logger.info("Shutdown signal received (signal %d) — stopping", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # ------------------------------------------------------------------ #
    # Initialise outputs (non-fatal at startup — will retry per frame)   #
    # ------------------------------------------------------------------ #
    mqtt: Optional[MQTTClient] = None
    if config.use_mqtt:
        mqtt = MQTTClient(config)
        try:
            mqtt.connect()
        except ConnectionError:
            logger.warning(
                "Could not connect to MQTT broker at startup — will retry on each publish"
            )

    influx: Optional[InfluxClient] = None
    if config.use_influxdb:
        try:
            influx = InfluxClient(config)
        except Exception:
            logger.exception("Could not initialise InfluxDB client — InfluxDB writes disabled")

    # ------------------------------------------------------------------ #
    # Main loop                                                           #
    # ------------------------------------------------------------------ #
    ser = _open_serial(config)
    last_write_time = 0.0

    try:
        while not stop_event.is_set():

            # --- 1. Read raw bytes from serial port ---
            raw_bytes = ser.read(FRAME_SIZE)
            if stop_event.is_set():
                break

            if len(raw_bytes) < FRAME_SIZE:
                logger.warning(
                    "Short serial read: got %d of %d bytes — timeout or disconnect, retrying",
                    len(raw_bytes), FRAME_SIZE,
                )
                continue

            daten = raw_bytes.hex()

            # --- 2. Validate M-Bus frame header ---
            if not validate_mbus_start(daten):
                logger.warning(
                    "Invalid M-Bus frame header (first 4 bytes: %s) — flushing buffers",
                    daten[0:8],
                )
                time.sleep(2.5)
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                continue  # discard this frame entirely

            logger.debug("M-Bus frame header OK")

            # --- 3. Decrypt ---
            try:
                system_title, frame_counter, frame = extract_frame_parts(daten)
                apdu = evn_decrypt(frame, config.key, system_title, frame_counter)
            except Exception:
                logger.exception("Decryption failed — skipping frame")
                continue

            if not apdu.startswith("0f80"):
                logger.debug("Unexpected APDU header %r — skipping", apdu[:8])
                continue

            # --- 4. Parse OBIS values ---
            try:
                reading = parse_apdu(apdu)
            except ET.ParseError:
                logger.exception("XML parse error in APDU — skipping frame")
                continue
            except Exception:
                logger.exception("Unexpected error parsing APDU — skipping frame")
                continue

            # --- 5. Apply minimum write interval (rate limiting) ---
            now = time.monotonic()
            if config.min_interval_seconds > 0 and (now - last_write_time) < config.min_interval_seconds:
                logger.debug(
                    "Skipping output — %.1fs since last write (min=%.1fs)",
                    now - last_write_time, config.min_interval_seconds,
                )
                continue

            last_write_time = now

            logger.info(
                "Reading — Bezug: %.3f kWh  Lieferung: %.3f kWh  Leistung: %s W",
                reading.wirkenergie_bezug or 0.0,
                reading.wirkenergie_lieferung or 0.0,
                reading.wirkleistung_gesamt,
            )

            # --- 6. Output ---
            if config.print_value:
                _print_reading(reading)

            if mqtt:
                mqtt.publish(reading)

            if influx:
                influx.write(reading)

    finally:
        logger.info("Closing serial port %s", config.port)
        ser.close()
        if mqtt:
            mqtt.disconnect()
        logger.info("SmartMeter stopped")
