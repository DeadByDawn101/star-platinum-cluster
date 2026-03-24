# SELF Framework for Trading Analysis Evolution

## Executive Summary

SELF (Self-Evolution with Language Feedback) enables LLMs to autonomously improve through self-feedback and self-refinement cycles. This document adapts SELF for **trading analysis evolution** — using Llama 3.3 70B on our Star Platinum cluster to continuously improve its market predictions using Maya's paper trading outcomes as automatic ground truth.

**Key Insight:** SELF eliminates the need for human labels. In trading, **win/loss is automatic feedback** — the market tells us if we were right.

---

## 1. Paper Core Concepts

### 1.1 SELF Framework

```
┌─────────────────────────────────────────────────────────────┐
│                    SELF LEARNING LOOP                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. META-SKILL LEARNING (bootstrap)                         │
│     └─ Teach model: self-feedback + self-refinement         │
│                                                              │
│  2. SELF-EVOLUTION ITERATIONS (main loop)                   │
│     For each iteration t:                                    │
│       a) Generate initial response r to prompt p            │
│       b) Self-feedback: model critiques own response        │
│       c) Self-refinement: model improves response to r̂      │
│       d) Filter: keep only high-quality refinements         │
│       e) Fine-tune model on (p, r̂) pairs                   │
│                                                              │
│  3. INFERENCE                                                │
│     └─ Model can self-refine at inference time             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Why SELF for Trading

| SELF Property | Trading Application |
|---------------|---------------------|
| No human labels needed | Win/loss from market is ground truth |
| Language feedback | Rich analysis of why trades won/lost |
| Iterative improvement | Each trading day improves the model |
| Self-refinement at inference | Think twice before trading |

---

## 2. Trading Adaptation Architecture

### 2.1 Training Data: Maya Paper Trader

Maya decisions at `/opt/ravenx/data/paper/btc5m/decisions_v3.jsonl`:

```json
// Trading signal
{"ts":"2026-03-20T22:04:56","mode":"oracle","direction":"UP","confidence":0.85,
 "bullVotes":6,"bearVotes":1,"fired":["mom_short_bull","ema_bull","rsi_bull"],
 "rsi":70.81,"macd":0.23,"vol":0.000046,"action":"trade"}

// Outcome (5 minutes later)
{"ts":"2026-03-20T22:05:02","mode":"resolve","predicted":"UP","actual":"DOWN",
 "win":false,"pnl":-15}
```

**This is perfect for SELF:**
- Prompt p = market state + indicators
- Initial response r = trade decision + analysis
- Ground truth = win/loss (automatic label!)

### 2.2 Meta-Skill Training Corpus

Create ~500 examples with this structure:

```
[PROMPT]
Market Analysis Request:
- Timestamp: 2026-03-20 22:04 UTC
- BTC/USD 5-minute window
- Indicators: RSI=70.81, MACD=0.23, Vol=0.000046
- Bull signals: mom_short_bull, ema_bull, rsi_bull, macd_bull
- Bear signals: bb_compress
- Confidence: 0.85

What is your trade analysis and recommendation?

[INITIAL_RESPONSE]
Based on the indicators, I recommend a LONG position:
- RSI at 70.81 shows strong momentum
- MACD positive at 0.23 confirms uptrend
- 6 bull votes vs 1 bear vote
Recommendation: BUY with high confidence.

[SELF_FEEDBACK]
Analysis of my response:
FLAWS IDENTIFIED:
1. RSI at 70.81 is near overbought territory (>70), not just "strong momentum"
2. I didn't consider that bb_compress suggests consolidation, often preceding reversal
3. High bull consensus (6:1) could indicate crowded trade risk
4. Volume at 0.000046 is below average - low conviction move

SUGGESTIONS:
- Acknowledge overbought risk from RSI
- Reduce confidence due to potential reversal signals
- Consider shorter hold time given bb_compress

