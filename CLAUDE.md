# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Reads encrypted M-Bus data from an EVN Sagemcom T210-D smart meter via serial port, decrypts it with AES-128-GCM, parses DLMS/OBIS codes, and publishes readings to MQTT and/or InfluxDB. Designed to run as a systemd service on Linux.

## Running the Service

```bash
# Run directly
python3 AusleseSkript.py

# Systemd service management
sudo systemctl start smartmeter.service
sudo systemctl stop smartmeter.service
sudo journalctl -u smartmeter.service -f
```

There is no build step, no virtual environment, and no test suite. Dependencies are installed system-wide via `install.sh`.

## Configuration

All config lives in `config.json` (gitignored — use `config-Beispiel.json` as template). Key fields:

- `port` / `baudrate`: Serial device (typically `/dev/ttyUSB0`, 2400 baud)
- `key`: 32-char hex AES key obtained from EVN
- `useMQTT` / `useInfluxdb`: Toggle output channels
- `minIntervalSeconds`: Rate-limit writes (0 = every frame, ~330ms apart)
- `printValue`: Print readings to stdout
- `logLevel`: DEBUG/INFO/WARNING/ERROR

## Architecture & Data Flow

```
Serial port (282-byte M-Bus frame)
  → decrypt.py     AES-128-GCM decryption using EVN key
  → parser.py      gurux_dlms XML → OBIS code extraction → MeterReading
  → runner.py      Rate limiting, fan-out to outputs
      ├── mqtt_client.py    12 topics under Smartmeter/*, QoS=1, retain=True
      └── influx_client.py  5 InfluxDB measurements, nanosecond precision
```

**`runner.py`** is the orchestrator: opens serial port, runs the main loop, handles SIGTERM/SIGINT gracefully, and coordinates all output clients.

**`models.py`** defines `MeterReading` — a dataclass with ~15 optional fields (voltages, currents, power, energy) plus a computed `wirkleistung_gesamt` (net power = import − export).

**`config.py`** validates the JSON config at startup — checks key length, required IPs when integrations are enabled, type coercion.

## External Integrations

**MQTT** (paho-mqtt 1.6.1): Topics like `Smartmeter/SpannungL1`, `Smartmeter/WirkleistungBezug`, etc. Auto-reconnects with 5s retry. Uses background thread (`loop_start()`).

**InfluxDB 1.x** (influxdb library): Database "SmartMeter", measurements: `Wirkenergie`, `Momentanleistung`, `Spannung`, `Strom`, `Leistungsfaktor`. Writes are synchronous; errors are logged but don't crash the loop.

**Grafana**: Pre-built dashboard in `Grafana-Dashboard.json` (Grafana 12 compatible). Import via Grafana UI.

## German Terminology

The codebase mixes German and English. Key terms:
- *Bezug* = import (consuming from grid), *Lieferung* = export (feeding to grid)
- *Wirkenergie* = active energy (kWh), *Wirkleistung* = active power (W)
- *Spannung* = voltage, *Strom* = current, *Leistungsfaktor* = power factor
