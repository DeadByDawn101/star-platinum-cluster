#!/usr/bin/env bash
# Star Platinum — Close the TB4 Ring
# Run AFTER plugging the M1 Pro → Brain cable
# Usage: bash scripts/setup_ring.sh

set -euo pipefail

BRAIN_IFACE="${1:-en1}"  # Brain port connected to M1 Pro (en1 or en3)
BRAIN_IP="10.42.1.1"
M1_IP="10.42.1.5"

echo "🖤 Closing the Star Platinum ring..."
echo "   Brain port: $BRAIN_IFACE → $BRAIN_IP"
echo "   M1 Pro:     $M1_IP"
echo ""

# Brain side
echo "► Configuring brain ring port ($BRAIN_IFACE)..."
sudo /sbin/ifconfig $BRAIN_IFACE inet $BRAIN_IP netmask 255.255.255.0
sudo /sbin/networksetup -setMTU "$(networksetup -listallhardwareports | grep -B1 $BRAIN_IFACE | grep 'Hardware Port' | sed 's/Hardware Port: //')" 9000 2>/dev/null || true
echo "   Brain: $BRAIN_IP on $BRAIN_IFACE ✅"

# M1 Pro side
echo "► Configuring M1 Pro ring port..."
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 admin@Node-3-m1pro.local "
sudo /sbin/ifconfig en2 inet $M1_IP netmask 255.255.255.0
echo 'M1 Pro ring port configured ✅'
" 

# Test the ring close
echo ""
echo "► Testing ring close..."
sleep 2
RESULT=$(/sbin/ping -c 3 $M1_IP 2>&1 | grep -E "received|loss")
echo "   Brain → M1 Pro: $RESULT"

echo ""
echo "🖤 Ring closed! Run: exo-pipe mlx-community/Llama-3.3-70B-Instruct-4bit"
