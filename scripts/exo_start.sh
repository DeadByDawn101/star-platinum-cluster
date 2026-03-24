#!/usr/bin/env bash
# Star Platinum — Persistent exo Node Service
# Starts exo in a tmux session that survives SSH disconnects.
# Auto-restarts if exo crashes. Logs to ~/.exo/exo.log
#
# Usage:
#   bash scripts/exo_start.sh          # Start exo in tmux
#   bash scripts/exo_start.sh stop     # Stop exo
#   bash scripts/exo_start.sh status   # Check if running
#   bash scripts/exo_start.sh logs     # Tail the log
#   bash scripts/exo_start.sh attach   # Attach to tmux session
#
# Once started, close your SSH session — exo keeps running.
# Reconnect anytime with: tmux attach -t star-platinum

set -euo pipefail

SESSION="star-platinum"
EXO_DIR="$HOME/Projects/exo"
LOG_DIR="$HOME/.exo"
LOG_FILE="$LOG_DIR/exo.log"
NAMESPACE="star-platinum"

G='\033[0;32m' R='\033[0;31m' C='\033[0;36m' Y='\033[1;33m' N='\033[0m'

mkdir -p "$LOG_DIR"

case "${1:-start}" in

  start)
    # Check if already running
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo -e "${Y}[sp]${N} exo is already running in tmux session '$SESSION'"
        echo -e "${C}[sp]${N} Attach with: tmux attach -t $SESSION"
        echo -e "${C}[sp]${N} Or check:    bash scripts/exo_start.sh status"
        exit 0
    fi

    echo -e "${C}╔════════════════════════════════════════════════╗${N}"
    echo -e "${C}║  「STAR PLATINUM」— Starting exo node            ║${N}"
    echo -e "${C}╚════════════════════════════════════════════════╝${N}"
    echo ""

    # Create tmux session with auto-restart loop
    tmux new-session -d -s "$SESSION" bash -c "
        export PATH=/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH
        while true; do
            echo '========================================'
            echo \"[\$(date)] Starting exo...\"
            echo '========================================'
            cd $EXO_DIR
            MLX_METAL_FAST_SYNCH=1 EXO_LIBP2P_NAMESPACE=$NAMESPACE uv run exo 2>&1 | tee -a $LOG_FILE
            EXIT_CODE=\$?
            echo \"\"
            echo \"[\$(date)] exo exited with code \$EXIT_CODE\"
            echo \"Restarting in 5 seconds... (Ctrl+C to stop)\"
            sleep 5
        done
    "

    echo -e "${G}[ok]${N}  exo started in tmux session '${SESSION}'"
    echo ""
    echo "  Node:     $(scutil --get ComputerName 2>/dev/null || hostname)"
    echo "  Chip:     $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'Apple Silicon')"
    echo "  Memory:   $(python3 -c "import subprocess; r=subprocess.run(['sysctl','-n','hw.memsize'],capture_output=True,text=True); print(str(int(r.stdout.strip()or 0)//1073741824)+'GB')" 2>/dev/null || echo 'unknown')"
    echo "  Log:      $LOG_FILE"
    echo "  Dashboard: http://localhost:52415"
    echo ""
    echo -e "${C}  Commands:${N}"
    echo "    tmux attach -t $SESSION     # View live output"
    echo "    bash scripts/exo_start.sh stop    # Stop exo"
    echo "    bash scripts/exo_start.sh status  # Check status"
    echo "    bash scripts/exo_start.sh logs    # Tail logs"
    echo ""
    echo -e "${G}  Safe to close SSH — exo keeps running.${N}"
    ;;

  stop)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux kill-session -t "$SESSION"
        pkill -f "EXO_LIBP2P_NAMESPACE" 2>/dev/null || true
        echo -e "${R}[sp]${N} exo stopped"
    else
        echo -e "${Y}[sp]${N} exo is not running"
    fi
    ;;

  restart)
    $0 stop
    sleep 2
    $0 start
    ;;

  status)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo -e "${G}[sp]${N} exo is RUNNING in tmux session '$SESSION'"
        echo ""
        # Show last few log lines
        if [[ -f "$LOG_FILE" ]]; then
            echo "  Last 5 log lines:"
            tail -5 "$LOG_FILE" | sed 's/^/    /'
        fi
        echo ""
        echo "  Attach: tmux attach -t $SESSION"
    else
        echo -e "${R}[sp]${N} exo is NOT running"
        echo "  Start:  bash scripts/exo_start.sh"
    fi
    ;;

  logs)
    if [[ -f "$LOG_FILE" ]]; then
        tail -f "$LOG_FILE"
    else
        echo "No log file yet — start exo first"
    fi
    ;;

  attach)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux attach -t "$SESSION"
    else
        echo -e "${R}[sp]${N} No tmux session — start exo first"
    fi
    ;;

  *)
    echo "Usage: $0 {start|stop|restart|status|logs|attach}"
    ;;
esac
