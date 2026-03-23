#!/bin/bash
#
# TB4 Network Setup Script for Star Platinum Cluster
# 
# This script configures Thunderbolt network interfaces for optimal
# tensor transport performance between cluster nodes.
#
# Features:
# - MTU 9000 (jumbo frames) for high throughput
# - Static IP assignment for predictable routing
# - TCP tuning for low latency
#
# Usage:
#   ./setup_tb4_network.sh                    # Interactive mode
#   ./setup_tb4_network.sh --node brain       # Set up as brain node
#   ./setup_tb4_network.sh --node m1pro       # Set up as M1 Pro node
#   ./setup_tb4_network.sh --check            # Check current config
#
# RavenX LLC - Star Platinum Cluster
#

set -e

# =============================================================================
# Configuration
# =============================================================================

# MTU size (9000 = jumbo frames, 1500 = standard)
MTU=9000

# IP addressing scheme for TB4 ring
# Each node gets IPs on its connected interfaces
# Format: 169.254.x.y where x = node, y = interface
declare -A NODE_IPS=(
    ["brain_1"]="169.254.1.1"    # M4 Max TB5 port 1 -> M1 Pro
    ["brain_2"]="169.254.5.1"    # M4 Max TB5 port 3 -> M3
    ["m1pro_1"]="169.254.1.2"    # M1 Pro -> M4 Max
    ["m1pro_2"]="169.254.2.2"    # M1 Pro -> iMac Pro
    ["imac_1"]="169.254.2.3"     # iMac Pro -> M1 Pro
    ["imac_2"]="169.254.3.3"     # iMac Pro -> M2 Pro
    ["m2pro_1"]="169.254.3.4"    # M2 Pro -> iMac Pro
    ["m2pro_2"]="169.254.4.4"    # M2 Pro -> M3
    ["m3_1"]="169.254.4.5"       # M3 -> M2 Pro
    ["m3_2"]="169.254.5.5"       # M3 -> M4 Max
)

# SSH config for remote nodes (for cluster-wide setup)
SSH_KEY="${HOME}/.ssh/id_ed25519"
declare -A SSH_HOSTS=(
    ["m1pro"]="admin@Node-3-m1pro.local"
    ["m2pro"]="admon@macbook-m2.local"
    ["m3"]="node1@100.90.247.62"
)

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo "ℹ️  $1"
}

log_success() {
    echo "✅ $1"
}

log_warning() {
    echo "⚠️  $1"
}

log_error() {
    echo "❌ $1"
}

get_tb_interfaces() {
    # Get list of Thunderbolt network interfaces
    networksetup -listallhardwareports 2>/dev/null | \
        grep -A1 -i "thunderbolt" | \
        grep "Device:" | \
        awk '{print $2}'
}

get_interface_status() {
    local iface=$1
    /sbin/ifconfig "$iface" 2>/dev/null | grep "status:" | awk '{print $2}'
}

get_interface_ip() {
    local iface=$1
    /sbin/ifconfig "$iface" 2>/dev/null | grep "inet " | awk '{print $2}'
}

get_interface_mtu() {
    local iface=$1
    /sbin/ifconfig "$iface" 2>/dev/null | grep "mtu" | awk '{for(i=1;i<=NF;i++) if($i=="mtu") print $(i+1)}'
}

# =============================================================================
# Check Mode
# =============================================================================

check_config() {
    echo "🌩️ Star Platinum TB4 Network Status"
    echo "===================================="
    echo ""
    
    # Check RDMA status
    if command -v rdma_ctl &>/dev/null; then
        RDMA_STATUS=$(rdma_ctl status 2>/dev/null || echo "unknown")
        echo "RDMA Status: $RDMA_STATUS"
    else
        echo "RDMA Status: rdma_ctl not found"
    fi
    echo ""
    
    # List TB interfaces
    echo "Thunderbolt Interfaces:"
    echo "-----------------------"
    
    TB_IFACES=$(get_tb_interfaces)
    if [ -z "$TB_IFACES" ]; then
        log_warning "No Thunderbolt interfaces found"
        return
    fi
    
    for iface in $TB_IFACES; do
        STATUS=$(get_interface_status "$iface")
        IP=$(get_interface_ip "$iface")
        MTU_VAL=$(get_interface_mtu "$iface")
        
        if [ "$STATUS" = "active" ]; then
            STATUS_ICON="🟢"
        else
            STATUS_ICON="🔴"
        fi
        
        echo "$STATUS_ICON $iface: status=$STATUS, IP=${IP:-none}, MTU=${MTU_VAL:-unknown}"
    done
    
    echo ""
    
    # Check connectivity to other nodes
    echo "Node Connectivity:"
    echo "------------------"
    
    for node in "${!SSH_HOSTS[@]}"; do
        host="${SSH_HOSTS[$node]}"
        if ssh -i "$SSH_KEY" -o ConnectTimeout=2 -o BatchMode=yes "$host" "exit 0" 2>/dev/null; then
            echo "🟢 $node ($host): reachable"
        else
            echo "🔴 $node ($host): not reachable"
        fi
    done
}

