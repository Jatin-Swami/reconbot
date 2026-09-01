import pandas as pd
from rapidfuzz import fuzz
from datetime import datetime, timedelta
import random
import time


def _run_pass1(bank_df, ledger_df):
    """Same unambiguous-only exact-match logic as match_engine.py — kept in sync
    so this benchmark measures the real pipeline, not a simplified stand-in."""
    exact = pd.merge(bank_df, ledger_df, left_on=['reference_id', 'amount', 'date'],
                      right_on=['invoice_id', 'amount', 'date'], how='inner')
    txn_id_counts = exact['txn_id'].value_counts()
    ledger_id_counts = exact['ledger_id'].value_counts()
    unambiguous = exact['txn_id'].map(txn_id_counts).eq(1) & exact['ledger_id'].map(ledger_id_counts).eq(1)
    exact = exact[unambiguous]

    matched_t = set(exact['txn_id'])
    matched_l = set(exact['ledger_id'])
    ubank = bank_df[~bank_df['txn_id'].isin(matched_t)]
    uledg = ledger_df[~ledger_df['ledger_id'].isin(matched_l)]
    return matched_t, matched_l, ubank, uledg


def _run_pass2_blocked(ubank, uledg):
    """Date-bucketed blocking version (what match_engine.py actually runs)."""
    ledger_date_index = {}
    for l_row in uledg.itertuples():
        ledger_date_index.setdefault(l_row.date, []).append(l_row)

    new_t, new_l = set(), set()
    for b in ubank.itertuples():
        candidate_dates = [b.date + timedelta(days=d) for d in range(-3, 4)]
        candidates = [l for d in candidate_dates for l in ledger_date_index.get(d, [])]
        for l in candidates:
            if l.ledger_id in new_l:
                continue
            if abs(b.amount - l.amount) / l.amount <= 0.01 and abs((b.date - l.date).days) <= 3:
                if fuzz.token_set_ratio(str(b.description), f"{str(l.party_name)} {str(l.description)}") >= 70:
                    new_t.add(b.txn_id)
                    new_l.add(l.ledger_id)
                    break
    return new_t, new_l


def _run_pass2_naive(ubank, uledg):
    """Unblocked O(n*m) cross-product version, kept ONLY to honestly demonstrate
    why blocking matters. Not used by the real pipeline."""
    new_t, new_l = set(), set()
    for b in ubank.itertuples():
        for l in uledg.itertuples():
            if l.ledger_id in new_l:
                continue
            if abs(b.amount - l.amount) / l.amount <= 0.01 and abs((b.date - l.date).days) <= 3:
                if fuzz.token_set_ratio(str(b.description), f"{str(l.party_name)} {str(l.description)}") >= 70:
                    new_t.add(b.txn_id)
                    new_l.add(l.ledger_id)
                    break
    return new_t, new_l


def _generate_dataset(n_exact, n_fuzzy, seed=42):
    """
    Vary amount and description per row (via a per-row varying suffix/cents)
    so every bank row has exactly one valid ledger partner within the date
    window -- matching how real transaction data behaves (unique amounts to
    the cent, unique invoice/party references). This matters for the
    benchmark's correctness, not just its realism: if every row were
    interchangeable (identical amount + description across the whole
    dataset), the greedy "first candidate that satisfies all 3 rules, then
    break" matching strategy becomes iteration-order-dependent -- a different
    scan order can leave a different subset of rows stranded even though a
    different assignment would have matched everyone. That's a property of
    the greedy algorithm itself (confirmed present in the original nested-loop
    version too, under row reordering), not something blocking introduces,
    but it's not something a benchmark should paper over with unrealistic
    duplicate data either.
    """
    random.seed(seed)
    start_date = datetime(2023, 10, 1)
    b_recs, l_recs = [], []

    for i in range(n_exact):
        d_str = (start_date + timedelta(days=random.randint(0, 30))).strftime('%Y-%m-%d')
        amt = round(100.0 + (i % 5000) / 100, 2)  # unique-ish amount per row
        b_recs.append({'txn_id': f"T-{i}", 'date': d_str, 'amount': amt, 'description': f"Payment A{i}", 'reference_id': f"I-{i}"})
        l_recs.append({'ledger_id': f"L-{i}", 'date': d_str, 'amount': amt, 'party_name': f"Company_{i}", 'description': "Vendor payment", 'invoice_id': f"I-{i}"})

    for i in range(n_exact, n_exact + n_fuzzy):
        d_str = (start_date + timedelta(days=random.randint(0, 30))).strftime('%Y-%m-%d')
        amt = round(100.0 + (i % 5000) / 100, 2)
        bank_amt = round(amt * 1.005, 2)  # within the 1% fuzzy tolerance, still unique per row
        b_recs.append({'txn_id': f"T-{i}", 'date': d_str, 'amount': bank_amt, 'description': f"ACH Transfer Fuzz_Provider_{i}", 'reference_id': None})
        l_recs.append({'ledger_id': f"L-{i}", 'date': d_str, 'amount': amt, 'party_name': f"Fuzz_Provider_{i}", 'description': "Consulting services", 'invoice_id': f"I-{i}"})

    bank_df = pd.DataFrame(b_recs)
    ledger_df = pd.DataFrame(l_recs)
    bank_df['date'] = pd.to_datetime(bank_df['date'])
    ledger_df['date'] = pd.to_datetime(ledger_df['date'])
    return bank_df, ledger_df


