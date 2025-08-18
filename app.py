import streamlit as st
import pandas as pd
import re
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import time
import random
from io import BytesIO

# ---- SESSION STATE FOR STOP FLAG ----
if "stop_flag" not in st.session_state:
    st.session_state.stop_flag = False

# ---- STOP FUNCTION ----
def stop_search():
    st.session_state.stop_flag = True
    st.warning("⛔ Search stopped by user. Partial results will be available for download.")

# ---- CONTACT SCRAPER ----
def extract_contacts(company):
    emails, phones = set(), set()
    try:
        urls = search(f"{company} Contact OR About", num_results=3)  # 3 links for balance
        for url in urls:
            if st.session_state.stop_flag:
                break
            try:
                response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if response.status_code != 200:
                    continue
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text(" ", strip=True)

                # Extract emails
                for match in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
                    emails.add(match)

                # Extract phone numbers
                for match in re.findall(r"\+?\d[\d\s\-\(\)]{7,15}", text):
                    phones.add(match.strip())
            except Exception:
                continue
    except Exception as e:
        return [], [], str(e)

    return list(emails), list(phones), None

# ---- MAIN FUNCTION ----
def run_scraper(uploaded_file):
    st.session_state.stop_flag = False

    df = pd.read_excel(uploaded_file)
    results = []

    progress = st.progress(0)
    status_text = st.empty()
    total = len(df)

    for idx, row in df.iterrows():
        if st.session_state.stop_flag:
            break

        company = str(row[0])
        status_text.write(f"🔎 Processing row {idx+1} of {total}: **{company}**")

        emails, phones, error = extract_contacts(company)

        results.append({
            "Row": idx + 1,
            "Company": company,
            "Emails": ", ".join(emails) if emails else "Not Found",
            "Phones": ", ".join(phones) if phones else "Not Found",
            "Error": error if error else ""
        })

        # Adaptive delay (between 3-6 seconds)
        time.sleep(random.uniform(3, 6))

        progress.progress((idx + 1) / total)

    return pd.DataFrame(results)

# ---- STREAMLIT UI ----
st.title("📊 Professional Contact Scraper")

uploaded_file = st.file_uploader("Upload Excel File (Company Names in first column)", type=["xlsx"])

if uploaded_file:
    start_button = st.button("▶ Start Extraction")
    stop_button = st.button("⏹ Stop Extraction", on_click=stop_search)

    if start_button:
        with st.spinner("Extracting contacts... Please wait."):
            result_df = run_scraper(uploaded_file)

            st.write(f"**✅ Processed Rows: {len(result_df)}**")

            # Auto-download Excel file
            output = BytesIO()
            result_df.to_excel(output, index=False)
            st.download_button(
                label="📥 Download Results",
                data=output.getvalue(),
                file_name="contact_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            if st.session_state.stop_flag:
                st.warning("⚠️ Process stopped early. Download contains partial results.")
            else:
                st.success("✅ Extraction Completed!")
