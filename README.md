# 📊 ReconBot: AI Financial Reconciliation Engine

An intelligent, hybrid reconciliation pipeline built for the Razorpay Hackathon. ReconBot automates the matching of bank statements to internal ledger entries, reducing manual accounting overhead while maintaining strict auditability.

## 🧠 Architecture
ReconBot uses a 3-pass hybrid matching engine to optimize for both speed and cost:
1. **Pass 1 (Exact Match):** Standard pandas merges for identical amounts, dates, and reference IDs.
2. **Pass 2 (Fuzzy Match):** RapidFuzz evaluates string similarities (e.g., slight vendor name variations) for high-confidence matches.
3. **Pass 3 (AI Agent):** A Groq-powered LLM (`openai/gpt-oss-20b`) handles edge cases (e.g., missing invoices, date shifts, batch payments) using semantic reasoning. 

## 🚀 How to Run Locally

**1. Install Dependencies**
```bash
pip install -r requirements.txt
