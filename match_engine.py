import json
import os
import pandas as pd
from rapidfuzz import fuzz
from datetime import timedelta

# Files produced by the LATER stages of the pipeline (Pass 3 / cost summary).
# match_engine.py always runs first, so if we don't clear these out here, a
# stale matches_stage2.csv/exceptions.csv from a PREVIOUS full run can sit on
# disk and get silently picked up by verify_accuracy.py or app.py after this
# run -- producing accuracy numbers or a dashboard that don't reflect the
# current bank_statement.csv/ledger.csv at all. Clearing them makes it obvious
# (empty tables / "run Pass 3" state) rather than quietly wrong.
_DOWNSTREAM_ARTIFACTS = ['matches_stage2.csv', 'exceptions.csv', 'cost_metrics.json']

def run_matching_engine():
    for f in _DOWNSTREAM_ARTIFACTS:
        if os.path.exists(f):
            os.remove(f)

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

    # Fix: a naive drop_duplicates() here silently discards genuine, ambiguous
    # collisions (e.g. two bank txns on the same day, same amount, same ref_id)
    # WITHOUT sending the losers to Pass 2/3 -- they just vanish from every
    # output file. Instead: only auto-accept rows where BOTH the txn_id and the
    # ledger_id are unambiguous (appear exactly once in the merge result). Any
    # txn_id or ledger_id involved in a many-to-many collision is explicitly
    # excluded from Pass 1 and falls through to Pass 2/3, where the fuzzy and
    # LLM stages have more context (description, date proximity) to break the
    # tie -- and if they can't, it correctly lands in the exceptions queue for
    # a human instead of being auto-matched to the wrong counterparty or lost.
    txn_id_counts = exact_matches['txn_id'].value_counts()
    ledger_id_counts = exact_matches['ledger_id'].value_counts()
    unambiguous_mask = (
        exact_matches['txn_id'].map(txn_id_counts).eq(1) &
        exact_matches['ledger_id'].map(ledger_id_counts).eq(1)
    )
    ambiguous_count = len(exact_matches) - unambiguous_mask.sum()
    exact_matches = exact_matches[unambiguous_mask]

    if ambiguous_count > 0:
        print(f"[PASS 1] ⚠️  {ambiguous_count} exact-match candidates were ambiguous "
              f"(same date/amount/ref_id collided across multiple rows) and were "
              f"deferred to Pass 2/3 rather than silently dropped.")

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
    # Blocking index: bucket unmatched ledger rows by date so we only ever
    # compare a bank row against ledger rows that could possibly satisfy the
    # +/-3-day rule, instead of the full O(bank x ledger) cross product.
    # This turns the worst case from O(n*m) into roughly O(n*k) where k is the
    # average number of ledger candidates per 7-day window (date +/-3 days) --
    # a big win once "unmatched" volume grows past a few hundred rows, since a
    # bank/ledger pair with heavy fuzzy-match volume degrades quadratically
    # without this. See benchmark_scale.py for a stress test with a much
    # larger unmatched pool.
    ledger_date_index = {}
    for l_row in unmatched_ledger.itertuples():
        ledger_date_index.setdefault(l_row.date, []).append(l_row)

    newly_matched_txns = set()
    newly_matched_ledgers = set()

    for b_row in unmatched_bank.itertuples():
        if b_row.txn_id in newly_matched_txns:
            continue

        # Only pull ledger candidates whose date falls inside the 3-day window --
        # everything outside it fails Rule 2 anyway, so there's no reason to
        # run the (relatively expensive) fuzzy text comparison against them.
        candidate_dates = [b_row.date + timedelta(days=d) for d in range(-3, 4)]
        candidates = [l for d in candidate_dates for l in ledger_date_index.get(d, [])]

        for l_row in candidates:
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
    
    final_unmatched_bank = unmatched_bank[~unmatched_bank['txn_id'].isin(newly_matched_txns)].copy()
    final_unmatched_ledger = unmatched_ledger[~unmatched_ledger['ledger_id'].isin(newly_matched_ledgers)].copy()

    print(f"[PASS 2] Fuzzy Matches: {len(newly_matched_txns)}. Pushing {len(final_unmatched_bank)} to Pass 3 (LLM).")

    final_unmatched_bank['date'] = final_unmatched_bank['date'].dt.strftime('%Y-%m-%d')
    final_unmatched_ledger['date'] = final_unmatched_ledger['date'].dt.strftime('%Y-%m-%d')

    matches_df.to_csv('matches_stage1.csv', index=False)
    final_unmatched_bank.to_csv('unmatched_bank.csv', index=False)
    final_unmatched_ledger.to_csv('unmatched_ledger.csv', index=False)

    # Persist the run's true totals so downstream stages (Pass 3, the dashboard)
    # never have to hardcode a dataset size. This is the single source of truth
    # for "how many transactions were in this run."
    with open('run_state.json', 'w') as f:
        json.dump({
            'total_bank_txns': len(bank_df),
            'total_ledger_records': len(ledger_df),
            'resolved_locally': len(matches_df),
        }, f, indent=2)

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