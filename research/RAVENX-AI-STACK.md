# RavenX AI Trading Intelligence Stack

## Executive Summary

This document defines the complete AI stack for RavenX trading intelligence, integrating:
- **LeWM**: Market world model for state prediction
- **SELF**: Self-evolving LLM analyst
- **MiroFish**: Multi-agent simulation
- **Maya**: Trading execution engine

**Goal:** Zero-latency, locally-trained trading intelligence that learns from every trade.

---

## 1. Full Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        RAVENX TRADING INTELLIGENCE STACK                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                         DATA INGESTION LAYER                              │   │
│  │                                                                           │   │
│  │  Binance WS ─────┐                                                        │   │
│  │  Coinbase WS ────┼──▶ Unified Market Feed ──▶ OHLCV + Order Book         │   │
│  │  DEX Feeds ──────┘                             (5m, 15m, 1h candles)      │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                          WORLD MODEL LAYER                                │   │
│  │                                                                           │   │
│  │         ┌─────────────────────────────────────────────────┐              │   │
│  │         │              LeWM-MARKET (15M params)            │              │   │
│  │         │                                                  │              │   │
│  │         │   Market Frame [4, 60, 64]                      │              │   │
│  │         │        │                                        │              │   │
│  │         │        ▼                                        │              │   │
│  │         │   ┌────────────┐    ┌────────────┐             │              │   │
│  │         │   │  Encoder   │───▶│  z_t [256] │             │              │   │
│  │         │   │  (ViT-Tiny)│    │   latent   │             │              │   │
│  │         │   └────────────┘    └─────┬──────┘             │              │   │
│  │         │                           │                     │              │   │
│  │         │                    ┌──────┴──────┐             │              │   │
│  │         │                    │  Predictor  │             │              │   │
│  │         │   Action ─────────▶│  z_t + a_t  │             │              │   │
│  │         │   (buy/sell/hold)  │  → ẑ_{t+1}  │             │              │   │
│  │         │                    └──────┬──────┘             │              │   │
│  │         │                           │                     │              │   │
│  │         │                           ▼                     │              │   │
│  │         │              Predicted Market State             │              │   │
│  │         │              (6-step lookahead)                │              │   │
│  │         │                                                  │              │   │
│  │         └──────────────────────────────────────────────────┘              │   │
│  │                                        │                                  │   │
│  │                                        ▼                                  │   │
│  │                          LeWM Confidence Score                            │   │
│  │                          (how certain is predicted path?)                │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                       LLM ANALYSIS LAYER                                  │   │
│  │                                                                           │   │
│  │      ┌──────────────────────────────────────────────────────────────┐    │   │
│  │      │        SELF-EVOLVED TRADING ANALYST (Llama 3.3 70B)          │    │   │
│  │      │                                                               │    │   │
│  │      │  Input:                                                       │    │   │
│  │      │    • Market state + indicators                                │    │   │
│  │      │    • LeWM predicted states                                   │    │   │
│  │      │    • Historical context                                       │    │   │
│  │      │                                                               │    │   │
│  │      │  Process:                                                     │    │   │
│  │      │    1. Initial Analysis ────────────────────────────┐         │    │   │
│  │      │                                                     │         │    │   │
│  │      │    2. Self-Critique ◄──────────────────────────────┘         │    │   │
│  │      │       "What could go wrong?"                                  │    │   │
│  │      │                │                                              │    │   │
│  │      │                ▼                                              │    │   │
│  │      │    3. Refined Analysis                                        │    │   │
│  │      │       (improved with self-feedback)                          │    │   │
│  │      │                                                               │    │   │
│  │      │  Output:                                                      │    │   │
│  │      │    • Trade recommendation (LONG/SHORT/SKIP)                  │    │   │
│  │      │    • Confidence score (calibrated)                           │    │   │
│  │      │    • Risk warnings                                            │    │   │
│  │      │    • Reasoning chain                                          │    │   │
│  │      └──────────────────────────────────────────────────────────────┘    │   │
│  │                                        │                                  │   │
│  │                                        ▼                                  │   │
│  │                          LLM Confidence + Warnings                        │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                      SIMULATION LAYER (Optional)                          │   │
│  │                                                                           │   │
│  │         ┌──────────────────────────────────────────────────┐             │   │
│  │         │              MIROFISH SWARM                       │             │   │
│  │         │                                                   │             │   │
│  │         │  Bull Agent ◄────────▶ Bear Agent                │             │   │
│  │         │      │                     │                      │             │   │
│  │         │      └────────┬───────────┘                      │             │   │
│  │         │               │                                   │             │   │
│  │         │               ▼                                   │             │   │
│  │         │         Debate: Should we trade?                 │             │   │
│  │         │                                                   │             │   │
│  │         │  Whale Agent ──▶ "Watch for liquidation hunt"    │             │   │
│  │         │  Retail Agent ─▶ "FOMO if pump continues"        │             │   │
│  │         │                                                   │             │   │
│  │         │  Consensus: 3/4 agents agree LONG                │             │   │
│  │         └──────────────────────────────────────────────────┘             │   │
│  │                                        │                                  │   │
│  │                                        ▼                                  │   │
│  │                          Swarm Consensus Score                            │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                       DECISION FUSION LAYER                               │   │
│  │                                                                           │   │
│  │   ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │   │                    CONFIDENCE FUSION                             │    │   │
│  │   │                                                                  │    │   │
│  │   │   Maya Indicators:  0.85 (6 bull / 1 bear)                      │    │   │
│  │   │   LeWM Prediction:  0.72 (moderate upside predicted)            │    │   │
│  │   │   SELF Analyst:     0.58 (warns of overbought risk)             │    │   │
│  │   │   MiroFish Swarm:   0.65 (3/4 agents bullish)                   │    │   │
│  │   │                                                                  │    │   │
│  │   │   Weighted Fusion:                                               │    │   │
│  │   │     final = 0.4*maya + 0.25*lewm + 0.25*self + 0.10*miro       │    │   │
│  │   │     final = 0.4*0.85 + 0.25*0.72 + 0.25*0.58 + 0.10*0.65       │    │   │
│  │   │     final = 0.719                                                │    │   │
│  │   │                                                                  │    │   │
│  │   │   Override Rules:                                                │    │   │
│  │   │     • IF SELF warns "reversal" → reduce by 0.15                 │    │   │
│  │   │     • IF LeWM + SELF both < 0.5 → SKIP                          │    │   │
│  │   │     • IF all four > 0.7 → boost to 0.9                          │    │   │
│  │   │                                                                  │    │   │
│  │   └─────────────────────────────────────────────────────────────────┘    │   │
│  │                                        │                                  │   │
│  │                                        ▼                                  │   │
│  │                          Final Decision: TRADE (0.72)                    │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                        EXECUTION LAYER (Maya)                             │   │
│  │                                                                           │   │
│  │   ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │   │                    MAYA PAPER TRADER                             │    │   │
│  │   │                                                                  │    │   │
│  │   │   Decision: LONG BTC with confidence 0.72                       │    │   │
│  │   │                                                                  │    │   │
│  │   │   Position Sizing:                                               │    │   │
│  │   │     • conf > 0.8: 1x position                                   │    │   │
│  │   │     • conf > 0.7: 0.5x position ◄── this one                    │    │   │
│  │   │     • conf > 0.6: 0.25x position                                │    │   │
│  │   │                                                                  │    │   │
│  │   │   Execution:                                                     │    │   │
│  │   │     → Open paper long 0.5x at 87,250                            │    │   │
│  │   │     → Stop loss: 86,500 (-0.86%)                                │    │   │
│  │   │     → Take profit: 88,000 (+0.86%)                              │    │   │
│  │   │                                                                  │    │   │
│  │   └─────────────────────────────────────────────────────────────────┘    │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                         │
│                                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                         FEEDBACK LOOP                                     │   │
│  │                                                                           │   │
│  │   5 minutes later:                                                        │   │
│  │     Result: WIN (+13.5 pips) or LOSS (-15 pips)                         │   │
│  │                                                                           │   │
│  │   Feedback stored in:                                                     │   │
│  │     /opt/ravenx/data/paper/btc5m/decisions_v3.jsonl                     │   │
│  │                                                                           │   │
│  │   Used for:                                                               │   │
│  │     • LeWM retraining (nightly)                                          │   │
│  │     • SELF evolution (nightly)                                            │   │
│  │     • Maya indicator tuning (weekly)                                     │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Flow Specification

