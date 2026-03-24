# LeWM for Market World Modeling

## Executive Summary

LeWorldModel (LeWM) is a Joint-Embedding Predictive Architecture (JEPA) that learns world models from raw observations. This document adapts LeWM for financial time series prediction, enabling RavenX to build a **market world model** that predicts future market states from current observations and trading actions.

**Key Insight from Paper:** LeWM is a **15M parameter model** that trains on a **single GPU in hours** — perfect for our Star Platinum cluster with 184GB distributed memory.

---

## 1. Paper Core Concepts

### 1.1 What LeWM Does

```
Encoder: z_t = enc(o_t)         # Encode observation to latent
Predictor: ẑ_{t+1} = pred(z_t, a_t)   # Predict next latent from current + action
Loss: ||ẑ_{t+1} - z_{t+1}||² + λ·SIGReg(Z)
```

**Two-term objective:**
1. **Prediction Loss**: MSE between predicted and actual next embedding
2. **SIGReg Regularizer**: Prevents collapse by enforcing Gaussian-distributed latents

**No stop-gradient, no EMA, no pretrained encoders — pure end-to-end learning.**

### 1.2 Why LeWM for Markets

| LeWM Property | Market Application |
|--------------|-------------------|
| 15M parameters | Fits on single Apple Silicon node (even 8GB iPad) |
| Hours to train | Daily model updates feasible |
| Task-agnostic | Works for any market (BTC, ETH, stocks) |
| Latent planning | Simulate "what if" scenarios before trading |
| No reconstruction loss | Focuses on dynamics, not pixel-perfect prediction |

---

## 2. Market Adaptation Architecture

### 2.1 Observation Space: Market "Frames"

Instead of video frames, we treat market data as 2D images:

```
┌─────────────────────────────────────────────────┐
│           MARKET FRAME (60x64 tensor)           │
├─────────────────────────────────────────────────┤
│ Row 0-11:  OHLCV candles (12 x 5 features)      │
│ Row 12-23: Technical indicators (12 x 5)        │
│ Row 24-35: Order book imbalance (12 levels)     │
│ Row 36-47: Volume profile (12 price levels)     │
│ Row 48-59: Momentum/velocity features           │
├─────────────────────────────────────────────────┤
│ Channels: [price, volume, momentum, orderflow]  │
└─────────────────────────────────────────────────┘
```

**Frame dimensions:** `[4, 60, 64]` (4 channels × 60 rows × 64 time steps)

#### 2.1.1 Channel Breakdown

| Channel | Contents | Normalization |
|---------|----------|---------------|
| Price | OHLC normalized to % change | [-5, +5] clipped |
| Volume | Log volume relative to 24h avg | [-3, +3] |
| Momentum | RSI, MACD, BB position | [0, 1] |
| Orderflow | Bid/ask imbalance, CVD | [-1, +1] |

### 2.2 Action Space: Trading Signals

```python
ACTION_SPACE = {
    0: "HOLD",
    1: "BUY_SMALL",   # 0.25x position
    2: "BUY_MEDIUM",  # 0.5x position
    3: "BUY_LARGE",   # 1x position
    4: "SELL_SMALL",  # -0.25x position
    5: "SELL_MEDIUM", # -0.5x position
    6: "SELL_LARGE",  # -1x position
}

# Action embedding: [7] one-hot → [64] learned embedding
action_embed = action_encoder(action_id)  # MLP: 7 → 64
```

