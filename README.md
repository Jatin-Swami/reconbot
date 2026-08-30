# ReconBot: Cost-Aware AI Financial Reconciliation

**ReconBot** is a 3-pass intelligent reconciliation pipeline designed to automate the clearing of bank statement and ledger discrepancies. Built for the Razorpay hackathon, this engine minimizes expensive LLM API calls by routing transactions through progressively complex local filters, utilizing AI strictly as a last resort for semantic anomalies.

## 🧠 The Architecture: A 3-Pass Funnel

Rather than passing raw financial data directly to an LLM (which is slow, expensive, and prone to hallucination), ReconBot utilizes a funnel architecture to achieve 90%+ compute savings.

1. **Pass 1: Deterministic Match (Pandas)**
   * **Mechanism:** Exact inner merge on `date`, `amount`, and `reference_id`.
   * **Safeguard:** Built-in Cartesian conflict resolution to prevent duplicate assignments on identical daily transactions.
2. **Pass 2: Fuzzy Match (RapidFuzz)**
   * **Mechanism:** Catches typos, minor date shifts, and missing reference fields.
   * **Ruleset:** Amount variance ≤ 1%, Date window ≤ 3 days, Text similarity ≥ 70%.
   * **Innovation:** Concatenates `invoice_id` into the fuzzy token pool to bridge extreme vendor abbreviations without triggering the LLM.
3. **Pass 3: Semantic Match (Groq / `gpt-oss-20b`)**
   * **Mechanism:** Handles heavy semantic drift (e.g., matching "AMZN WEB SRVCS" to "AWS Cloud Hosting" outside the 3-day window).
   * **Safeguards:** Implements strict hallucination guards (verifying the returned ID exists in the candidate pool) and requires an AI confidence score > 0.8. 
   * **Exceptions:** Unresolvable transactions (e.g., universal bank fees) are safely isolated into an exceptions queue.

---

## 🛠️ Engineering Rigor & Diagnostic Tools

This repository includes standalone diagnostic scripts designed to mathematically validate the pipeline's logic and performance. Reviewers are encouraged to run these locally:

* **`python benchmark_scale.py`** 
  Proves the local engine (Pass 1 & 2) scales gracefully. Generates and reconciles a synthetic 10,000-row dataset, measuring wall-clock time and rows-per-second throughput.
* **`python tune_thresholds.py`** 
  The mathematical justification for the Pass 2 text-similarity threshold. Sweeps unmatched data across 60%, 70%, 80%, and 90% parameters, calculating precision against a hidden ground-truth file to prove zero false-positives at the 70% mark.
* **`python verify_accuracy.py`** 
  A strict correctness audit. Compares the final pipeline output against the generated ground-truth pairings to output True Positives, False Positives, False Negatives, and an overall Precision Score.

---

## 🚀 Quick Start (Local Deployment)

**1. Clone & Install**
```bash
git clone [https://github.com/yourusername/reconbot.git](https://github.com/yourusername/reconbot.git)
cd reconbot
pip install -r requirements.txt
```

**2. Configure Environment**
Create a `.env` file in the root directory and add your Groq API key:
```text
GROQ_API_KEY=gsk_your_api_key_here
```

**3. Generate Test Data & Launch**
```bash
# Generate the synthetic bank statement, ledger, and hidden ground-truth files
python generate_data.py

# Launch the Streamlit dashboard
streamlit run app.py
```
*Click **"🚀 Run Full Reconciliation"** in the sidebar to execute the pipeline and view the real-time compute savings metric.*

---

## 📁 Repository Structure 

For the purposes of this hackathon, the repository relies on a flat directory structure to guarantee zero-friction local deployment for reviewers.

* **`app.py`**: The Streamlit frontend and pipeline orchestrator.
* **`match_engine.py`**: The local deterministic and fuzzy matching engine (Passes 1 & 2).
* **`pass3_engine.py`**: The LLM reasoning engine, complete with exponential backoff rate limiters and JSONL audit logging.
* **`generate_data.py`**: Synthetic data generator containing exact, fuzzy, semantic, and exception test cases.
* **`llm_audit_log.jsonl`**: Append-only audit trail capturing every raw prompt and response from the AI.

---

## 🏭 Production Roadmap

While the hackathon prototype utilizes local CSVs and a flat directory for ease of evaluation, the architecture is designed for enterprise deployment:

* **Data Ingestion:** Local `.csv` generation would be replaced by direct integrations with AWS S3 or a Snowflake data warehouse for live ledger syncing.
* **Microservice Architecture:** The codebase would be modularized into a `src/` directory, separating the Streamlit frontend from a FastAPI backend to handle concurrent webhook triggers.
* **Compliance & Monitoring:** The local `llm_audit_log.jsonl` file would be upgraded to stream directly into Datadog or AWS CloudWatch, providing compliance teams with real-time visibility into AI reasoning and token expenditure.