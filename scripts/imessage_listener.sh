#!/usr/bin/env bash
# iMessage → OpenClaw listener
# Watches for new messages from Gabe (+14088028241) and forwards to OpenClaw webchat session
# Usage: bash scripts/imessage_listener.sh [since_rowid]

GABE_NUMBER="+14088028241"
CHAT_ID=3
SINCE_ROWID="${1:-0}"
OC_GATEWAY="http://localhost:18789"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "iMessage listener starting — watching chat $CHAT_ID from rowid $SINCE_ROWID"
log "Forwarding messages from $GABE_NUMBER to OpenClaw"

imsg watch --chat-id "$CHAT_ID" --since-rowid "$SINCE_ROWID" --json | while IFS= read -r line; do
  # Parse the message
  IS_FROM_ME=$(echo "$line" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('is_from_me','false'))" 2>/dev/null)
  
  # Only process inbound messages (not ones I sent)
  if [[ "$IS_FROM_ME" == "False" ]] || [[ "$IS_FROM_ME" == "false" ]]; then
    TEXT=$(echo "$line" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('text',''))" 2>/dev/null)
    ROWID=$(echo "$line" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('id',''))" 2>/dev/null)
    
    if [[ -n "$TEXT" ]] && [[ "$TEXT" != "None" ]] && [[ "$TEXT" != "￼" ]]; then
      log "📱 New message (rowid $ROWID): $TEXT"
      
      # Forward to OpenClaw as a user message via the gateway API
      TOKEN=$(cat ~/.openclaw/token 2>/dev/null || grep -r "token" ~/.openclaw/openclaw.json 2>/dev/null | head -1 | grep -o '"[a-f0-9]*"' | tr -d '"' | head -1)
      
      curl -s -X POST "$OC_GATEWAY/api/message" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "{\"text\": \"[iMessage from Gabe]: $TEXT\", \"channel\": \"imessage\"}" \
        > /dev/null 2>&1
        
      log "✅ Forwarded to OpenClaw"
    fi
  fi
done