### 2.3 Model Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LEWM-MARKET                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Market Frame [4, 60, 64]                              │
│       │                                                 │
│       ▼                                                 │
│  ┌──────────────────────┐                              │
│  │   Market Encoder     │  ViT-Tiny adapted for 2D    │
│  │   (5M parameters)    │  Patch size: 4x4            │
│  │                      │  Layers: 6                   │
│  │   Conv2D → ViT →     │  Heads: 6                    │
│  │   [CLS] → Projection │  Hidden: 192                 │
│  └──────────────────────┘                              │
│       │                                                 │
│       ▼                                                 │
│   z_t [256]  ← Latent embedding                        │
│       │                                                 │
│       ├──────────────────────┐                         │
│       │                      │                         │
│       ▼                      ▼                         │
│  ┌────────────┐    ┌────────────────────┐             │
│  │  SIGReg    │    │    Predictor       │             │
│  │ Gaussian   │    │  (10M parameters)   │             │
│  │ regularize │    │                     │             │
│  └────────────┘    │  Transformer        │             │
│                    │  z_t + a_t →        │             │
│                    │  → ẑ_{t+1}          │             │
│                    │                     │             │
│                    │  Uses AdaLN for     │             │
│                    │  action conditioning │             │
│                    └────────────────────┘             │
│                           │                            │
│                           ▼                            │
│                    ẑ_{t+1} [256]                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Training Pipeline

### 3.1 Dataset Construction

Source: Maya paper trader decisions at `/opt/ravenx/data/paper/btc5m/decisions_v3.jsonl`

```python
# Extract training data from Maya decisions
def build_training_data(decisions_path):
    trajectories = []
    current_traj = []
    
    for line in open(decisions_path):
        record = json.loads(line)
        
        if record['mode'] == 'skip':
            continue
            
        if record['mode'] in ['oracle', 'baseline']:
            # Trading signal
            frame = build_market_frame(
                ts=record['windowStartMs'],
                indicators={
                    'rsi': record['rsi'],
                    'macd': record['macd'],
                    'vol': record['vol'],
                    'confidence': record['confidence']
                }
            )
            action = direction_to_action(record['direction'], record['confidence'])
            current_traj.append((frame, action))
            
        elif record['mode'] == 'resolve':
            # Outcome
            if len(current_traj) > 0:
                current_traj[-1] = (*current_traj[-1], record['win'], record['pnl'])
                
        # New trajectory every 12 candles (1 hour)
        if len(current_traj) >= 12:
            trajectories.append(current_traj)
            current_traj = []
            
    return trajectories
```

### 3.2 Training Configuration

```python
config = {
    # Model
    "encoder": "ViT-Tiny-Market",
    "encoder_dim": 192,
    "latent_dim": 256,
    "predictor_layers": 6,
    "predictor_heads": 8,
    
    # Training
    "batch_size": 64,
    "trajectory_length": 12,  # 1 hour of 5m candles
    "learning_rate": 1e-4,
    "epochs": 100,
    "lambda_sigreg": 0.1,  # Only tunable hyperparameter
    
    # SIGReg
    "num_projections": 1024,
    
    # Hardware (Star Platinum cluster)
    "device": "mps",  # Apple Silicon Metal
    "mixed_precision": True,
}
```

### 3.3 Training Loop (MLX)

```python
import mlx.core as mx
import mlx.nn as nn

def train_step(model, batch, optimizer):
    """Single training step for LeWM-Market"""
    
    frames, actions, next_frames = batch
    
    def loss_fn(model):
        # Encode current and next frames
        z_t = model.encoder(frames)
        z_tp1 = model.encoder(next_frames)
        
        # Predict next latent
        z_hat_tp1 = model.predictor(z_t, actions)
        
        # Prediction loss (MSE)
        pred_loss = mx.mean((z_hat_tp1 - z_tp1) ** 2)
        
        # SIGReg loss (Gaussian regularization)
        sigreg_loss = compute_sigreg(z_t, num_projections=1024)
        
        return pred_loss + 0.1 * sigreg_loss, (pred_loss, sigreg_loss)
    
    (loss, (pred_loss, sigreg_loss)), grads = mx.value_and_grad(
        loss_fn, has_aux=True
    )(model)
    
    optimizer.update(model, grads)
    
    return {
        'loss': loss,
        'pred_loss': pred_loss,
        'sigreg_loss': sigreg_loss
    }
```

