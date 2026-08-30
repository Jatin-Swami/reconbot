import os
import json
import pandas as pd
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
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

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)

    # 3. Handle matches vs exceptions based on threshold
    if result.get("match_found") and result.get("confidence", 0) > 0.8 and result.get("matched_ledger_id"):
        matches_stage2.append({
            "txn_id": bank_txn["txn_id"],
            "ledger_id": result["matched_ledger_id"],
            "confidence": result["confidence"],
            "reasoning": result["reasoning"]
        })
        # Remove matched ledger item so it can't be matched twice
        ledger_candidates = [c for c in ledger_candidates if c["ledger_id"] != result["matched_ledger_id"]]
    else:
        exceptions.append({
            "txn_id": bank_txn["txn_id"],
            "reasoning": result.get("reasoning", "No high-confidence candidate matched.")
        })

# 4. Save output CSVs to fulfill the contract
pd.DataFrame(matches_stage2).to_csv("matches_stage2.csv", index=False)
pd.DataFrame(exceptions).to_csv("exceptions.csv", index=False)

print(f"Pass 3 Complete: {len(matches_stage2)} matches, {len(exceptions)} exceptions.")