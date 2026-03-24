#!/usr/bin/env python3
"""
SELF Trading Loop: Self-Evolution with Language Feedback for Trading

Inspired by SELF (https://arxiv.org/abs/2310.00533)
Adapted for trading analysis self-improvement.

Usage:
    python self_trade_loop.py --mode prepare --input decisions.jsonl --output training.jsonl
    python self_trade_loop.py --mode train --data training.jsonl --epochs 3
    python self_trade_loop.py --mode analyze --market-state state.json
"""

import argparse
import json
import asyncio
import aiohttp
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SELFConfig:
    """SELF Trading configuration"""
    # Model endpoint (Star Platinum cluster)
    model_endpoint: str = "http://localhost:52415/v1"
    model_name: str = "mlx-community/Llama-3.3-70B-Instruct-4bit"
    
    # Generation parameters
    max_tokens: int = 1024
    temperature: float = 0.7
    
    # SELF parameters
    beta: float = 0.5  # Balance between direct response and meta-skill
    quality_threshold: float = 0.7  # Minimum quality score to keep
    
    # Training
    lora_rank: int = 16
    lora_alpha: int = 32
    learning_rate: float = 2e-5
    batch_size: int = 4


# =============================================================================
# Prompts
# =============================================================================

ANALYSIS_PROMPT = """You are an expert crypto trading analyst. Analyze this market state and provide a trade recommendation.

Market State:
- Timestamp: {timestamp}
- Symbol: BTC/USD
- Timeframe: 5-minute
- Current Confidence: {confidence:.2f}

Technical Indicators:
- RSI: {rsi:.2f}
- MACD: {macd:.4f}
- Volatility: {vol:.6f}

Signal Votes:
- Bull signals: {bull_votes} votes ({bull_signals})
- Bear signals: {bear_votes} votes ({bear_signals})

Provide your analysis in this format:

## Market Assessment
[Your overall market assessment]

## Key Signals
[Most important signals and their interpretation]

## Risk Factors
[Potential risks to consider]

## Trade Recommendation
Direction: [LONG/SHORT/SKIP]
Confidence: [0.0-1.0]
Reasoning: [Brief reasoning]"""


SELF_FEEDBACK_PROMPT = """Review your trade analysis and identify potential flaws based on the actual outcome.

YOUR ORIGINAL ANALYSIS:
{initial_analysis}

ACTUAL OUTCOME:
- Result: {outcome} ({win_loss})
- PnL: {pnl:+.1f}
- Predicted Direction: {predicted}
- Actual Direction: {actual}

Based on this outcome, critique your original analysis:

## Flaws Identified
[What did you get wrong? What signals did you misinterpret?]

## Overlooked Factors
[What risks or signals did you miss?]

## Suggested Improvements
[How would you improve this analysis in the future?]

## Severity Score
[Rate the severity of your mistakes: LOW/MEDIUM/HIGH]"""


REFINEMENT_PROMPT = """Based on your self-feedback, provide an improved analysis.

ORIGINAL ANALYSIS:
{initial_analysis}

SELF-CRITIQUE:
{self_feedback}

Now provide a refined analysis that:
1. Addresses all identified flaws
2. Incorporates the overlooked factors
3. Shows more nuanced reasoning
4. Adjusts confidence appropriately

## Refined Market Assessment
[Improved assessment addressing the flaws]

## Updated Risk Analysis
[Better risk identification]

## Revised Recommendation
Direction: [LONG/SHORT/SKIP]
Confidence: [0.0-1.0] (adjusted based on critique)
Key Insight: [What you learned from this analysis]"""


# =============================================================================
# LLM Client
# =============================================================================