### 2.1 Real-Time Inference Flow

```
Time: T=0 (new 5m candle closes)

1. DATA INGESTION (0-50ms)
   Binance WS → OHLCV + orderbook snapshot
   
2. FEATURE ENGINEERING (50-100ms)
   Compute: RSI, MACD, BB, EMA, volume profile
   
3. MAYA INDICATORS (100-150ms)
   Vote aggregation: bullVotes=6, bearVotes=1, conf=0.85
   
4. LEWM PREDICTION (150-300ms)
   market_frame → encoder → z_t → predictor → ẑ_{t+1:t+6}
   Planning cost: ||ẑ_target - ẑ_final||²
   
5. SELF ANALYSIS (300-2000ms) [optional for high-conf trades]
   IF maya_conf < 0.8:
     initial = llm.analyze(market_state)
     critique = llm.self_critique(initial)
     refined = llm.refine(initial, critique)
   
6. FUSION (2000-2050ms)
   Combine all signals → final_decision
   
7. EXECUTION (2050-2100ms)
   IF decision == TRADE:
     maya.execute_paper_trade()

Total latency: < 2.1 seconds (well within 5m window)
```

### 2.2 Training Data Flow

```
                    TRAINING PIPELINE (Nightly 2AM PT)
                    
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  1. COLLECT DECISIONS (2:00 AM)                                 │
│     └─▶ SSH to GCP: ravenx@34.182.110.4                         │
│     └─▶ Download: /opt/ravenx/data/paper/btc5m/decisions_v3.jsonl│
│     └─▶ Filter last 24h: ~288 decisions (5m × 24h)              │
│                                                                  │
│  2. LEWM DATA PREP (2:05 AM)                                    │
│     └─▶ Build market frames from OHLCV                          │
│     └─▶ Create (frame, action, next_frame) tuples              │
│     └─▶ Output: lewm_training_data.npz                          │
│                                                                  │
│  3. LEWM TRAINING (2:10 AM)                                     │
│     └─▶ Load on single M4 Max node                              │
│     └─▶ Train 20 epochs (~45 min)                               │
│     └─▶ Checkpoint: lewm_market_v{date}.mlx                     │
│                                                                  │
│  4. SELF DATA PREP (3:00 AM)                                    │
│     └─▶ For each (decision, resolve) pair:                      │
│         └─▶ Generate initial analysis (Llama 70B)               │
│         └─▶ Generate self-critique (knowing outcome)            │
│         └─▶ Generate refined analysis                           │
│         └─▶ Filter quality > 0.7                                │
│     └─▶ Output: self_training_data.jsonl                        │
│                                                                  │
│  5. SELF FINE-TUNING (4:00 AM)                                  │
│     └─▶ Distribute across 4 nodes (MLX Ring)                    │
│     └─▶ QLoRA fine-tune 3 epochs (~90 min)                     │
│     └─▶ Checkpoint: self_analyst_v{date}.mlx                    │
│                                                                  │
│  6. EVALUATION (5:30 AM)                                        │
│     └─▶ Test on holdout (last 3 days)                           │
│     └─▶ Compare: new vs current models                          │
│     └─▶ Deploy if improvement > 2%                              │
│                                                                  │
│  7. CLEANUP (6:00 AM)                                           │
│     └─▶ Archive training data                                    │
│     └─▶ Prune old checkpoints (keep last 7)                     │
│     └─▶ Log training metrics                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Hardware Allocation

### 3.1 Star Platinum Cluster (184GB Total)

| Node | Role | Memory | GPU | Tasks |
|------|------|--------|-----|-------|
| M4 Max (128GB) | Master | 46GB unified | 40 GPU cores | LeWM inference, SELF inference, Training coordinator |
| M1 Ultra (64GB) | Worker 1 | 46GB unified | 64 GPU cores | Llama 70B layer 0-23 |
| M2 Max (32GB) | Worker 2 | 23GB unified | 38 GPU cores | Llama 70B layer 24-47 |
| M3 Pro (36GB) | Worker 3 | 18GB unified | 18 GPU cores | Llama 70B layer 48-79 |

### 3.2 Memory Budget

```
LeWM-Market (15M params):
  - Model: 60MB (bf16)
  - Inference batch: 100MB
  - Training batch: 2GB
  - Total: 2.2GB

