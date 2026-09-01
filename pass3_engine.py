import os
import json
import time
import sys
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    print("⚠️ GROQ_API_KEY missing! Skipping Pass 3 gracefully.")
    # Route all leftovers to exceptions without crashing.
    # Explicit columns so a pd.read_csv().empty check downstream (app.py) still
    # works and doesn't KeyError on a header-less CSV.
    pd.DataFrame([], columns=["txn_id", "ledger_id", "confidence", "reasoning"]).to_csv("matches_stage2.csv", index=False)
    if os.path.exists("unmatched_bank.csv"):
        unmatched_df = pd.read_csv("unmatched_bank.csv")
        unmatched_df["reasoning"] = "Pass 3 Skipped: Missing API Key."
        unmatched_df[["txn_id", "reasoning"]].to_csv("exceptions.csv", index=False)
    else:
        pd.DataFrame([], columns=["txn_id", "reasoning"]).to_csv("exceptions.csv", index=False)

    # Still surface a real (0%) cost-savings number instead of leaving app.py
    # showing a stale metric from a previous run.
    if os.path.exists("run_state.json"):
        with open("run_state.json") as f:
            run_state = json.load(f)
        with open("cost_metrics.json", "w") as f:
            json.dump({"compute_saved_pct": 0.0, "note": "Pass 3 skipped: missing API key"}, f)
    sys.exit(0) # Exit cleanly before Groq init

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# 1. Load unmatched data
bank_df = pd.read_csv("unmatched_bank.csv")
ledger_df = pd.read_csv("unmatched_ledger.csv")

# Convert all remaining ledger rows into a clean candidate list
ledger_candidates = ledger_df.to_dict(orient="records")

matches_stage2 = []
exceptions = []

# System prompt provided by your teammate
SYSTEM_PROMPT = """You are an expert AI Finance Controller. Your task is to reconcile unmatched bank transactions against unmatched internal ledger entries. You will receive one bank transaction and a list of potential ledger candidates.
Evaluate them based on subtle clues like typos, embedded invoice numbers, or slight date shifts.
If you are confident (score > 0.8), declare a match. If the transaction is a bank fee, duplicate, or completely unresolvable, set match_found to false.
Output your final decision strictly in the requested JSON format."""

# 2. Iterate through bank transactions (1 API call per bank txn)
for _, bank_row in bank_df.iterrows():
    bank_txn = bank_row.to_dict()
    
    user_prompt = f"""
    Bank Transaction to Match:
    {json.dumps(bank_txn, indent=2)}

    Potential Ledger Candidates:
    {json.dumps(ledger_candidates, indent=2)}

    Respond with JSON matching this schema:
    {{
      "match_found": true/false,
      "matched_ledger_id": "L-XXX or null",
      "confidence": float between 0.0 and 1.0,
      "reasoning": "Clear explanation of why this candidate matched or why it is an exception"
    }}
    """

    print(f"Analyzing {bank_txn['txn_id']}...", end=" ", flush=True)
    retry_delay = 2
    
    while True:
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            # --- Raw JSONL Audit Logging (append-only, one line per LLM call) ---
            try:
                with open("llm_audit_log.jsonl", "a") as f:
                    log_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "txn_id": bank_txn["txn_id"],
                        "raw_response": response.choices[0].message.content
                    }
                    f.write(json.dumps(log_entry) + "\n")
            except Exception as log_e:
                print(f"⚠️ Non-fatal: Failed to write to audit log for {bank_txn['txn_id']}")

            result = json.loads(response.choices[0].message.content)
            
            # NEW PATCH: Safe schema extraction to prevent KeyErrors on malformed LLM responses
            match_found = result.get("match_found", False)
            matched_id = result.get("matched_ledger_id")
            confidence = result.get("confidence", 0.0)
            reasoning = result.get("reasoning", "No reasoning provided by LLM.")
            
            # Extract valid IDs to prevent hallucination acceptance
            valid_ledger_ids = {c["ledger_id"] for c in ledger_candidates}

            # 3. Handle matches vs exceptions safely
            if match_found and confidence > 0.8 and matched_id in valid_ledger_ids:
                matches_stage2.append({
                    "txn_id": bank_txn["txn_id"],
                    "ledger_id": matched_id,
                    "confidence": confidence,
                    "reasoning": reasoning
                })
                # Remove matched ledger item so it can't be matched twice
                ledger_candidates = [c for c in ledger_candidates if c["ledger_id"] != matched_id]
            else:
                exceptions.append({
                    "txn_id": bank_txn["txn_id"],
                    "reasoning": reasoning if not match_found else "LLM matched invalid ID or low confidence."
                })
                
            print("[SUCCESS] Complete")
            break # Break the while loop on success
            
        except Exception as e:
            if "429" in str(e):
                print(f"[WAIT] Rate limit. Backing off {retry_delay}s...", end=" ", flush=True)
                time.sleep(retry_delay)
                retry_delay *= 2 # Exponential backoff
            else:
                print(f"[ERROR] JSON/API Error: Pushing to exceptions.")
                exceptions.append({
                    "txn_id": bank_txn["txn_id"],
                    "reasoning": "AI reconciliation failed due to syntax or network error."
                })
                break # Break on non-recoverable errors

# 4. Save output CSVs to fulfill the contract
# Explicitly define columns so the CSV has headers even if the AI found 0 matches
df_stage2 = pd.DataFrame(matches_stage2, columns=["txn_id", "ledger_id", "confidence", "reasoning"])
df_exceptions = pd.DataFrame(exceptions, columns=["txn_id", "reasoning"])

df_stage2.to_csv("matches_stage2.csv", index=False)
df_exceptions.to_csv("exceptions.csv", index=False)

# 5. Calculate and export cost metrics
# Read the true dataset size from run_state.json (written by match_engine.py) instead
# of hardcoding it. Falls back gracefully if match_engine.py wasn't run first, so this
# script never crashes -- it just can't compute a percentage without a denominator.
txns_sent_to_ai = len(bank_df)

if os.path.exists("run_state.json"):
    with open("run_state.json") as f:
        run_state = json.load(f)
    total_initial_txns = run_state["total_bank_txns"]
else:
    print("⚠️  run_state.json not found (run match_engine.py first). "
          "Falling back to an estimate: local resolutions + txns sent to AI.")
    total_initial_txns = txns_sent_to_ai  # can't know locally-resolved count without it

txns_resolved_locally = total_initial_txns - txns_sent_to_ai
compute_saved_pct = (txns_resolved_locally / total_initial_txns) * 100 if total_initial_txns > 0 else 0

# Removed the money bag emoji to prevent Windows terminal CP1252 crash
print(f"\n--- [$] PIPELINE COST SUMMARY ---")
print(f"Pass 3 Complete: {len(matches_stage2)} matches, {len(exceptions)} exceptions.")
print(f"Total Transactions: {total_initial_txns}")
print(f"Resolved via Local Rules (Free): {txns_resolved_locally}")
print(f"Sent to AI (Paid Compute): {txns_sent_to_ai}")
print(f"Compute Costs Saved: {compute_saved_pct:.1f}%")

# Save metric for the dashboard
with open("cost_metrics.json", "w") as f:
    json.dump({"compute_saved_pct": compute_saved_pct}, f)