class SELFTrader:
    """SELF-evolving trading analyst"""
    
    def __init__(self, config: SELFConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def generate(self, prompt: str, system: str = "You are an expert crypto trading analyst.") -> str:
        """Generate completion from LLM"""
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with.")
        
        payload = {
            "model": self.config.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        
        try:
            async with self.session.post(
                f"{self.config.model_endpoint}/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"API error {response.status}: {error_text}")
                
                data = await response.json()
                return data["choices"][0]["message"]["content"]
                
        except asyncio.TimeoutError:
            raise RuntimeError("LLM request timed out")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Network error: {e}")
    
    async def generate_initial_analysis(self, market_state: Dict) -> str:
        """Step 1: Generate initial trade analysis"""
        prompt = ANALYSIS_PROMPT.format(
            timestamp=market_state.get("timestamp", "N/A"),
            confidence=market_state.get("confidence", 0.5),
            rsi=market_state.get("rsi", 50.0),
            macd=market_state.get("macd", 0.0),
            vol=market_state.get("vol", 0.0),
            bull_votes=market_state.get("bullVotes", 0),
            bear_votes=market_state.get("bearVotes", 0),
            bull_signals=", ".join(market_state.get("bull_signals", [])),
            bear_signals=", ".join(market_state.get("bear_signals", [])),
        )
        
        return await self.generate(prompt)
    
    async def generate_self_feedback(self, initial_analysis: str, outcome: Dict) -> str:
        """Step 2: Self-critique given the outcome"""
        prompt = SELF_FEEDBACK_PROMPT.format(
            initial_analysis=initial_analysis,
            outcome="WIN" if outcome.get("win") else "LOSS",
            win_loss="profit" if outcome.get("win") else "loss",
            pnl=outcome.get("pnl", 0),
            predicted=outcome.get("predicted", "N/A"),
            actual=outcome.get("actual", "N/A"),
        )
        
        return await self.generate(prompt)
    
    async def generate_refined_analysis(self, initial_analysis: str, self_feedback: str) -> str:
        """Step 3: Refine analysis based on feedback"""
        prompt = REFINEMENT_PROMPT.format(
            initial_analysis=initial_analysis,
            self_feedback=self_feedback,
        )
        
        return await self.generate(prompt)
    
    def filter_quality(self, original: str, refined: str, outcome: Dict) -> Tuple[bool, float]:
        """Step 4: Check if refinement is high quality"""
        # Quality heuristics
        quality_score = 0.0
        
        # 1. Refinement mentions the actual outcome direction
        actual = outcome.get("actual", "").lower()
        if actual and actual in refined.lower():
            quality_score += 0.3
        
        # 2. Refinement is substantive (not too short)
        if len(refined) > len(original) * 0.8:
            quality_score += 0.2
        
        # 3. Contains key learning phrases
        learning_phrases = [
            "learned", "realized", "overlooked", "missed", 
            "should have", "mistake", "improvement", "adjusted"
        ]
        phrase_count = sum(1 for p in learning_phrases if p in refined.lower())
        quality_score += min(0.3, phrase_count * 0.1)
        
        # 4. Confidence adjustment mentioned
        if "confidence" in refined.lower() and any(
            x in refined.lower() for x in ["reduce", "increase", "adjust", "lower", "higher"]
        ):
            quality_score += 0.2
        
        return quality_score >= self.config.quality_threshold, quality_score
    
    async def run_evolution_step(self, decision: Dict) -> Optional[Dict]:
        """Run complete SELF evolution step on one decision"""
        signal = decision.get("signal", {})
        outcome = decision.get("outcome", {})
        
        # Parse signals
        fired = signal.get("fired", [])
        bull_signals = [s for s in fired if "bull" in s.lower()]
        bear_signals = [s for s in fired if "bear" in s.lower()]
        
        market_state = {
            "timestamp": signal.get("ts", ""),
            "confidence": signal.get("confidence", 0.5),
            "rsi": signal.get("rsi", 50.0),
            "macd": signal.get("macd", 0.0),
            "vol": signal.get("vol", 0.0),
            "bullVotes": signal.get("bullVotes", 0),
            "bearVotes": signal.get("bearVotes", 0),
            "bull_signals": bull_signals,
            "bear_signals": bear_signals,
        }
        
        try:
            # Step 1: Initial analysis
            initial = await self.generate_initial_analysis(market_state)
            
            # Step 2: Self-feedback
            feedback = await self.generate_self_feedback(initial, outcome)
            
            # Step 3: Refined analysis
            refined = await self.generate_refined_analysis(initial, feedback)
            
            # Step 4: Quality filter
            passes, quality = self.filter_quality(initial, refined, outcome)
            
            if passes:
                return {
                    "prompt": ANALYSIS_PROMPT.format(
                        **market_state,
                        bull_signals=", ".join(market_state["bull_signals"]),
                        bear_signals=", ".join(market_state["bear_signals"]),
                    ),
                    "response": refined,
                    "quality_score": quality,
                    "metadata": {
                        "original": initial,
                        "feedback": feedback,
                        "outcome": outcome,
                        "signal": signal,
                    }
                }
            else:
                return None
                
        except Exception as e:
            print(f"Error in evolution step: {e}")
            return None


# =============================================================================
# Data Processing
# =============================================================================

def load_decisions(decisions_path: str) -> List[Dict]:
    """Load Maya decision-resolve pairs"""
    decisions = []
    current = None
    
    with open(decisions_path) as f:
        for line in f:
            record = json.loads(line)
            
            if record.get("mode") in ["oracle", "baseline"]:
                current = record
            elif record.get("mode") == "resolve" and current:
                decisions.append({
                    "signal": current,
                    "outcome": record
                })
                current = None
    
    return decisions


async def prepare_training_data(
    decisions_path: str, 
    output_path: str,
    max_examples: int = 500
):
    """Prepare SELF training data from Maya decisions"""
    config = SELFConfig()
    decisions = load_decisions(decisions_path)
    
    print(f"Loaded {len(decisions)} decision-outcome pairs")
    
    # Sample if too many
    if len(decisions) > max_examples:
        import random
        decisions = random.sample(decisions, max_examples)
        print(f"Sampled down to {len(decisions)} examples")
    
    training_data = []
    
    async with SELFTrader(config) as trader:
        for i, decision in enumerate(decisions):
            print(f"Processing {i+1}/{len(decisions)}...", end="\r")
            
            result = await trader.run_evolution_step(decision)
            if result:
                training_data.append(result)
            
            # Rate limit
            await asyncio.sleep(0.5)
    
    # Save training data
    with open(output_path, "w") as f:
        for item in training_data:
            f.write(json.dumps(item) + "\n")
    
    print(f"\nSaved {len(training_data)} training examples to {output_path}")
    
    # Print stats
    avg_quality = sum(t["quality_score"] for t in training_data) / len(training_data)
    print(f"Average quality score: {avg_quality:.3f}")


# =============================================================================
# Inference with Self-Refinement
# =============================================================================

async def analyze_with_refinement(market_state: Dict, config: SELFConfig) -> Dict:
    """Full SELF-style analysis with inference-time refinement"""
    async with SELFTrader(config) as trader:
        # Initial analysis
        initial = await trader.generate_initial_analysis(market_state)
        
        # Self-critique (without knowing outcome - speculative)
        critique_prompt = f"""Review your analysis and identify potential weaknesses or alternative interpretations.

YOUR ANALYSIS:
{initial}

Consider:
1. What could go wrong with this trade?
2. Are there any signals you might be over/under-weighting?
3. What market conditions would invalidate your thesis?

## Potential Weaknesses
[Identify 2-3 potential issues]

## Alternative Interpretation  
[How else could these signals be read?]

## Confidence Adjustment
[Should confidence be adjusted? Why?]"""
        
        critique = await trader.generate(critique_prompt)
        
        # Refine based on self-critique
        refine_prompt = f"""Based on your self-critique, provide a final refined analysis.

ORIGINAL ANALYSIS:
{initial}

SELF-CRITIQUE:
{critique}

Provide a final, balanced analysis that accounts for the identified weaknesses.

## Final Assessment
[Balanced assessment]

## Final Recommendation
Direction: [LONG/SHORT/SKIP]
Confidence: [0.0-1.0]
Key Risk: [Main risk to watch]"""
        
        refined = await trader.generate(refine_prompt)
        
        # Parse recommendation
        recommendation = parse_recommendation(refined)
        
        return {
            "initial_analysis": initial,
            "self_critique": critique,
            "refined_analysis": refined,
            "recommendation": recommendation,
        }


def parse_recommendation(analysis: str) -> Dict:
    """Extract recommendation from analysis text"""
    direction = "SKIP"
    confidence = 0.5
    
    # Look for direction
    analysis_lower = analysis.lower()
    if "direction: long" in analysis_lower or "direction:long" in analysis_lower:
        direction = "LONG"
    elif "direction: short" in analysis_lower or "direction:short" in analysis_lower:
        direction = "SHORT"
    elif "direction: skip" in analysis_lower or "direction:skip" in analysis_lower:
        direction = "SKIP"
    
    # Look for confidence
    import re
    conf_match = re.search(r"confidence:\s*([\d.]+)", analysis_lower)
    if conf_match:
        try:
            confidence = float(conf_match.group(1))
            confidence = max(0.0, min(1.0, confidence))
        except ValueError:
            pass
    
    return {
        "direction": direction,
        "confidence": confidence,
    }


# =============================================================================
# Training (LoRA)
# =============================================================================

def train_lora(data_path: str, checkpoint_path: str, config: SELFConfig):
    """Fine-tune with LoRA on SELF-generated data"""
    try:
        import mlx.core as mx
        import mlx_lm
    except ImportError:
        print("MLX LM not installed. Install with: pip install mlx-lm")
        return
    
    print(f"Loading training data from {data_path}...")
    
    # Load training data
    training_examples = []
    with open(data_path) as f:
        for line in f:
            example = json.loads(line)
            training_examples.append({
                "text": f"<s>[INST] {example['prompt']} [/INST] {example['response']}</s>"
            })
    
    print(f"Loaded {len(training_examples)} examples")
    
    # Save in format expected by mlx-lm
    train_path = Path(data_path).parent / "train.jsonl"
    with open(train_path, "w") as f:
        for ex in training_examples:
            f.write(json.dumps(ex) + "\n")
    
    # LoRA training config
    lora_config = {
        "model": config.model_name,
        "train": str(train_path),
        "lora_layers": config.lora_rank,
        "batch_size": config.batch_size,
        "iters": len(training_examples) * 3 // config.batch_size,  # 3 epochs
        "learning_rate": config.learning_rate,
        "adapter_file": checkpoint_path,
    }
    
    print(f"Training LoRA adapter...")
    print(f"Config: {lora_config}")
    
    # This would use mlx-lm's training utilities
    # For prototype, just save the config
    config_path = Path(checkpoint_path).with_suffix(".json")
    with open(config_path, "w") as f:
        json.dump(lora_config, f, indent=2)
    
    print(f"LoRA config saved to {config_path}")
    print("To train, run:")
    print(f"  mlx_lm.lora --model {config.model_name} --train {train_path} --adapter-file {checkpoint_path}")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="SELF Trading Loop")
    parser.add_argument("--mode", choices=["prepare", "train", "analyze"], required=True)
    parser.add_argument("--input", help="Input decisions file (for prepare)")
    parser.add_argument("--output", help="Output training data file (for prepare)")
    parser.add_argument("--data", help="Training data file (for train)")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--checkpoint", help="LoRA checkpoint path (for train)")
    parser.add_argument("--market-state", help="Market state JSON (for analyze)")
    parser.add_argument("--max-examples", type=int, default=500, help="Max examples to process")
    
    args = parser.parse_args()
    config = SELFConfig()
    
    if args.mode == "prepare":
        if not args.input or not args.output:
            parser.error("--input and --output required for prepare mode")
        asyncio.run(prepare_training_data(args.input, args.output, args.max_examples))
        
    elif args.mode == "train":
        if not args.data or not args.checkpoint:
            parser.error("--data and --checkpoint required for train mode")
        train_lora(args.data, args.checkpoint, config)
        
    elif args.mode == "analyze":
        if not args.market_state:
            parser.error("--market-state required for analyze mode")
        
        # Load market state
        with open(args.market_state) as f:
            market_state = json.load(f)
        
        # Run analysis
        result = asyncio.run(analyze_with_refinement(market_state, config))
        
        print("\n" + "=" * 60)
        print("SELF TRADING ANALYSIS")
        print("=" * 60)
        print("\n## Initial Analysis")
        print(result["initial_analysis"][:500] + "..." if len(result["initial_analysis"]) > 500 else result["initial_analysis"])
        print("\n## Self-Critique")
        print(result["self_critique"][:500] + "..." if len(result["self_critique"]) > 500 else result["self_critique"])
        print("\n## Final Recommendation")
        print(f"Direction: {result['recommendation']['direction']}")
        print(f"Confidence: {result['recommendation']['confidence']:.2f}")


# =============================================================================
# Integration with Maya
# =============================================================================

class SelfEvolvedAnalyst:
    """SELF-evolved analyst for Maya integration"""
    
    def __init__(self, config: Optional[SELFConfig] = None):
        self.config = config or SELFConfig()
        
    async def analyze_trade(self, decision_data: Dict) -> Dict:
        """Full SELF-style analysis for Maya integration"""
        # Extract market state from Maya decision format
        market_state = {
            "timestamp": decision_data.get("ts", ""),
            "confidence": decision_data.get("confidence", 0.5),
            "rsi": decision_data.get("rsi", 50.0),
            "macd": decision_data.get("macd", 0.0),
            "vol": decision_data.get("vol", 0.0),
            "bullVotes": decision_data.get("bullVotes", 0),
            "bearVotes": decision_data.get("bearVotes", 0),
            "bull_signals": [s for s in decision_data.get("fired", []) if "bull" in s.lower()],
            "bear_signals": [s for s in decision_data.get("fired", []) if "bear" in s.lower()],
        }
        
        result = await analyze_with_refinement(market_state, self.config)
        
        return {
            "recommendation": result["recommendation"]["direction"],
            "confidence": result["recommendation"]["confidence"],
            "warnings": self._extract_warnings(result["self_critique"]),
            "reasoning": result["refined_analysis"],
        }
    
    def _extract_warnings(self, critique: str) -> List[str]:
        """Extract warning keywords from self-critique"""
        warnings = []
        warning_patterns = [
            "overbought", "oversold", "divergence", "reversal",
            "low volume", "crowded", "uncertain", "risky",
            "consolidation", "breakout", "fake", "trap"
        ]
        
        critique_lower = critique.lower()
        for pattern in warning_patterns:
            if pattern in critique_lower:
                warnings.append(pattern)
        
        return warnings
    
    def should_skip_trade(self, maya_decision: Dict, llm_analysis: Dict) -> Tuple[bool, str]:
        """Determine if LLM analysis suggests skipping"""
        # High severity warnings
        severe_warnings = ["reversal", "overbought", "divergence", "trap"]
        has_severe = any(w in llm_analysis.get("warnings", []) for w in severe_warnings)
        
        # Confidence disagreement
        maya_conf = maya_decision.get("confidence", 0.5)
        llm_conf = llm_analysis.get("confidence", 0.5)
        conf_diff = abs(maya_conf - llm_conf)
        
        # Direction disagreement
        maya_dir = "LONG" if maya_decision.get("direction") == "UP" else "SHORT"
        llm_dir = llm_analysis.get("recommendation", "SKIP")
        direction_disagree = maya_dir != llm_dir and llm_dir != "SKIP"
        
        # Skip if severe warning, large disagreement, or direction conflict
        if has_severe:
            return True, f"Severe warning: {[w for w in llm_analysis.get('warnings', []) if w in severe_warnings]}"
        if conf_diff > 0.3:
            return True, f"Confidence disagreement: Maya={maya_conf:.2f}, LLM={llm_conf:.2f}"
        if direction_disagree:
            return True, f"Direction disagreement: Maya={maya_dir}, LLM={llm_dir}"
        
        return False, "Signals aligned"


if __name__ == "__main__":
    main()
