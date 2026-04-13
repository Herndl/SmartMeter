from dataclasses import dataclass
from typing import Optional


@dataclass
class MeterReading:
    """A single snapshot of all values read from the smart meter."""

    timestamp_ns: int  # nanoseconds since epoch (for InfluxDB)

    wirkenergie_bezug: Optional[float] = None      # kWh — cumulative active energy import
    wirkenergie_lieferung: Optional[float] = None  # kWh — cumulative active energy export

    wirkleistung_bezug: Optional[int] = None       # W — instantaneous power import
    wirkleistung_lieferung: Optional[int] = None   # W — instantaneous power export

    spannung_l1: Optional[float] = None  # V
    spannung_l2: Optional[float] = None  # V
    spannung_l3: Optional[float] = None  # V

    strom_l1: Optional[float] = None  # A
    strom_l2: Optional[float] = None  # A
    strom_l3: Optional[float] = None  # A

    leistungsfaktor: Optional[float] = None

    @property
    def wirkleistung_gesamt(self) -> Optional[int]:
        """Net instantaneous power (import minus export) in W."""
        if self.wirkleistung_bezug is not None and self.wirkleistung_lieferung is not None:
            return self.wirkleistung_bezug - self.wirkleistung_lieferung
        return None