[REFINED_RESPONSE]
Revised analysis with identified weaknesses:
- RSI at 70.81 is approaching overbought, suggesting limited upside
- Strong bull consensus (6:1) but bb_compress warns of potential reversal
- Below-average volume indicates weak conviction

Recommendation: CAUTIOUS LONG with REDUCED confidence (0.65 → 0.55)
Risk: Set tight stop-loss due to overbought RSI
Alternative: Wait for pullback before entry

[OUTCOME]
Result: LOSS (market went DOWN)
The self-feedback correctly identified the overbought risk and reversal potential.
The refined response's caution was validated.
```

### 2.3 Self-Evolution Prompts

**Generation Prompt:**
```
You are a crypto trading analyst. Analyze this market state and provide a trade recommendation:

Market State:
{timestamp}
{indicators_json}
{technical_signals}

Provide your analysis and recommendation in this format:
1. Market Assessment
2. Key Signals
3. Risk Factors
4. Trade Recommendation (LONG/SHORT/SKIP)
5. Confidence (0-1)
```

**Self-Feedback Prompt:**
```
Review your trade analysis and identify potential flaws:

ORIGINAL ANALYSIS:
{initial_response}

ACTUAL OUTCOME:
{win_loss} with PnL of {pnl}

Based on this outcome, critique your original analysis:
1. What signals did you misinterpret?
2. What risks did you overlook?
3. How would you improve the analysis?

Format:
FLAWS:
- ...
SUGGESTIONS:
- ...
```

**Self-Refinement Prompt:**
```
Based on your self-feedback, provide an improved analysis:

ORIGINAL ANALYSIS:
{initial_response}

SELF-CRITIQUE:
{self_feedback}