# =============================================================================
# Setup Mode
# =============================================================================

configure_interface() {
    local iface=$1
    local ip=$2
    
    log_info "Configuring $iface with IP $ip, MTU $MTU"
    
    # Set MTU
    sudo /sbin/ifconfig "$iface" mtu "$MTU" || log_warning "Failed to set MTU on $iface"
    
    # Set IP
    sudo /sbin/ifconfig "$iface" inet "$ip" netmask 255.255.255.0 up || log_warning "Failed to set IP on $iface"
    
    log_success "$iface configured"
}

setup_node() {
    local node=$1
    
    echo "🌩️ Setting up TB4 network for node: $node"
    echo ""
    
    TB_IFACES=$(get_tb_interfaces)
    if [ -z "$TB_IFACES" ]; then
        log_error "No Thunderbolt interfaces found"
        exit 1
    fi
    
    # Get array of interfaces
    IFS=$'\n' read -r -d '' -a IFACE_ARRAY <<< "$TB_IFACES" || true
    
    # Configure based on node
    case $node in
        brain|m4max)
            if [ ${#IFACE_ARRAY[@]} -ge 1 ]; then
                configure_interface "${IFACE_ARRAY[0]}" "${NODE_IPS[brain_1]}"
            fi
            if [ ${#IFACE_ARRAY[@]} -ge 2 ]; then
                configure_interface "${IFACE_ARRAY[1]}" "${NODE_IPS[brain_2]}"
            fi
            ;;
        m1pro)
            if [ ${#IFACE_ARRAY[@]} -ge 1 ]; then
                configure_interface "${IFACE_ARRAY[0]}" "${NODE_IPS[m1pro_1]}"
            fi
            if [ ${#IFACE_ARRAY[@]} -ge 2 ]; then
                configure_interface "${IFACE_ARRAY[1]}" "${NODE_IPS[m1pro_2]}"
            fi
            ;;
        imac)
            if [ ${#IFACE_ARRAY[@]} -ge 1 ]; then
                configure_interface "${IFACE_ARRAY[0]}" "${NODE_IPS[imac_1]}"
            fi
            if [ ${#IFACE_ARRAY[@]} -ge 2 ]; then
                configure_interface "${IFACE_ARRAY[1]}" "${NODE_IPS[imac_2]}"
            fi
            ;;
        m2pro)
            if [ ${#IFACE_ARRAY[@]} -ge 1 ]; then
                configure_interface "${IFACE_ARRAY[0]}" "${NODE_IPS[m2pro_1]}"
            fi
            if [ ${#IFACE_ARRAY[@]} -ge 2 ]; then
                configure_interface "${IFACE_ARRAY[1]}" "${NODE_IPS[m2pro_2]}"
            fi
            ;;
        m3)
            if [ ${#IFACE_ARRAY[@]} -ge 1 ]; then
                configure_interface "${IFACE_ARRAY[0]}" "${NODE_IPS[m3_1]}"
            fi
            if [ ${#IFACE_ARRAY[@]} -ge 2 ]; then
                configure_interface "${IFACE_ARRAY[1]}" "${NODE_IPS[m3_2]}"
            fi
            ;;
        *)
            log_error "Unknown node: $node"
            echo "Valid nodes: brain, m1pro, imac, m2pro, m3"
            exit 1
            ;;
    esac
    
    echo ""
    log_success "Node $node configured"
}

setup_all_nodes() {
    echo "🌩️ Setting up TB4 network on all cluster nodes"
    echo ""
    
    # Setup local node (assumed to be brain)
    setup_node "brain"
    
    # Setup remote nodes
    for node in "${!SSH_HOSTS[@]}"; do
        host="${SSH_HOSTS[$node]}"
        log_info "Setting up $node at $host..."
        
        if ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$host" "true" 2>/dev/null; then
            # Copy this script to remote and run it
            scp -i "$SSH_KEY" "$0" "${host}:/tmp/setup_tb4_network.sh"
            ssh -i "$SSH_KEY" "$host" "chmod +x /tmp/setup_tb4_network.sh && /tmp/setup_tb4_network.sh --node $node"
        else
            log_warning "Cannot reach $node, skipping"
        fi
    done
    
    log_success "All nodes configured"
}

# =============================================================================
# TCP Tuning
# =============================================================================

tune_tcp() {
    echo "🔧 Applying TCP performance tuning..."
    
    # macOS uses different sysctl names than Linux
    # These settings optimize for low-latency high-bandwidth transfers
    
    # Increase max socket buffer sizes (requires root)
    sudo sysctl -w kern.ipc.maxsockbuf=8388608 2>/dev/null || true
    sudo sysctl -w net.inet.tcp.sendspace=2097152 2>/dev/null || true
    sudo sysctl -w net.inet.tcp.recvspace=2097152 2>/dev/null || true
    
    # Disable delayed ACKs for lower latency
    sudo sysctl -w net.inet.tcp.delayed_ack=0 2>/dev/null || true
    
    # Enable TCP timestamps for better RTT estimation
    sudo sysctl -w net.inet.tcp.rfc1323=1 2>/dev/null || true
    
    log_success "TCP tuning applied"
}

# =============================================================================
# Enable RDMA
# =============================================================================

enable_rdma() {
    echo "🚀 Checking RDMA status..."
    
    if ! command -v rdma_ctl &>/dev/null; then
        log_warning "rdma_ctl not found - RDMA may not be available on this macOS version"
        return
    fi
    
    RDMA_STATUS=$(rdma_ctl status 2>/dev/null || echo "unknown")
    
    if [ "$RDMA_STATUS" = "enabled" ]; then
        log_success "RDMA is already enabled"
    elif [ "$RDMA_STATUS" = "disabled" ]; then
        log_warning "RDMA is disabled. To enable, boot into Recovery Mode and run:"
        echo "        rdma_ctl enable"
        echo "        Then reboot"
    else
        log_warning "RDMA status unknown: $RDMA_STATUS"
    fi
}

# =============================================================================
# Main
# =============================================================================

show_help() {
    echo "Star Platinum TB4 Network Setup"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --check           Check current TB4 network status"
    echo "  --node NAME       Set up specific node (brain, m1pro, imac, m2pro, m3)"
    echo "  --all             Set up all nodes in cluster"
    echo "  --tune            Apply TCP performance tuning"
    echo "  --rdma            Check/enable RDMA"
    echo "  -h, --help        Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 --check                 # Show current status"
    echo "  $0 --node brain            # Configure brain (M4 Max) node"
    echo "  $0 --node m1pro --tune     # Configure M1 Pro with TCP tuning"
    echo "  $0 --all                   # Configure all cluster nodes"
}

# Parse arguments
MODE=""
NODE=""
DO_TUNE=false
DO_RDMA=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            MODE="check"
            shift
            ;;
        --node)
            MODE="node"
            NODE="$2"
            shift 2
            ;;
        --all)
            MODE="all"
            shift
            ;;
        --tune)
            DO_TUNE=true
            shift
            ;;
        --rdma)
            DO_RDMA=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Execute
case $MODE in
    check)
        check_config
        ;;
    node)
        if [ -z "$NODE" ]; then
            log_error "Node name required"
            exit 1
        fi
        setup_node "$NODE"
        ;;
    all)
        setup_all_nodes
        ;;
    "")
        # Interactive mode or just tune/rdma
        if [ "$DO_TUNE" = true ] || [ "$DO_RDMA" = true ]; then
            :  # Continue to tune/rdma below
        else
            check_config
        fi
        ;;
esac

# Apply TCP tuning if requested
if [ "$DO_TUNE" = true ]; then
    tune_tcp
fi

# Check RDMA if requested
if [ "$DO_RDMA" = true ]; then
    enable_rdma
fi

echo ""
echo "Done! 🌩️"
