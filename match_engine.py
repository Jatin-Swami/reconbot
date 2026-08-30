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
    # We use pandas "merge" to find rows where all three columns match perfectly.
    # We use an 'inner' join, which only keeps records that exist in both files.
    exact_matches = pd.merge(
        bank_df, 
        ledger_df, 
        left_on=['reference_id', 'amount', 'date'], 
        right_on=['invoice_id', 'amount', 'date'],
        how='inner'
    )

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

    # ==========================================
    # PASS 2: FUZZY MATCH
    # ==========================================
    # For small datasets, looping through the unmatched rows is perfectly fine 
    # and makes the logic incredibly easy to read.
    
    # We will keep track of newly matched IDs so we don't double-match them
    newly_matched_txns = set()
    newly_matched_ledgers = set()

    # itertuples() is a fast way to loop through rows in pandas
    for b_row in unmatched_bank.itertuples():
        if b_row.txn_id in newly_matched_txns:
            continue
            
        for l_row in unmatched_ledger.itertuples():
            if l_row.ledger_id in newly_matched_ledgers:
                continue
                
            # Rule 1: Amount must be within +/- 1%
            # formula: absolute difference / ledger amount <= 0.01
            amount_diff_pct = abs(b_row.amount - l_row.amount) / l_row.amount
            amount_match = amount_diff_pct <= 0.01
            
            # Rule 2: Date must be within 3 days
            date_diff_days = abs((b_row.date - l_row.date).days)
            date_match = date_diff_days <= 3
            
            # Rule 3: Text Similarity
            # Combine ledger party name and description to compare against bank description
            # token_set_ratio ignores word order (e.g. "Tech Corp" matches "Corp Tech")
            ledger_text = f"{str(l_row.party_name)} {str(l_row.description)}"
            bank_text = str(b_row.description)
            text_score = fuzz.token_set_ratio(bank_text, ledger_text)
            text_match = text_score >= 70  # RapidFuzz scores are 0 to 100
            
            # If all three conditions are met, it's a fuzzy match!
            if amount_match and date_match and text_match:
                matches.append({
                    'txn_id': b_row.txn_id,
                    'ledger_id': l_row.ledger_id,
                    'match_pass': 'pass2_fuzzy',
                    'confidence': round(text_score / 100, 2) # convert 70 to 0.70
                })
                newly_matched_txns.add(b_row.txn_id)
                newly_matched_ledgers.add(l_row.ledger_id)
                break # Move to the next bank transaction

    # ==========================================
    # PREPARE FINAL OUTPUTS
    # ==========================================
    
    # 1. Matches DataFrame
    matches_df = pd.DataFrame(matches)
    
    # 2. Final Unmatched DataFrames
    final_unmatched_bank = unmatched_bank[~unmatched_bank['txn_id'].isin(newly_matched_txns)]
    final_unmatched_ledger = unmatched_ledger[~unmatched_ledger['ledger_id'].isin(newly_matched_ledgers)]

    # Format dates back to strings so they look clean in the CSV
    final_unmatched_bank['date'] = final_unmatched_bank['date'].dt.strftime('%Y-%m-%d')
    final_unmatched_ledger['date'] = final_unmatched_ledger['date'].dt.strftime('%Y-%m-%d')

    # Save exactly the three files your teammate needs
    matches_df.to_csv('matches_stage1.csv', index=False)
    final_unmatched_bank.to_csv('unmatched_bank.csv', index=False)
    final_unmatched_ledger.to_csv('unmatched_ledger.csv', index=False)

    # Print a summary for you
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