# ReconBot 🤖
**Razorpay AI Buildathon 2026 — Track 4: AI Finance Controller**

ReconBot is an AI agent that reconciles a company's bank statement against its internal ledger. It uses a three-pass architecture to maximize speed and minimize API costs, falling back to an LLM only for ambiguous matches, and bubbling up honest exceptions when confidence is low.

## 🏗️ Architecture Pipeline
1. **Pass 1 (Exact Match):** `reference_id` + `amount` + `date` all match.
2. **Pass 2 (Fuzzy Match):** `amount` within tolerance, dates close, descriptions similar (via `rapidfuzz`).
3. **Pass 3 (AI Match):** Claude 3.5 Haiku evaluates the leftovers via structured tool use.

## 📁 File Contract
To ensure the parallel development pipeline works, we adhere to these exact I/O files:

**Input Data:**
* `bank_statement.csv`
* `ledger.csv`

**Stage 1 & 2 Output (Deterministic):**
* `matches_stage1.csv`
* `unmatched_bank.csv`
* `unmatched_ledger.csv`

**Stage 3 Output (AI):**
* `matches_stage2.csv`
* `exceptions.csv`

## 🚀 Setup Instructions
*(To be completed on Day 6)*
