"""InfluxDB client wrapper for writing MeterReading snapshots."""

import logging

from .config import Config
from .models import MeterReading

logger = logging.getLogger(__name__)


class InfluxClient:
    """Writes meter readings to an InfluxDB 1.x database.

    Each field group maps to a separate InfluxDB measurement so that
    Grafana queries and retention policies can be applied independently.
    """

    def __init__(self, config: Config) -> None:
        from influxdb import InfluxDBClient

        self._config = config
        self._client = InfluxDBClient(
            host=config.influxdb_ip,
            port=config.influxdb_port,
            database=config.influxdb_database,
        )
        logger.info(
            "InfluxDB client initialised — %s:%d / %s",
            config.influxdb_ip, config.influxdb_port, config.influxdb_database,
        )

    def write(self, reading: MeterReading) -> bool:
        """Write *reading* to InfluxDB.  Returns True on success.

        Only measurements that have at least one non-None field are written.
        Logs a warning (not an exception) on write failure so the main loop
        can continue.
        """
        points = self._build_points(reading)
        if not points:
            logger.warning("No valid data points to write — skipping InfluxDB write")
            return False

        try:
            ok = self._client.write_points(
                points,
                database=self._config.influxdb_database,
                time_precision="n",
            )
            if ok:
                logger.debug("InfluxDB write OK (%d points)", len(points))
            else:
                logger.error("InfluxDB write_points returned False")
            return bool(ok)
        except Exception:
            logger.exception("Failed to write to InfluxDB")
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_points(self, reading: MeterReading) -> list:
        points = []
        ts = reading.timestamp_ns

        # --- Wirkenergie ---
        fields = {}
        if reading.wirkenergie_bezug is not None:
            fields["Bezug"] = float(reading.wirkenergie_bezug)
        if reading.wirkenergie_lieferung is not None:
            fields["Lieferung"] = float(reading.wirkenergie_lieferung)
        if fields:
            points.append({"measurement": "Wirkenergie", "fields": fields, "time": ts})

        # --- Momentanleistung ---
        fields = {}
        if reading.wirkleistung_bezug is not None:
            fields["Bezug"] = int(reading.wirkleistung_bezug)
        if reading.wirkleistung_lieferung is not None:
            fields["Lieferung"] = int(reading.wirkleistung_lieferung)
        if reading.wirkleistung_gesamt is not None:
            fields["Gesamt"] = int(reading.wirkleistung_gesamt)
        if fields:
            points.append({"measurement": "Momentanleistung", "fields": fields, "time": ts})

        # --- Spannung ---
        fields = {}
        for phase in (1, 2, 3):
            v = getattr(reading, f"spannung_l{phase}")
            if v is not None:
                fields[f"L{phase}"] = float(v)
        if fields:
            points.append({"measurement": "Spannung", "fields": fields, "time": ts})

        # --- Strom ---
        fields = {}
        for phase in (1, 2, 3):
            v = getattr(reading, f"strom_l{phase}")
            if v is not None:
                fields[f"L{phase}"] = float(v)
        if fields:
            points.append({"measurement": "Strom", "fields": fields, "time": ts})

        # --- Leistungsfaktor ---
        if reading.leistungsfaktor is not None:
            points.append({
                "measurement": "Leistungsfaktor",
                "fields": {"value": float(reading.leistungsfaktor)},
                "time": ts,
            })

        return points