def run_benchmark():
    # -----------------------------------------------------------------
    # Scenario 1: "happy path" -- mirrors real-world reconciliation where
    # most transactions exact-match (90% here), matching generate_data.py's
    # proportions. This is the realistic end-to-end throughput number.
    # -----------------------------------------------------------------
    print("=" * 60)
    print("SCENARIO 1: Realistic mix (9,000 exact / 1,000 fuzzy, n=10,000)")
    print("=" * 60)
    bank_df, ledger_df = _generate_dataset(n_exact=9000, n_fuzzy=1000)

    start_time = time.time()
    matched_t, matched_l, ubank, uledg = _run_pass1(bank_df, ledger_df)
    new_t, new_l = _run_pass2_blocked(ubank, uledg)
    total_time = time.time() - start_time
    total_matches = len(matched_t) + len(new_t)

    print(f"Total Matches:    {total_matches} / {len(bank_df)}")
    print(f"Total Wall Time:  {total_time:.2f} seconds")
    print(f"Throughput Speed: {len(bank_df) / total_time:.0f} rows/second")

    # -----------------------------------------------------------------
    # Scenario 2: stress test -- the pool that actually reaches Pass 2 is
    # large (2,000 unmatched bank x 2,000 unmatched ledger = 4,000,000
    # possible pairs). This is the scenario the original benchmark never
    # tested, and where an unblocked nested loop would visibly buckle.
    # Blocked vs. naive are run back-to-back on the SAME data so the
    # speedup is a real, reproducible number, not a claim.
    # -----------------------------------------------------------------
    print()
    print("=" * 60)
    print("SCENARIO 2: Stress test -- large unmatched pool (n=2,000, all fuzzy)")
    print("=" * 60)
    bank_df2, ledger_df2 = _generate_dataset(n_exact=0, n_fuzzy=2000)
    _, _, ubank2, uledg2 = _run_pass1(bank_df2, ledger_df2)  # everything falls through to Pass 2

    t0 = time.time()
    blocked_t, blocked_l = _run_pass2_blocked(ubank2, uledg2)
    blocked_time = time.time() - t0

    t0 = time.time()
    naive_t, naive_l = _run_pass2_naive(ubank2, uledg2)
    naive_time = time.time() - t0

    assert blocked_t == naive_t and blocked_l == naive_l, "Blocking changed match results — bug!"

    print(f"Unmatched pool:      {len(ubank2)} bank x {len(uledg2)} ledger = {len(ubank2) * len(uledg2):,} possible pairs")
    print(f"Naive O(n*m) time:   {naive_time:.2f}s")
    print(f"Blocked (date-index) time: {blocked_time:.2f}s")
    print(f"Speedup:             {naive_time / blocked_time:.1f}x  (results identical: {len(blocked_t)} matches either way)")


if __name__ == "__main__":
    run_benchmark()