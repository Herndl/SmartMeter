#!/bin/bash
set -euo pipefail

dateipfad="$(cd "$(dirname "$0")" && pwd)"
filename="/etc/systemd/system/smartmeter.service"

sudo tee "$filename" >/dev/null <<EOF
[Unit]
Description=SmartMeterData Script
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/stefan/smartMeter/AusleseSkript.py
WorkingDirectory=/home/stefan/smartMeter
Restart=always
RestartSec=10
User=root

# optional, aber sehr hilfreich:
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "File $filename created."

sudo systemctl daemon-reload
sudo systemctl enable --now smartmeter.service
sudo systemctl restart smartmeter.service