---

## 4. Inference: Latent Planning for Trading

### 4.1 Planning Pipeline

```
┌─────────────────────────────────────────────────────────┐
│               LATENT PLANNING FOR TRADE                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. ENCODE CURRENT STATE                               │
│     z_now = encoder(current_market_frame)              │
│                                                         │
│  2. DEFINE TARGET STATE                                 │
│     z_target = encoder(desired_profit_state)           │
│     OR: z_target = learned_profit_embedding            │
│                                                         │
│  3. OPTIMIZE ACTION SEQUENCE                            │
│     For each candidate action sequence [a_1, ..., a_H]: │
│       z_1 = predictor(z_now, a_1)                      │
│       z_2 = predictor(z_1, a_2)                        │
│       ...                                               │
│       z_H = predictor(z_{H-1}, a_H)                    │
│                                                         │
│     cost = ||z_H - z_target||²                         │
│                                                         │
│  4. USE CROSS-ENTROPY METHOD (CEM)                     │
│     - Sample N action sequences                         │
│     - Evaluate cost for each                            │
│     - Keep top K sequences                              │
│     - Update sampling distribution                      │
│     - Repeat until convergence                          │
│                                                         │
│  5. EXECUTE BEST ACTION                                 │
│     Execute a_1 from best sequence                      │
│     Replan at next timestep (MPC style)                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Planning Code

```python
def plan_trade(model, current_frame, horizon=6, num_samples=100, num_elite=10):
    """Use CEM to find optimal action sequence"""
    
    # Encode current state
    z_now = model.encoder(current_frame)
    
    # Target: "profitable state" learned embedding
    z_target = model.profit_embedding  # Learned from winning trades
    
    # Initialize action distribution
    action_mean = mx.zeros((horizon, 7))  # Uniform initially
    action_std = mx.ones((horizon, 7))
    
    for _ in range(10):  # CEM iterations
        # Sample action sequences
        sequences = sample_actions(action_mean, action_std, num_samples)
        
        # Evaluate each sequence
        costs = []
        for seq in sequences:
            z = z_now
            for action in seq:
                z = model.predictor(z, action)
            cost = mx.sum((z - z_target) ** 2)
            costs.append(cost)
        
        # Keep elite sequences
        elite_idx = mx.argsort(mx.array(costs))[:num_elite]
        elite_seqs = sequences[elite_idx]
        
        # Update distribution
        action_mean = mx.mean(elite_seqs, axis=0)
        action_std = mx.std(elite_seqs, axis=0) + 0.1
    
    # Return best action
    best_seq = elite_seqs[0]
    return best_seq[0]  # First action only (MPC)
```

---

## 5. Integration with Maya Paper Trader

### 5.1 Enhanced Decision Pipeline

```
┌────────────────────────────────────────────────────────────┐
│                   MAYA + LEWM-MARKET                        │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Market Data (5m candles)                                  │
│        │                                                    │
│        ├─────────────────────┐                             │
│        │                     │                             │
│        ▼                     ▼                             │
│  ┌──────────────┐   ┌────────────────────┐                │
│  │   EXISTING   │   │    LEWM-MARKET     │                │
│  │  INDICATORS  │   │    WORLD MODEL     │                │
│  │              │   │                    │                │
│  │  RSI, MACD   │   │  Encode → Plan →   │                │
│  │  BB, EMA     │   │  Predict future    │                │
│  │  Votes       │   │  market states     │                │
│  └──────────────┘   └────────────────────┘                │
│        │                     │                             │
│        │                     │                             │
│        ▼                     ▼                             │
│  ┌─────────────────────────────────────────┐              │
│  │          DECISION FUSION                 │              │
│  │                                          │              │
│  │  If LeWM predicts STRONG profit state:  │              │
│  │    → Boost confidence by 0.1            │              │
│  │  If LeWM predicts LOSS state:           │              │
│  │    → Reduce confidence by 0.15          │              │
│  │  If disagreement with indicators:       │              │
│  │    → SKIP (wait for alignment)          │              │
│  └─────────────────────────────────────────┘              │
│                     │                                      │
│                     ▼                                      │
│              EXECUTE OR SKIP                               │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### 5.2 Implementation Hook