Now provide a refined analysis that addresses the identified flaws:
```

---

## 3. Implementation Architecture

### 3.1 System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                  SELF-TRADING EVOLUTION SYSTEM                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐    ┌─────────────────────────────────────────┐  │
│  │   Maya      │───▶│  Decision Logger                        │  │
│  │   Paper     │    │  /opt/ravenx/data/paper/btc5m/          │  │
│  │   Trader    │    │  decisions_v3.jsonl                     │  │
│  └─────────────┘    └─────────────────────────────────────────┘  │
│                                      │                            │
│                                      ▼                            │
│              ┌─────────────────────────────────────────┐         │
│              │        SELF Training Pipeline           │         │
│              │                                         │         │
│              │  1. Parse decision + resolve pairs      │         │
│              │  2. Build prompts from market state     │         │
│              │  3. Generate initial analysis           │         │
│              │  4. Add outcome (automatic feedback)    │         │
│              │  5. Generate self-critique              │         │
│              │  6. Generate refined analysis           │         │
│              │  7. Filter high-quality refinements     │         │
│              │  8. Create training dataset             │         │
│              └─────────────────────────────────────────┘         │
│                                      │                            │
│                                      ▼                            │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                 STAR PLATINUM CLUSTER                        │ │
│  │                                                              │ │
│  │   ┌────────────────────────────────────────────────────┐    │ │
│  │   │     Llama 3.3 70B (4-bit quantized, 37GB)          │    │ │
│  │   │     mlx-community/Llama-3.3-70B-Instruct-4bit      │    │ │
│  │   │                                                    │    │ │
│  │   │     OpenAI-compatible API: localhost:52415         │    │ │
│  │   └────────────────────────────────────────────────────┘    │ │
│  │                                                              │ │
│  │   Training: QLoRA fine-tuning on self-evolution data        │ │
│  │   Inference: Distributed across 4 nodes                     │ │
│  │                                                              │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                      │                            │
│                                      ▼                            │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  EVOLVED TRADING ANALYST                     │ │
│  │                                                              │ │
│  │  • Better pattern recognition from past mistakes             │ │
│  │  • Self-doubt on overconfident signals                       │ │
│  │  • Learned to identify reversal patterns                     │ │
│  │  • Can self-refine at inference time                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Training Pipeline Code Structure

```python
class SELFTradingPipeline:
    """SELF-Evolution for Trading Analysis"""
    
    def __init__(self, model_endpoint="http://localhost:52415"):
        self.model = OpenAICompatibleClient(model_endpoint)
        self.model_name = "mlx-community/Llama-3.3-70B-Instruct-4bit"
        
    async def load_decisions(self, decisions_path):
        """Load Maya decision-resolve pairs"""
        decisions = []
        current = None
        
        async for line in aiofiles.open(decisions_path):
            record = json.loads(line)
            
            if record['mode'] in ['oracle', 'baseline']:
                current = record
            elif record['mode'] == 'resolve' and current:
                decisions.append({
                    'signal': current,
                    'outcome': record
                })
                current = None
                
        return decisions
    
    async def generate_initial_analysis(self, market_state):
        """Step 1: Generate initial trade analysis"""
        prompt = self.build_analysis_prompt(market_state)
        response = await self.model.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content
    
    async def generate_self_feedback(self, analysis, outcome):
        """Step 2: Model critiques its own analysis given outcome"""
        prompt = self.build_feedback_prompt(analysis, outcome)
        response = await self.model.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content
    
    async def generate_refined_analysis(self, analysis, feedback):
        """Step 3: Model refines analysis based on feedback"""
        prompt = self.build_refinement_prompt(analysis, feedback)
        response = await self.model.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content
    
    async def filter_quality(self, original, refined, outcome):
        """Step 4: Keep only quality improvements"""
        # Refinement quality check:
        # - Does it acknowledge the mistake?
        # - Does it provide actionable improvement?
        # - Is it consistent with the outcome?
        
        # Simple heuristic: refined must mention the actual outcome
        actual_direction = outcome['actual']
        mentions_actual = actual_direction.lower() in refined.lower()
        
        # Length check: refined should be substantive
        is_substantive = len(refined) > len(original) * 0.8
        
        return mentions_actual and is_substantive
    
    async def run_evolution_iteration(self, decisions_path, output_path):
        """Complete one SELF evolution iteration"""
        decisions = await self.load_decisions(decisions_path)
        training_data = []
        
        for decision in decisions:
            # Generate initial analysis
            analysis = await self.generate_initial_analysis(decision['signal'])
            
            # Generate self-feedback (knowing outcome)
            feedback = await self.generate_self_feedback(
                analysis, decision['outcome']
            )
            
            # Generate refined analysis
            refined = await self.generate_refined_analysis(analysis, feedback)
            
            # Filter quality
            if await self.filter_quality(analysis, refined, decision['outcome']):
                training_data.append({
                    'prompt': self.build_analysis_prompt(decision['signal']),
                    'response': refined,  # Train on refined output
                    'metadata': {
                        'original': analysis,
                        'feedback': feedback,
                        'outcome': decision['outcome']
                    }
                })
        
        # Save training data
        with open(output_path, 'w') as f:
            for item in training_data:
                f.write(json.dumps(item) + '\n')
        
        return len(training_data)
```

---

## 4. Fine-Tuning Strategy

### 4.1 QLoRA for Efficient Training

```python
# MLX LoRA configuration
lora_config = {
    "rank": 16,
    "alpha": 32,
    "dropout": 0.05,
    "target_modules": ["q_proj", "v_proj", "o_proj"],
    "learning_rate": 2e-5,
    "batch_size": 4,
    "num_epochs": 3,
    "gradient_checkpointing": True,
}
```

### 4.2 Training Schedule

```
┌─────────────────────────────────────────────────────────────┐
│               SELF-EVOLUTION TRAINING SCHEDULE               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  DAILY (2 AM PT):                                           │
│    1. Collect last 24h of Maya decisions                    │
│    2. Run SELF evolution iteration                          │
│    3. Generate ~200-500 training examples                   │
│    4. Fine-tune with LoRA (~30 min on cluster)             │
│    5. Evaluate on holdout set                               │
│                                                              │
│  WEEKLY (Sunday 3 AM PT):                                   │
│    1. Merge LoRA weights into base model                    │
│    2. Run comprehensive evaluation                          │
│    3. Compare to previous week's model                      │
│    4. Deploy if improvement, else rollback                  │
│                                                              │
│  MONTHLY:                                                    │
│    1. Full model refresh from scratch                        │
│    2. Use last 90 days of trading data                      │
│    3. Run 3 full SELF evolution iterations                  │
│    4. Extensive backtesting before deployment               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Distributed Training on Star Platinum