Llama 3.3 70B (4-bit):
  - Model: 37GB
  - KV cache: 8GB (8K context)
  - Inference: 45GB total
  - Distributed: ~11GB per node

MiroFish (when active):
  - 4 agents × 500MB = 2GB
  - Shared context: 500MB
  - Total: 2.5GB

Reserved:
  - System: 10GB
  - Buffers: 5GB

TOTAL: ~65GB active (35% of cluster)
Headroom: 119GB for batch training
```

---

## 4. API Specification

### 4.1 RavenX AI Unified API

```python
# Base URL: http://localhost:52400/v1

# Endpoints:

POST /analyze
"""
Full AI stack analysis for a market state.
Returns all component signals + fused decision.
"""
Request:
{
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "market_state": {
        "ohlcv": [[ts, o, h, l, c, v], ...],
        "orderbook": {"bids": [...], "asks": [...]},
        "indicators": {
            "rsi": 70.81,
            "macd": 0.23,
            "bb_position": 0.85
        }
    },
    "components": ["maya", "lewm", "self", "mirofish"],  # optional
    "timeout_ms": 3000
}

Response:
{
    "decision": "LONG",
    "confidence": 0.72,
    "components": {
        "maya": {"direction": "UP", "confidence": 0.85, "votes": "6/7"},
        "lewm": {"predicted_direction": "UP", "confidence": 0.72, "horizon": 6},
        "self": {"direction": "UP", "confidence": 0.58, "warnings": ["overbought"]},
        "mirofish": {"consensus": "LONG", "confidence": 0.65, "agents": 4}
    },
    "reasoning": "Strong indicator consensus with moderate world model confidence...",
    "execution_params": {
        "position_size": 0.5,
        "stop_loss_pct": 0.86,
        "take_profit_pct": 0.86
    },
    "latency_ms": 1847
}

