import pandas as pd
from rapidfuzz import fuzz
from datetime import timedelta

def run_matching_engine():
    # 1. Load the data
    bank_df = pd.read_csv('bank_statement.csv')
    ledger_df = pd.read_csv('ledger.csv')

    # Convert date columns to actual datetime objects so we can do math on them (like +3 days)
    bank_df['date'] = pd.to_datetime(bank_df['date'])
    ledger_df['date'] = pd.to_datetime(ledger_df['date'])

    matches = [] # List to hold our successful matches

    # ==========================================
    # PASS 1: EXACT MATCH
    # ==========================================
    exact_matches = pd.merge(
        bank_df, 
        ledger_df, 
        left_on=['reference_id', 'amount', 'date'], 
        right_on=['invoice_id', 'amount', 'date'],
        how='inner'
    )

    # NEW PATCH (Fix 1): Drop duplicate ID assignments caused by many-to-many merge conflicts
    exact_matches = exact_matches.drop_duplicates(subset=['txn_id']).drop_duplicates(subset=['ledger_id'])

    # Save the successful exact matches to our list
    for index, row in exact_matches.iterrows():
        matches.append({
            'txn_id': row['txn_id'],
            'ledger_id': row['ledger_id'],
            'match_pass': 'pass1_exact',
            'confidence': 1.0
        })

    # Filter out the records we just matched so they aren't processed in Pass 2
    matched_txns = [m['txn_id'] for m in matches]
    matched_ledgers = [m['ledger_id'] for m in matches]

    unmatched_bank = bank_df[~bank_df['txn_id'].isin(matched_txns)].copy()
    unmatched_ledger = ledger_df[~ledger_df['ledger_id'].isin(matched_ledgers)].copy()

    print(f"[PASS 1] Exact Matches: {len(matches)}. Remaining Bank Candidates: {len(unmatched_bank)}")

    # ==========================================
    # PASS 2: FUZZY MATCH
    # ==========================================
    # For small datasets, looping through the unmatched rows is perfectly fine 
    # and makes the logic incredibly easy to read.
    
    newly_matched_txns = set()
    newly_matched_ledgers = set()

    for b_row in unmatched_bank.itertuples():
        if b_row.txn_id in newly_matched_txns:
            continue
            
        for l_row in unmatched_ledger.itertuples():
            if l_row.ledger_id in newly_matched_ledgers:
                continue
                
            # Rule 1: Amount must be within +/- 1%
            amount_diff_pct = abs(b_row.amount - l_row.amount) / l_row.amount
            amount_match = amount_diff_pct <= 0.01
            
            # Rule 2: Date must be within 3 days
            date_diff_days = abs((b_row.date - l_row.date).days)
            date_match = date_diff_days <= 3
            
            # Rule 3: Text Similarity
            ledger_text = f"{str(l_row.party_name)} {str(l_row.description)} {str(l_row.invoice_id)}"
            bank_text = str(b_row.description)
            text_score = fuzz.token_set_ratio(bank_text, ledger_text)
            text_match = text_score >= 70
            
            # If all three conditions are met, it's a fuzzy match!
            if amount_match and date_match and text_match:
                matches.append({
                    'txn_id': b_row.txn_id,
                    'ledger_id': l_row.ledger_id,
                    'match_pass': 'pass2_fuzzy',
                    'confidence': round(text_score / 100, 2)
                })
                newly_matched_txns.add(b_row.txn_id)
                newly_matched_ledgers.add(l_row.ledger_id)
                break 

    # ==========================================
    # PREPARE FINAL OUTPUTS
    # ==========================================
    
    matches_df = pd.DataFrame(matches)
    
    final_unmatched_bank = unmatched_bank[~unmatched_bank['txn_id'].isin(newly_matched_txns)]
    final_unmatched_ledger = unmatched_ledger[~unmatched_ledger['ledger_id'].isin(newly_matched_ledgers)]

    print(f"[PASS 2] Fuzzy Matches: {len(newly_matched_txns)}. Pushing {len(final_unmatched_bank)} to Pass 3 (LLM).")

    final_unmatched_bank['date'] = final_unmatched_bank['date'].dt.strftime('%Y-%m-%d')
    final_unmatched_ledger['date'] = final_unmatched_ledger['date'].dt.strftime('%Y-%m-%d')

    matches_df.to_csv('matches_stage1.csv', index=False)
    final_unmatched_bank.to_csv('unmatched_bank.csv', index=False)
    final_unmatched_ledger.to_csv('unmatched_ledger.csv', index=False)
    
    pass1_count = len(matches_df[matches_df['match_pass'] == 'pass1_exact'])
    pass2_count = len(matches_df[matches_df['match_pass'] == 'pass2_fuzzy'])
    
    print("\n--- RECONCILIATION SUMMARY ---")
    print(f"Total Bank Records: {len(bank_df)}")
    print(f"Total Ledger Records: {len(ledger_df)}")
    print("-" * 30)
    print(f"Pass 1 (Exact) Matches: {pass1_count}")
    print(f"Pass 2 (Fuzzy) Matches: {pass2_count}")
    print("-" * 30)
    print(f"Remaining Unmatched Bank: {len(final_unmatched_bank)} (Exceptions to send to AI)")
    print(f"Remaining Unmatched Ledger: {len(final_unmatched_ledger)} (Exceptions to send to AI)")
    print("Files matches_stage1.csv, unmatched_bank.csv, and unmatched_ledger.csv generated successfully.\n")

if __name__ == "__main__":
    run_matching_engine()