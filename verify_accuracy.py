import pandas as pd
import os

def run_verification():
    if not os.path.exists("ground_truth.csv"):
        print("Run generate_data.py first to create ground_truth.csv")
        return

    gt_df = pd.read_csv("ground_truth.csv")
    
    m1 = pd.read_csv("matches_stage1.csv") if os.path.exists("matches_stage1.csv") else pd.DataFrame()
    m2 = pd.read_csv("matches_stage2.csv") if os.path.exists("matches_stage2.csv") else pd.DataFrame()
    
    all_matches = pd.concat([m1, m2], ignore_index=True) if not m1.empty or not m2.empty else pd.DataFrame(columns=['txn_id', 'ledger_id'])
    
    # Merge truth with predicted matches
    eval_df = pd.merge(gt_df, all_matches[['txn_id', 'ledger_id']], on='txn_id', how='left')
    
    tp = len(eval_df[(eval_df['ledger_id'].notna()) & (eval_df['ledger_id'] == eval_df['true_ledger_id'])])
    fp = len(eval_df[(eval_df['ledger_id'].notna()) & (eval_df['ledger_id'] != eval_df['true_ledger_id'])])
    fn = len(eval_df[(eval_df['true_ledger_id'].notna()) & (eval_df['ledger_id'] != eval_df['true_ledger_id'])])
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    
    print("\n--- PIPELINE ACCURACY AUDIT ---")
    print(f"True Positives (TP): {tp}")
    print(f"False Positives (FP): {fp}")
    print(f"False Negatives (FN): {fn}")
    print(f"Precision Score:     {precision:.2%}\n")

if __name__ == "__main__":
    run_verification()