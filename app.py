import streamlit as st
import pandas as pd
import os
import subprocess
import sys
from dotenv import load_dotenv # <-- Add this

load_dotenv()
# 1. Page Configuration
st.set_page_config(page_title="ReconBot Dashboard", page_icon="📊", layout="wide")
st.title("📊 ReconBot: AI Financial Reconciliation")
st.markdown("Automated clearing for bank and ledger discrepancies.")
st.sidebar.header("⚙️ Pipeline Controls")
if st.sidebar.button("🚀 Run Full Reconciliation"):
    if not os.getenv("GROQ_API_KEY"):
        st.sidebar.error("❌ GROQ_API_KEY is missing. Please set it in your .env file or system environment.")
    else:
        try:
            with st.spinner("Running Pass 1 & 2 (Deterministic & Fuzzy)..."):
                # sys.executable guarantees it uses the exact same Python environment as Streamlit
                subprocess.run([sys.executable, "match_engine.py"], check=True, capture_output=True, text=True)
                
            with st.spinner("Running Pass 3 (LLM Reasoning)..."):
                subprocess.run([sys.executable, "pass3_engine.py"], check=True, capture_output=True, text=True)
                
            st.sidebar.success("✅ Pipeline complete!")
            st.rerun() # Reloads the dashboard with new CSV data
            
        except subprocess.CalledProcessError as e:
            # If a script crashes, catch the error and print it cleanly in the UI
            st.sidebar.error(f"❌ Script crashed: {e.cmd[1]}")
            st.sidebar.code(e.stderr) # Prints the exact Python traceback to the dashboard

# 2. Helper function to load data safely
def load_data(file_name):
    if os.path.exists(file_name) and os.path.getsize(file_name) > 0:
        return pd.read_csv(file_name)
    return pd.DataFrame()

# Load all outputs
st1_df = load_data("matches_stage1.csv")
st2_df = load_data("matches_stage2.csv")
exc_df = load_data("exceptions.csv")

# 3. Calculate Global Metrics
total_st1 = len(st1_df)
total_st2 = len(st2_df)
total_matches = total_st1 + total_st2
total_exceptions = len(exc_df)
total_transactions = total_matches + total_exceptions

match_rate = (total_matches / total_transactions * 100) if total_transactions > 0 else 0

# 4. Top Level KPI Dashboard
st.subheader("Live Reconciliation Status")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Transactions", total_transactions)
col2.metric("Rule-Based Matches (Pass 1 & 2)", total_st1)
col3.metric("AI Matches (Pass 3)", total_st2)
col4.metric("Exceptions (Manual Review)", total_exceptions)

# Match Rate Progress Bar
st.progress(match_rate / 100)
st.caption(f"**Overall Match Rate:** {match_rate:.1f}%")

st.divider()

# 5. Data Tables
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("🤖 AI Rescued Matches (Pass 3)")
    st.markdown("Transactions matched via LLM semantic reasoning.")
    if not st2_df.empty:
        st.dataframe(st2_df, use_container_width=True, hide_index=True)
    else:
        st.info("No AI matches found.")

with col_right:
    st.subheader("⚠️ Exceptions Queue")
    st.markdown("Transactions requiring human intervention.")
    if not exc_df.empty:
        st.dataframe(exc_df, use_container_width=True, hide_index=True)
    else:
        st.success("Zero exceptions! All transactions reconciled.")