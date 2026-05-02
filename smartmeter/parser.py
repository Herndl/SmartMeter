"""DLMS/OBIS frame parsing: APDU hex string -> MeterReading."""

import logging
import time
import xml.etree.ElementTree as ET

from gurux_dlms.GXDLMSTranslator import GXDLMSTranslator

from .models import MeterReading

logger = logging.getLogger(__name__)

# OBIS code (hex) -> internal field name (pre-scaling)
OBIS_MAP: dict[str, str] = {
    "0100010800FF": "wirkenergie_bezug_raw",
    "0100020800FF": "wirkenergie_lieferung_raw",
    "0100010700FF": "wirkleistung_bezug_raw",
    "0100020700FF": "wirkleistung_lieferung_raw",
    "0100200700FF": "spannung_l1_raw",
    "0100340700FF": "spannung_l2_raw",
    "0100480700FF": "spannung_l3_raw",
    "01001F0700FF": "strom_l1_raw",
    "0100330700FF": "strom_l2_raw",
    "0100470700FF": "strom_l3_raw",
    "01000D0700FF": "leistungsfaktor_raw",
}


def parse_apdu(apdu: str) -> MeterReading:
    """Parse a decrypted APDU hex string into a MeterReading.

    Raises:
        ET.ParseError: if the DLMS translator returns malformed XML.
        Exception: for unexpected errors during parsing.
    """
    xml_str = GXDLMSTranslator().pduToXml(apdu)
    root = ET.fromstring(xml_str)

    raw: dict[str, int] = {}
    items = list(root.iter())
    for i, child in enumerate(items):
        if child.tag != "OctetString" or "Value" not in child.attrib:
            continue
        obis = child.attrib["Value"]
        if obis not in OBIS_MAP:
            continue
        # The value for this OBIS code is in the immediately following element
        if i + 1 < len(items) and "Value" in items[i + 1].attrib:
            try:
                raw[OBIS_MAP[obis]] = int(items[i + 1].attrib["Value"], 16)
            except ValueError:
                logger.warning("Could not parse value for OBIS %s: %r", obis, items[i + 1].attrib["Value"])

    def _get(key: str):
        return raw.get(key)

    # Log which OBIS codes were present so interval/provider changes are visible
    logger.debug("Parsed OBIS codes: %s", list(raw.keys()))

    return MeterReading(
        timestamp_ns=int(time.time() * 1_000_000_000),
        # Wh -> kWh
        wirkenergie_bezug=(raw["wirkenergie_bezug_raw"] / 1000
                           if "wirkenergie_bezug_raw" in raw else None),
        wirkenergie_lieferung=(raw["wirkenergie_lieferung_raw"] / 1000
                               if "wirkenergie_lieferung_raw" in raw else None),
        # W — no scaling
        wirkleistung_bezug=_get("wirkleistung_bezug_raw"),
        wirkleistung_lieferung=_get("wirkleistung_lieferung_raw"),
        # 0.1 V per unit
        spannung_l1=(raw["spannung_l1_raw"] * 0.1 if "spannung_l1_raw" in raw else None),
        spannung_l2=(raw["spannung_l2_raw"] * 0.1 if "spannung_l2_raw" in raw else None),
        spannung_l3=(raw["spannung_l3_raw"] * 0.1 if "spannung_l3_raw" in raw else None),
        # 0.01 A per unit
        strom_l1=(raw["strom_l1_raw"] * 0.01 if "strom_l1_raw" in raw else None),
        strom_l2=(raw["strom_l2_raw"] * 0.01 if "strom_l2_raw" in raw else None),
        strom_l3=(raw["strom_l3_raw"] * 0.01 if "strom_l3_raw" in raw else None),
        # 0.001 per unit
        leistungsfaktor=(raw["leistungsfaktor_raw"] * 0.001
                         if "leistungsfaktor_raw" in raw else None),
    )
