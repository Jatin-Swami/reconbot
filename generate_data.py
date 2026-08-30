import pandas as pd
import random
from datetime import datetime, timedelta

# Set a seed so you get the exact same "random" data every time you run this
random.seed(42)

def generate_recon_data():
    bank_records = []
    ledger_records = []
    
    # Base starting date
    start_date = datetime(2023, 10, 1)
    
    # --- 1. CLEAN MATCHES (~50 records) ---
    # These match perfectly on date, amount, and reference/invoice ID
    for i in range(1, 51):
        date = start_date + timedelta(days=random.randint(0, 30))
        date_str = date.strftime('%Y-%m-%d')
        amount = round(random.uniform(100.0, 5000.0), 2)
        inv_id = f"INV-{1000 + i}"
        party = f"Company_{chr(65 + (i % 26))}" # Creates Company_A, Company_B, etc.
        
        bank_records.append({
            'txn_id': f"TXN-{10000 + i}",
            'date': date_str,
            'amount': amount,
            'description': f"Payment to {party} ref {inv_id}",
            'reference_id': inv_id
        })
        ledger_records.append({
            'ledger_id': f"LEDG-{50000 + i}",
            'date': date_str,
            'amount': amount,
            'party_name': party,
            'invoice_id': inv_id,
            'description': "Vendor payment"
        })

    # --- 2. FUZZY MATCHES (~15 records) ---
    # These have small discrepancies: dates off by 1-3 days, typos, missing reference fields
    for i in range(51, 66):
        ledger_date = start_date + timedelta(days=random.randint(0, 30))
        # Bank processes it 1-3 days later
        bank_date = ledger_date + timedelta(days=random.randint(1, 3)) 
        
        amount = round(random.uniform(100.0, 5000.0), 2)
        # Bank amount slightly off (e.g. 1% fee deducted)
        bank_amount = round(amount * random.uniform(0.99, 1.01), 2) 
        
        inv_id = f"INV-{1000 + i}"
        party = f"Service_Provider_{i}"
        
        # Bank description has a typo, and the reference_id is missing from its proper column
        bank_desc = f"ACH Transfer Srvce_Providr_{i} {inv_id}"
        
        bank_records.append({
            'txn_id': f"TXN-{10000 + i}",
            'date': bank_date.strftime('%Y-%m-%d'),
            'amount': bank_amount,
            'description': bank_desc,
            'reference_id': None  # Missing! Hidden in description instead
        })
        ledger_records.append({
            'ledger_id': f"LEDG-{50000 + i}",
            'date': ledger_date.strftime('%Y-%m-%d'),
            'amount': amount,
            'party_name': party,
            'invoice_id': inv_id,
            'description': "Consulting services"
        })

    # --- 3. EXCEPTIONS (~10 records) ---
    # Unmatched Bank Records (e.g., unexpected bank fees)
    for i in range(66, 71):
        bank_records.append({
            'txn_id': f"TXN-{10000 + i}",
            'date': (start_date + timedelta(days=15)).strftime('%Y-%m-%d'),
            'amount': 25.00,
            'description': "Monthly Account Maintenance Fee",
            'reference_id': None
        })
        
    # Unmatched Ledger Records (e.g., pending payments not yet in bank)
    for i in range(71, 76):
        ledger_records.append({
            'ledger_id': f"LEDG-{50000 + i}",
            'date': (start_date + timedelta(days=28)).strftime('%Y-%m-%d'),
            'amount': round(random.uniform(500.0, 1000.0), 2),
            'party_name': "Software Inc",
            'invoice_id': f"INV-{1000 + i}",
            'description': "Annual SaaS License"
        })

    # Convert to pandas DataFrames (tables)
    df_bank = pd.DataFrame(bank_records)
    df_ledger = pd.DataFrame(ledger_records)

    # Shuffle the rows so they aren't in perfect order
    df_bank = df_bank.sample(frac=1).reset_index(drop=True)
    df_ledger = df_ledger.sample(frac=1).reset_index(drop=True)

    # Save to CSV
    df_bank.to_csv('bank_statement.csv', index=False)
    df_ledger.to_csv('ledger.csv', index=False)
    print(f"Generated bank_statement.csv ({len(df_bank)} rows) and ledger.csv ({len(df_ledger)} rows).")

if __name__ == "__main__":
    generate_recon_data()