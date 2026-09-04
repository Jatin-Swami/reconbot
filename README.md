# ReconBot: Cost-Aware AI Financial Reconciliation

**ReconBot** is a 3-pass intelligent reconciliation pipeline designed to automate the clearing of bank statement and ledger discrepancies. Built for the Razorpay hackathon, this engine minimizes expensive LLM API calls by routing transactions through progressively complex local filters, utilizing AI strictly as a last resort for semantic anomalies.

## 🧠 The Architecture: A 3-Pass Funnel

Rather than passing raw financial data directly to an LLM (which is slow, expensive, and prone to hallucination), ReconBot utilizes a funnel architecture to achieve 90%+ compute savings.

1. **Pass 1: Deterministic Match (Pandas)**
   * **Mechanism:** Exact inner merge on `date`, `amount`, and `reference_id`.
   * **Safeguard:** Ambiguity-safe conflict resolution — if a date/amount/reference_id collision matches more than one row on either side, none of the colliding rows are auto-accepted. They're deferred to Pass 2/3, which have more context (description text, date proximity) to break the tie, rather than being silently dropped or arbitrarily assigned.
2. **Pass 2: Fuzzy Match (RapidFuzz)**
   * **Mechanism:** Catches typos, minor date shifts, and missing reference fields.
   * **Ruleset:** Amount variance ≤ 1%, Date window ≤ 3 days, Text similarity ≥ 70%.
   * **Innovation:** Concatenates `invoice_id` into the fuzzy token pool to bridge extreme vendor abbreviations without triggering the LLM.
   * **Performance:** Uses a date-bucketed blocking index instead of a raw cross product, so each bank row is only ever compared against ledger rows that could satisfy the 3-day rule. See `benchmark_scale.py` Scenario 2 for a measured speedup vs. the naive nested loop on a stress-test dataset.
3. **Pass 3: Semantic Match (Groq / `gpt-oss-20b`)**
   * **Mechanism:** Handles heavy semantic drift (e.g., matching "AMZN WEB SRVCS" to "AWS Cloud Hosting" outside the 3-day window).
   * **Safeguards:** Implements strict hallucination guards (verifying the returned ID exists in the candidate pool) and requires an AI confidence score > 0.8. 
   * **Exceptions:** Unresolvable transactions (e.g., universal bank fees) are safely isolated into an exceptions queue.

---

## 🛠️ Engineering Rigor & Diagnostic Tools

This repository includes standalone diagnostic scripts designed to mathematically validate the pipeline's logic and performance. Reviewers are encouraged to run these locally:

* **`python benchmark_scale.py`** 
  Two scenarios: (1) a realistic 10,000-row mix measuring end-to-end throughput, and (2) a stress test that runs the *same* large unmatched pool through both the blocked and naive O(n×m) Pass 2 implementations back-to-back, printing the measured speedup and asserting the two produce identical matches.
* **`python tune_thresholds.py`** 
  The mathematical justification for the Pass 2 text-similarity threshold. Sweeps unmatched data across 60%, 70%, 80%, and 90% parameters, calculating precision against a hidden ground-truth file to prove zero false-positives at the 70% mark.
* **`python verify_accuracy.py`** 
  A strict correctness audit. Compares the final pipeline output against the generated ground-truth pairings to output True Positives, False Positives, False Negatives, Precision, Recall, and F1. Also flags (rather than silently allowing) any case where the pipeline assigned the same ledger_id to two different transactions.

---

## 🚀 Quick Start (Local Deployment)

**1. Clone & Install**
```bash
git clone https://github.com/Jatin-Swami/reconbot.git
cd reconbot
pip install -r requirements.txt
```

**2. Configure Environment**
Create a `.env` file in the root directory and add your Groq API key:
```text
GROQ_API_KEY=gsk_your_api_key_here
```

**3. Run the Pipeline (in order)**

Each script reads files written by the one before it, so run them in this order the first time:

```bash
python generate_data.py    # 1. Creates bank_statement.csv, ledger.csv, ground_truth.csv
python match_engine.py     # 2. Pass 1 + 2 (local). Creates matches_stage1.csv, unmatched_*.csv, run_state.json
python pass3_engine.py     # 3. Pass 3 (LLM). Creates matches_stage2.csv, exceptions.csv, cost_metrics.json
python verify_accuracy.py  # 4. Optional: audits the final result against ground_truth.csv
```

| Step | Script | Depends on | Produces |
|---|---|---|---|
| 1 | `generate_data.py` | — | `bank_statement.csv`, `ledger.csv`, `ground_truth.csv` |
| 2 | `match_engine.py` | step 1 | `matches_stage1.csv`, `unmatched_bank.csv`, `unmatched_ledger.csv`, `run_state.json` |
| 3 | `pass3_engine.py` | step 2 | `matches_stage2.csv`, `exceptions.csv`, `cost_metrics.json` |
| 4 | `verify_accuracy.py` | steps 1–3 | audit printout only (no file output) |