```bash
# Using MLX distributed training
export MLX_METAL_FAST_SYNCH=1

# 4-node training for Llama 70B
mlx.launch --hostfile configs/star-platinum-ring.json -n 4 \
  python train_self_trading.py \
    --model mlx-community/Llama-3.3-70B-Instruct-4bit \
    --data output/self_evolution_data.jsonl \
    --lora-rank 16 \
    --epochs 3 \
    --batch-size 4
```

---

## 5. Inference with Self-Refinement

### 5.1 Two-Pass Inference

At inference time, the model can self-refine before making final decision:

```python
async def inference_with_refinement(market_state):
    """Two-pass inference with self-refinement"""
    
    # Pass 1: Initial analysis
    initial = await model.analyze(market_state)
    
    # Pass 2: Self-critique and refine
    critique = await model.self_feedback(initial, market_state)
    refined = await model.refine(initial, critique)
    
    # Extract final recommendation
    recommendation = extract_recommendation(refined)
    
    return {
        'initial': initial,
        'critique': critique,
        'final': refined,
        'recommendation': recommendation
    }
```

### 5.2 Confidence Adjustment

```python
def adjust_confidence(initial_conf, self_critique):
    """Adjust confidence based on self-critique severity"""
    
    # Count warning signals in critique
    warning_phrases = [
        'overbought', 'oversold', 'divergence', 'reversal',
        'low volume', 'crowded trade', 'uncertain', 'risky'
    ]
    
    warnings = sum(1 for phrase in warning_phrases 
                   if phrase in self_critique.lower())
    
    # Reduce confidence for each warning
    adjusted = initial_conf - (warnings * 0.05)
    
    return max(0.3, min(0.95, adjusted))
```

---

## 6. Integration with Maya

### 6.1 Enhanced Decision Flow

```
┌─────────────────────────────────────────────────────────────┐
│              MAYA + SELF-EVOLVED ANALYST                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Market Data → Maya Indicators → Base Decision              │
│                     │                                        │
│                     ▼                                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │            SELF-EVOLVED LLM ANALYST                    │  │
│  │                                                        │  │
│  │  1. Analyze market state with Llama 70B               │  │
│  │  2. Generate initial recommendation                    │  │
│  │  3. Self-critique (identify weaknesses)               │  │
│  │  4. Self-refine (improve recommendation)              │  │
│  │  5. Return adjusted confidence + reasoning            │  │
│  └───────────────────────────────────────────────────────┘  │
│                     │                                        │
│                     ▼                                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              DECISION FUSION                           │  │
│  │                                                        │  │
│  │  Maya Confidence: 0.85                                │  │
│  │  LLM Confidence: 0.62 (reduced via self-critique)     │  │
│  │                                                        │  │
│  │  IF LLM warns of reversal risk → SKIP                 │  │
│  │  IF LLM agrees with high confidence → BOOST           │  │
│  │  ELSE → Use weighted average                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                     │                                        │
│                     ▼                                        │
│              FINAL: TRADE or SKIP                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Implementation Hook

```python
class SelfEvolvedAnalyst:
    def __init__(self, model_endpoint="http://localhost:52415"):
        self.client = OpenAI(base_url=model_endpoint)
        self.model = "mlx-community/Llama-3.3-70B-Instruct-4bit"
    
    async def analyze_trade(self, decision_data):
        """Full SELF-style analysis for a trade"""
        
        # Build context
        context = self.build_market_context(decision_data)
        
        # Initial analysis
        initial = await self.generate_analysis(context)
        
        # Self-critique
        critique = await self.self_critique(initial, context)
        
        # Refined analysis
        refined = await self.refine(initial, critique)
        
        # Extract recommendation
        recommendation = self.parse_recommendation(refined)
        
        return {
            'recommendation': recommendation['direction'],
            'confidence': recommendation['confidence'],
            'warnings': self.extract_warnings(critique),
            'reasoning': refined
        }
    
    def should_skip_trade(self, maya_decision, llm_analysis):
        """Determine if LLM analysis suggests skipping"""
        
        # High severity warnings
        severe_warnings = ['reversal', 'overbought', 'divergence', 'trap']
        has_severe = any(w in ' '.join(llm_analysis['warnings']).lower() 
                        for w in severe_warnings)
        
        # Confidence disagreement
        conf_diff = abs(maya_decision['confidence'] - llm_analysis['confidence'])
        
        # Skip if severe warning or large disagreement
        return has_severe or conf_diff > 0.3
