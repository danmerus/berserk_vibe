#!/bin/bash
# Berserk Game Server - AWS Deployment Script
# Run this on your EC2 instance after cloning the repo

set -e  # Exit on error

echo "=== Berserk Server Deployment ==="

# Install Python if needed
if ! command -v python3.11 &> /dev/null; then
    echo "Installing Python 3.11..."
    sudo dnf install python3.11 -y
fi

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/berserk.service > /dev/null << EOF
[Unit]
Description=Berserk Game Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/python3.11 -m src.network.server --host 0.0.0.0 --port 7777
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
echo "Starting server..."
sudo systemctl daemon-reload
sudo systemctl enable berserk
sudo systemctl restart berserk

# Show status
sleep 2
echo ""
echo "=== Server Status ==="
sudo systemctl status berserk --no-pager

echo ""
echo "=== Done! ==="
echo "Server running on port 7777"
echo ""
echo "Useful commands:"
echo "  View logs:     sudo journalctl -u berserk -f"
echo "  Restart:       sudo systemctl restart berserk"
echo "  Stop:          sudo systemctl stop berserk"