`tune_thresholds.py` and `benchmark_scale.py` are independent diagnostics — `tune_thresholds.py` only needs step 1 to have run, and `benchmark_scale.py` generates and reconciles its own synthetic data, so it can be run any time with no setup at all.

> **Note:** `match_engine.py` clears out `matches_stage2.csv`, `exceptions.csv`, and `cost_metrics.json` at the start of every run. This is intentional — it stops a stale Pass 3 result from a previous run being silently reported alongside a new Pass 1/2 run. If you only ran steps 1–2 and then check `verify_accuracy.py`, seeing false negatives for the transactions still waiting on Pass 3 is expected, not a bug — run `pass3_engine.py` (step 3) to resolve them.

> **Note:** All CSV/JSON/JSONL files produced by the pipeline (`bank_statement.csv`, `ledger.csv`, `ground_truth.csv`, `matches_stage1.csv`, `matches_stage2.csv`, `unmatched_bank.csv`, `unmatched_ledger.csv`, `exceptions.csv`, `run_state.json`, `cost_metrics.json`, `llm_audit_log.jsonl`) are generated locally and are not committed to the repo. Run the pipeline once (steps 1–3 above) to produce them before launching the dashboard or running the diagnostic scripts.

**4. Launch the Dashboard (optional)**
```bash
streamlit run app.py
```
*Click **"🚀 Run Full Reconciliation"** in the sidebar to execute steps 2 and 3 automatically and view the real-time compute savings metric — you don't need to run `match_engine.py` / `pass3_engine.py` manually if you're using the dashboard. Step 1 (`generate_data.py`) still needs to be run once from the CLI first, since the dashboard doesn't generate the source data itself.*

---

## 📁 Repository Structure 

For the purposes of this hackathon, the repository relies on a flat directory structure to guarantee zero-friction local deployment for reviewers.

* **`app.py`**: The Streamlit frontend and pipeline orchestrator.
* **`match_engine.py`**: The local deterministic and fuzzy matching engine (Passes 1 & 2). Writes `run_state.json` as the single source of truth for dataset size, so cost metrics never rely on a hardcoded number.
* **`pass3_engine.py`**: The LLM reasoning engine, complete with exponential backoff rate limiters and JSONL audit logging.
* **`generate_data.py`**: Synthetic data generator containing exact, fuzzy, semantic, and exception test cases.
* **`llm_audit_log.jsonl`**: Append-only audit trail capturing every raw prompt and response from the AI.
* **`verify_accuracy.py` / `tune_thresholds.py` / `benchmark_scale.py`**: Diagnostic scripts — see above.

---

## ⚠️ Known Limitations (Honest Disclosure)

We'd rather name these ourselves than have a judge find them first:

* **Synthetic data only.** The pipeline has been validated against a generator-produced dataset with known ground truth, not real production bank/ledger exports, which will have messier formatting, timezones, and encoding issues.
* **Single-currency assumption.** Amount matching assumes both sides are in the same currency (INR in the sample data); no FX conversion or multi-currency handling yet.
* **Sequential Pass 3 calls.** LLM calls in `pass3_engine.py` run one bank transaction at a time (not batched/parallelized), which is the right call for audit-log ordering and rate-limit safety at hackathon scale, but would need batching for production volume.
* **No persistence layer.** State lives in flat CSVs for local judging; see the Production Roadmap below for the intended upgrade path.
* **Greedy matching is order-sensitive under fully ambiguous data.** Pass 2's "first candidate that satisfies all three rules wins" strategy can, in principle, leave a transaction unmatched even though a different assignment order would have matched it — this only surfaces when multiple unmatched rows share an identical amount *and* description within the same date window (verified via a stress test in `benchmark_scale.py`; does not occur in the sample dataset, where every party/invoice combination is unique). A production version would resolve this with a proper bipartite-matching algorithm (e.g. the Hungarian algorithm) instead of greedy first-match.

---

## 🏭 Production Roadmap

While the hackathon prototype utilizes local CSVs and a flat directory for ease of evaluation, the architecture is designed for enterprise deployment:

* **Data Ingestion:** Local `.csv` generation would be replaced by direct integrations with AWS S3 or a Snowflake data warehouse for live ledger syncing.
* **Microservice Architecture:** The codebase would be modularized into a `src/` directory, separating the Streamlit frontend from a FastAPI backend to handle concurrent webhook triggers.
* **Compliance & Monitoring:** The local `llm_audit_log.jsonl` file would be upgraded to stream directly into Datadog or AWS CloudWatch, providing compliance teams with real-time visibility into AI reasoning and token expenditure.
* **Pass 3 Batching:** Sequential per-transaction LLM calls would move to a batched/async request pattern to cut latency at production volume.
* **Optimal Matching:** Pass 2's greedy first-match strategy would be replaced with a proper bipartite-matching solver (e.g. `scipy.optimize.linear_sum_assignment`) to guarantee a globally optimal match set rather than an order-dependent greedy one.