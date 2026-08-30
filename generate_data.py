import pandas as pd
from datetime import datetime, timedelta
import random

def generate_recon_data():
    bank_records = []
    ledger_records = []
    ground_truth = [] 
    
    start_date = datetime(2023, 10, 1)
    
    # --- 1. CLEAN MATCHES (Caught by Pass 1) ---
    for i in range(1, 51):
        date = start_date + timedelta(days=random.randint(0, 30))
        date_str = date.strftime('%Y-%m-%d')
        amount = round(random.uniform(100.0, 5000.0), 2)
        inv_id = f"INV-{1000 + i}"
        party = f"Company_{chr(65 + (i % 26))}" 
        
        bank_records.append({
            'txn_id': f"TXN-{10000 + i}", 'date': date_str, 'amount': amount,
            'description': f"Payment to {party} ref {inv_id}", 'reference_id': inv_id
        })
        ledger_records.append({
            'ledger_id': f"LEDG-{50000 + i}", 'date': date_str, 'amount': amount,
            'party_name': party, 'invoice_id': inv_id, 'description': "Vendor payment"
        })
        ground_truth.append({'txn_id': f"TXN-{10000 + i}", 'true_ledger_id': f"LEDG-{50000 + i}"})

    # --- 2. FUZZY MATCHES (Caught by Pass 2) ---
    for i in range(51, 66):
        ledger_date = start_date + timedelta(days=random.randint(0, 30))
        bank_date = ledger_date + timedelta(days=random.randint(1, 3)) 
        amount = round(random.uniform(100.0, 5000.0), 2)
        bank_amount = round(amount * random.uniform(0.99, 1.01), 2) 
        inv_id = f"INV-{1000 + i}"
        party = f"Service_Provider_{i}"
        
        bank_records.append({
            'txn_id': f"TXN-{10000 + i}", 'date': bank_date.strftime('%Y-%m-%d'), 
            'amount': bank_amount, 'description': f"ACH Transfer Srvce_Providr_{i} {inv_id}", 'reference_id': None
        })
        ledger_records.append({
            'ledger_id': f"LEDG-{50000 + i}", 'date': ledger_date.strftime('%Y-%m-%d'), 
            'amount': amount, 'party_name': party, 'invoice_id': inv_id, 'description': "Consulting services"
        })
        ground_truth.append({'txn_id': f"TXN-{10000 + i}", 'true_ledger_id': f"LEDG-{50000 + i}"})

    # --- 3. EXCEPTIONS (Sent to Pass 3, but AI rejects them) ---
    for i in range(66, 71):
        bank_records.append({
            'txn_id': f"TXN-{10000 + i}", 'date': (start_date + timedelta(days=15)).strftime('%Y-%m-%d'),
            'amount': 25.00, 'description': "Monthly Account Maintenance Fee", 'reference_id': None
        })
        ground_truth.append({'txn_id': f"TXN-{10000 + i}", 'true_ledger_id': None})
        
    for i in range(71, 76):
        ledger_records.append({
            'ledger_id': f"LEDG-{50000 + i}", 'date': (start_date + timedelta(days=28)).strftime('%Y-%m-%d'),
            'amount': round(random.uniform(500.0, 1000.0), 2), 'party_name': "Software Inc", 
            'invoice_id': f"INV-{1000 + i}", 'description': "Annual SaaS License"
        })

    # --- 4. SEMANTIC MATCHES (Sent to Pass 3, AI rescues them) ---
    for i in range(76, 81):
        ledger_date = start_date + timedelta(days=random.randint(0, 20))
        # 5 day gap instantly fails Pass 2's 3-day rule
        bank_date = ledger_date + timedelta(days=5) 
        amount = round(random.uniform(1000.0, 3000.0), 2)
        
        bank_records.append({
            'txn_id': f"TXN-{10000 + i}", 'date': bank_date.strftime('%Y-%m-%d'), 
            'amount': amount, 'description': f"AMZN WEB SRVCS {i}", 'reference_id': f"AW-{i}"
        })
        ledger_records.append({
            'ledger_id': f"LEDG-{50000 + i}", 'date': ledger_date.strftime('%Y-%m-%d'), 
            'amount': amount, 'party_name': "AWS Cloud Hosting", 'invoice_id': f"AW-{i}", 'description': "Monthly Server Bill"
        })
        ground_truth.append({'txn_id': f"TXN-{10000 + i}", 'true_ledger_id': f"LEDG-{50000 + i}"})

    df_bank = pd.DataFrame(bank_records).sample(frac=1).reset_index(drop=True)
    df_ledger = pd.DataFrame(ledger_records).sample(frac=1).reset_index(drop=True)
    df_truth = pd.DataFrame(ground_truth) 

    df_bank.to_csv('bank_statement.csv', index=False)
    df_ledger.to_csv('ledger.csv', index=False)
    df_truth.to_csv('ground_truth.csv', index=False) 
    print(f"Generated bank_statement.csv, ledger.csv, and ground_truth.csv.")

if __name__ == "__main__":
    generate_recon_data()