```

---

## 7. Evaluation Metrics

### 7.1 Self-Evolution Quality

| Metric | Description | Target |
|--------|-------------|--------|
| Refinement Rate | % of analyses successfully refined | > 70% |
| Critique Quality | Self-critique mentions actual outcome factors | > 80% |
| Learning Signal | Accuracy improvement per iteration | > 2% |

### 7.2 Trading Performance

| Metric | Before SELF | After SELF (Target) |
|--------|-------------|---------------------|
| Win Rate | 55% | > 62% |
| Confidence Calibration | ±20% | ±10% |
| False Positive Rate | 15% | < 8% |
| Skip Accuracy | 60% | > 75% |

### 7.3 Ablation Studies

```python
# Compare: Base LLM vs SELF-evolved LLM
experiments = [
    "base_llama_70b",          # No fine-tuning
    "self_1_iteration",         # Single SELF iteration
    "self_3_iterations",        # Three SELF iterations
    "self_with_inference_refine", # SELF + inference-time refinement
]
```

---

## 8. Files to Create

```
~/Projects/star-platinum-cluster/research/
├── SELF-TRADING-DESIGN.md         # This document
├── self_trade_loop.py             # SELF pipeline implementation
├── meta_skill_corpus.jsonl        # Bootstrap training data
└── eval_self_trading.py           # Evaluation scripts
```

---

## 9. Risk Mitigation

### 9.1 Model Collapse Prevention

```python
# Prevent quality degradation over iterations
def quality_gate(training_data, min_quality=0.7):
    """Ensure training data meets quality threshold"""
    
    # Score each example
    scored = [(ex, score_example(ex)) for ex in training_data]
    
    # Filter low quality
    filtered = [ex for ex, score in scored if score >= min_quality]
    
    # Require minimum examples
    if len(filtered) < 100:
        raise QualityException("Insufficient quality training data")
    
    return filtered
```

### 9.2 Rollback Mechanism

```python
# Keep last N good checkpoints
CHECKPOINT_HISTORY = 5

def deploy_model(new_model, eval_results):
    if eval_results['win_rate'] < current_model_win_rate - 0.02:
        # Rollback to previous version
        return load_checkpoint(-1)
    return new_model
```

---

## References

- SELF Paper: https://arxiv.org/abs/2310.00533
- SELF v4 (detailed): https://arxiv.org/html/2310.00533v4
- Maya Paper Trader: RavenX internal system
- Star Platinum Cluster: 184GB Apple Silicon distributed compute

---

*RavenX AI — Teaching machines to learn from their mistakes.* 🖤