```python
# In Maya's decision logic
async def enhanced_decision(window_data):
    # Existing indicator voting
    indicator_result = compute_indicator_votes(window_data)
    
    # NEW: LeWM prediction
    market_frame = build_market_frame(window_data)
    planned_action = lewm_model.plan_trade(market_frame)
    lewm_confidence = lewm_model.predict_confidence(planned_action)
    
    # Fusion
    if indicator_result['confidence'] > 0.75 and lewm_confidence > 0.7:
        # Strong agreement: boost
        final_confidence = min(0.95, indicator_result['confidence'] + 0.1)
        return {'action': 'trade', 'confidence': final_confidence}
    
    elif indicator_result['confidence'] > 0.7 and lewm_confidence < 0.3:
        # Disagreement: skip
        return {'action': 'skip', 'reason': 'lewm_disagreement'}
    
    else:
        # Defer to existing logic
        return indicator_result
```

---

## 6. Training Schedule

### Phase 1: Initial Training (Week 1)

| Day | Task | Dataset | Hardware |
|-----|------|---------|----------|
| 1 | Data preprocessing | 30 days Maya decisions | Single node |
| 2-3 | Train LeWM-Market v1 | 10K trajectories | M4 Max (128GB) |
| 4 | Evaluate on holdout | Last 7 days | Single node |
| 5 | Hyperparameter sweep | λ ∈ {0.01, 0.1, 1.0} | 4-node cluster |

### Phase 2: Integration (Week 2)

| Day | Task |
|-----|------|
| 1-2 | Implement Maya integration hook |
| 3 | A/B test: Maya vs Maya+LeWM |
| 4-5 | Analyze results, iterate |

### Phase 3: Continuous Learning (Ongoing)

- Nightly retraining on last 24h of data
- Weekly full retrain on last 30 days
- Monthly architecture review

---

## 7. Hardware Requirements

### Single Node (Development)

- **Model:** 15M parameters = ~60MB in bf16
- **Memory:** 2GB for training batch
- **Training time:** ~2 hours for 100 epochs

### Cluster (Production)

- **Star Platinum:** 4 nodes × 46GB unified memory
- **Distributed training:** Data parallel across nodes
- **Inference:** Any single node can run inference

---

## 8. Metrics & Evaluation

### 8.1 World Model Quality

| Metric | Target | Measurement |
|--------|--------|-------------|
| Prediction MSE | < 0.1 | ||ẑ - z||² on holdout |
| Planning accuracy | > 65% | Planned action matches profitable direction |
| Latent linearity | > 0.8 | PCA explains 80% of variance |

### 8.2 Trading Performance

| Metric | Current (Maya) | Target (Maya+LeWM) |
|--------|----------------|-------------------|
| Win rate | ~55% | > 60% |
| Profit factor | 1.2 | > 1.5 |
| Drawdown | -15% | < -10% |

---

## 9. Files to Create

```
~/Projects/star-platinum-cluster/research/
├── LEWM-MARKET-DESIGN.md          # This document
├── lewm_market_prototype.py       # MLX implementation
├── market_frame_builder.py        # Data preprocessing
└── lewm_maya_integration.py       # Maya hook
```

---

## References

- LeWorldModel Paper: https://arxiv.org/html/2603.19312v1
- SIGReg: Sketched-Isotropic-Gaussian Regularizer
- JEPA: Joint-Embedding Predictive Architecture (LeCun 2022)
- CEM: Cross-Entropy Method for planning

---

*RavenX AI — Building the market mind.* 🖤