GET /health
"""
Check all components are operational.
"""
Response:
{
    "status": "healthy",
    "components": {
        "maya": "connected",
        "lewm": "loaded",
        "self": "loaded",
        "mirofish": "ready",
        "cluster": "4/4 nodes online"
    },
    "model_versions": {
        "lewm": "v2026-03-24",
        "self": "v2026-03-24"
    }
}

POST /feedback
"""
Submit trade outcome for learning.
"""
Request:
{
    "trade_id": "uuid",
    "outcome": "WIN",
    "pnl": 13.5,
    "actual_direction": "UP"
}
```

### 4.2 Component APIs

```python
# LeWM-Market API
POST /lewm/predict
{
    "market_frame": [...],  # [4, 60, 64] tensor
    "actions": [0, 1, 0, 0, 0, 0],  # 6-step action sequence
}
→ {"predicted_states": [...], "confidence": 0.72}

# SELF Analyst API
POST /self/analyze
{
    "market_state": {...},
    "enable_refinement": true
}
→ {"analysis": "...", "critique": "...", "refined": "...", "confidence": 0.58}

# MiroFish API
POST /mirofish/simulate
{
    "scenario": "btc_5m_long",
    "agents": ["bull", "bear", "whale", "retail"],
    "max_rounds": 3
}
→ {"consensus": "LONG", "debate_log": [...], "confidence": 0.65}
```

---

## 5. Training Pipeline Design

### 5.1 Nightly Training Script

```bash
#!/bin/bash
# ~/Projects/star-platinum-cluster/scripts/nightly_train.sh

