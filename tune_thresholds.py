import pandas as pd
from rapidfuzz import fuzz
import os

def sweep_thresholds():
    if not os.path.exists('bank_statement.csv') or not os.path.exists('ground_truth.csv'):
        print("Run generate_data.py first.")
        return

    bank_df = pd.read_csv('bank_statement.csv')
    ledger_df = pd.read_csv('ledger.csv')
    gt_df = pd.read_csv('ground_truth.csv')

    bank_df['date'] = pd.to_datetime(bank_df['date'])
    ledger_df['date'] = pd.to_datetime(ledger_df['date'])

    # 1. Run Exact Match (Pass 1) to get the true starting point for Pass 2
    exact_matches = pd.merge(
        bank_df, 
        ledger_df, 
        left_on=['reference_id', 'amount', 'date'], 
        right_on=['invoice_id', 'amount', 'date'], 
        how='inner'
    )
    exact_matches = exact_matches.drop_duplicates(subset=['txn_id']).drop_duplicates(subset=['ledger_id'])
    
    matched_txns = set(exact_matches['txn_id'])
    matched_ledgers = set(exact_matches['ledger_id'])

    # 2. Isolate the unmatched data that Pass 2 should actually evaluate
    unmatched_bank = bank_df[~bank_df['txn_id'].isin(matched_txns)].copy()
    unmatched_ledger = ledger_df[~ledger_df['ledger_id'].isin(matched_ledgers)].copy()

    print(f"\n{'Threshold':<10} | {'Matches':<10} | {'Precision':<10}")
    print("-" * 35)

    for thresh in [60, 70, 80, 90]:
        matches = []
        newly_matched_txns, newly_matched_ledgers = set(), set()
        
        for b_row in unmatched_bank.itertuples():
            for l_row in unmatched_ledger.itertuples():
                if l_row.ledger_id in newly_matched_ledgers: continue
                
                amount_match = abs(b_row.amount - l_row.amount) / l_row.amount <= 0.01
                date_match = abs((b_row.date - l_row.date).days) <= 3
                text_score = fuzz.token_set_ratio(str(b_row.description), f"{str(l_row.party_name)} {str(l_row.description)} {str(l_row.invoice_id)}")
                
                if amount_match and date_match and text_score >= thresh:
                    matches.append({'txn_id': b_row.txn_id, 'ledger_id': l_row.ledger_id})
                    newly_matched_txns.add(b_row.txn_id)
                    newly_matched_ledgers.add(l_row.ledger_id)
                    break
        
        if not matches:
            print(f"{thresh:<10} | {0:<10} | 0.00%")
            continue
            
        # 3. Evaluate the matches against the hidden truth file
        eval_df = pd.merge(pd.DataFrame(matches), gt_df, on='txn_id', how='left')
        tp = len(eval_df[eval_df['ledger_id'] == eval_df['true_ledger_id']])
        fp = len(eval_df[eval_df['ledger_id'] != eval_df['true_ledger_id']])
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        
        print(f"{thresh:<10} | {len(matches):<10} | {precision:.2%}")

if __name__ == "__main__":
    sweep_thresholds()