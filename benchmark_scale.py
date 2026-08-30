import pandas as pd
from rapidfuzz import fuzz
from datetime import datetime, timedelta
import random
import time

def run_benchmark():
    print("Generating 10,000 synthetic records for benchmarking...")
    random.seed(42)
    start_date = datetime(2023, 10, 1)
    
    b_recs, l_recs = [], []
    
    # 9000 exact matches
    for i in range(9000):
        d_str = (start_date + timedelta(days=random.randint(0, 30))).strftime('%Y-%m-%d')
        b_recs.append({'txn_id': f"T-{i}", 'date': d_str, 'amount': 100.0, 'description': "A", 'reference_id': f"I-{i}"})
        l_recs.append({'ledger_id': f"L-{i}", 'date': d_str, 'amount': 100.0, 'party_name': "A", 'description': "B", 'invoice_id': f"I-{i}"})
        
    # 1000 fuzzy matches
    for i in range(9000, 10000):
        d_str = (start_date + timedelta(days=random.randint(0, 30))).strftime('%Y-%m-%d')
        b_recs.append({'txn_id': f"T-{i}", 'date': d_str, 'amount': 101.0, 'description': "Fuzz A", 'reference_id': None})
        l_recs.append({'ledger_id': f"L-{i}", 'date': d_str, 'amount': 100.0, 'party_name': "Fuzz A", 'description': "B", 'invoice_id': f"I-{i}"})
    
    bank_df = pd.DataFrame(b_recs)
    ledger_df = pd.DataFrame(l_recs)
    
    print("Running Local Pipeline (Pass 1 & Pass 2)...")
    start_time = time.time()
    
    # Pass 1
    bank_df['date'] = pd.to_datetime(bank_df['date'])
    ledger_df['date'] = pd.to_datetime(ledger_df['date'])
    exact = pd.merge(bank_df, ledger_df, left_on=['reference_id', 'amount', 'date'], right_on=['invoice_id', 'amount', 'date'], how='inner')
    exact = exact.drop_duplicates(subset=['txn_id']).drop_duplicates(subset=['ledger_id'])
    
    matched_t = set(exact['txn_id'])
    matched_l = set(exact['ledger_id'])
    ubank = bank_df[~bank_df['txn_id'].isin(matched_t)]
    uledg = ledger_df[~ledger_df['ledger_id'].isin(matched_l)]
    
    # Pass 2
    new_t, new_l = set(), set()
    for b in ubank.itertuples():
        for l in uledg.itertuples():
            if l.ledger_id in new_l: continue
            if abs(b.amount - l.amount) / l.amount <= 0.01 and abs((b.date - l.date).days) <= 3:
                if fuzz.token_set_ratio(str(b.description), f"{str(l.party_name)} {str(l.description)}") >= 70:
                    new_t.add(b.txn_id)
                    new_l.add(l.ledger_id)
                    break
                    
    end_time = time.time()
    total_time = end_time - start_time
    total_matches = len(matched_t) + len(new_t)
    
    print("-" * 35)
    print(f"Total Matches:    {total_matches} / 10000")
    print(f"Total Wall Time:  {total_time:.2f} seconds")
    print(f"Throughput Speed: {10000 / total_time:.0f} rows/second")

if __name__ == "__main__":
    run_benchmark()