set -e

DATE=$(date +%Y-%m-%d)
LOG_DIR=~/Projects/star-platinum-cluster/logs/training/$DATE
mkdir -p $LOG_DIR

echo "=== RavenX AI Stack Nightly Training ===" | tee $LOG_DIR/train.log
echo "Date: $DATE" | tee -a $LOG_DIR/train.log

# 1. Collect decisions from GCP
echo "[1/6] Collecting decisions from Maya..." | tee -a $LOG_DIR/train.log
scp -i ~/.ssh/ravenx_gcp_qa \
    ravenx@34.182.110.4:/opt/ravenx/data/paper/btc5m/decisions_v3.jsonl \
    $LOG_DIR/decisions.jsonl

# 2. Prepare LeWM training data
echo "[2/6] Preparing LeWM training data..." | tee -a $LOG_DIR/train.log
python ~/Projects/star-platinum-cluster/research/lewm_market_prototype.py \
    --mode prepare \
    --input $LOG_DIR/decisions.jsonl \
    --output $LOG_DIR/lewm_data.npz

# 3. Train LeWM
echo "[3/6] Training LeWM-Market..." | tee -a $LOG_DIR/train.log
python ~/Projects/star-platinum-cluster/research/lewm_market_prototype.py \
    --mode train \
    --data $LOG_DIR/lewm_data.npz \
    --epochs 20 \
    --checkpoint ~/Projects/star-platinum-cluster/checkpoints/lewm_$DATE.mlx

# 4. Prepare SELF training data
echo "[4/6] Preparing SELF training data..." | tee -a $LOG_DIR/train.log
python ~/Projects/star-platinum-cluster/research/self_trade_loop.py \
    --mode prepare \
    --input $LOG_DIR/decisions.jsonl \
    --output $LOG_DIR/self_data.jsonl

# 5. Fine-tune SELF
echo "[5/6] Fine-tuning SELF Analyst..." | tee -a $LOG_DIR/train.log
export MLX_METAL_FAST_SYNCH=1
mlx.launch --hostfile ~/Projects/star-platinum-cluster/configs/star-platinum-ring.json \
    -n 4 -- python ~/Projects/star-platinum-cluster/research/self_trade_loop.py \
    --mode train \
    --data $LOG_DIR/self_data.jsonl \
    --epochs 3 \
    --lora-rank 16 \
    --checkpoint ~/Projects/star-platinum-cluster/checkpoints/self_$DATE.mlx

# 6. Evaluate and deploy
echo "[6/6] Evaluating and deploying..." | tee -a $LOG_DIR/train.log
python ~/Projects/star-platinum-cluster/research/eval_stack.py \
    --lewm ~/Projects/star-platinum-cluster/checkpoints/lewm_$DATE.mlx \
    --self ~/Projects/star-platinum-cluster/checkpoints/self_$DATE.mlx \
    --holdout $LOG_DIR/decisions.jsonl \
    --deploy-if-better

echo "=== Training Complete ===" | tee -a $LOG_DIR/train.log
```

### 5.2 Crontab Entry

```bash
# Nightly training at 2 AM PT
0 2 * * * ~/Projects/star-platinum-cluster/scripts/nightly_train.sh >> ~/Projects/star-platinum-cluster/logs/cron.log 2>&1
```

---

## 6. Timeline

### Week 1: Foundation

| Day | Task | Owner | Deliverable |
|-----|------|-------|-------------|
| Mon | LeWM prototype complete | AI | `lewm_market_prototype.py` |
| Tue | SELF prototype complete | AI | `self_trade_loop.py` |
| Wed | Market frame builder | AI | `market_frame_builder.py` |
| Thu | Data pipeline integration | AI | Data flows working |
| Fri | Single-node training test | AI | LeWM + SELF trained |

### Week 2: Integration

| Day | Task | Owner | Deliverable |
|-----|------|-------|-------------|
| Mon | Maya integration hook | AI | `lewm_maya_integration.py` |
| Tue | API server implementation | AI | Unified API running |
| Wed | Distributed training test | AI | 4-node training working |
| Thu | A/B testing framework | AI | Compare Maya vs Maya+AI |
| Fri | Initial results analysis | AI | Performance report |

### Week 3-4: Optimization

| Task | Effort |
|------|--------|
| Hyperparameter tuning | 3 days |
| Latency optimization | 2 days |
| MiroFish integration | 3 days |
| Production hardening | 2 days |

### Month 2+: Continuous Learning

- Daily automated retraining
- Weekly performance reviews
- Monthly architecture iterations
- Gradual real-money deployment

---

## 7. Risk Management

### 7.1 Technical Risks

| Risk | Mitigation |
|------|------------|
| Model collapse | Quality gates on training data |
| Latency spike | Timeout fallback to Maya-only |
| Memory OOM | Aggressive batching, quantization |
| Training divergence | Rollback to previous checkpoint |

### 7.2 Trading Risks

| Risk | Mitigation |
|------|------------|
| Overconfidence | SELF critique reduces false positives |
| Regime change | Weekly full retrain on recent data |
| Black swan | LeWM "surprise detection" triggers SKIP |
| Correlation breakdown | MiroFish simulates edge cases |

### 7.3 Monitoring

```python
# Key metrics to track
metrics = {
    # Model quality
    "lewm_prediction_mse": "<0.1",
    "self_refinement_rate": ">70%",
    "confidence_calibration": "±10%",
    
    # Trading performance
    "win_rate": ">60%",
    "profit_factor": ">1.5",
    "max_drawdown": "<-10%",
    
    # System health
    "inference_latency_p99": "<2000ms",
    "training_success_rate": ">95%",
    "cluster_utilization": "40-80%",
}
```

---

## 8. Files Structure

```
~/Projects/star-platinum-cluster/
├── research/
│   ├── LEWM-MARKET-DESIGN.md          # LeWM adaptation design
│   ├── SELF-TRADING-DESIGN.md         # SELF adaptation design
│   ├── RAVENX-AI-STACK.md             # This document
│   ├── lewm_market_prototype.py       # LeWM MLX implementation
│   ├── self_trade_loop.py             # SELF pipeline
│   ├── market_frame_builder.py        # Data preprocessing
│   └── eval_stack.py                  # Evaluation scripts
│
├── configs/
│   ├── star-platinum-ring.json        # MLX hostfile
│   ├── lewm_config.yaml               # LeWM hyperparameters
│   └── self_config.yaml               # SELF hyperparameters
│
├── scripts/
│   ├── nightly_train.sh               # Training automation
│   ├── deploy_models.sh               # Model deployment
│   └── rollback.sh                    # Emergency rollback
│
├── checkpoints/
│   ├── lewm_YYYY-MM-DD.mlx           # LeWM checkpoints
│   └── self_YYYY-MM-DD.mlx           # SELF LoRA checkpoints
│
├── logs/
│   ├── training/                      # Training logs
│   ├── inference/                     # Inference logs
│   └── cron.log                       # Automation logs
│
└── docs/
    ├── ROADMAP.md                     # Project roadmap
    └── API.md                         # API documentation
```

---

## 9. Success Criteria

### Phase 1 (Week 2): Proof of Concept
- [ ] LeWM predicts market direction with >55% accuracy
- [ ] SELF improves prediction quality by >5% after 1 iteration
- [ ] End-to-end pipeline runs without manual intervention

### Phase 2 (Week 4): Integration
- [ ] Maya+AI beats Maya-only by >5% win rate
- [ ] Inference latency <2 seconds at P99
- [ ] Nightly training runs reliably

### Phase 3 (Month 2): Production
- [ ] Win rate >60% sustained over 30 days
- [ ] Profit factor >1.5
- [ ] Zero critical failures in training pipeline
- [ ] Ready for limited real-money deployment

---

*RavenX AI — The market mind that never sleeps.* 🖤
