import streamlit as st
import pandas as pd
import re
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import time
import random
from io import BytesIO

# ---- GLOBAL VARIABLES ----
stop_flag = False

# ---- STOP FUNCTION ----
def stop_search():
    global stop_flag
    stop_flag = True
    st.warning("⛔ Search stopped by user.")

# ---- CONTACT SCRAPER ----
def extract_contacts(company):
    emails, phones = set(), set()
    try:
        urls = search(f"{company} Contact OR About", num_results=3)  # 3 links for balance
        for url in urls:
            if stop_flag:
                break
            try:
                response = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
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
    global stop_flag
    stop_flag = False

    df = pd.read_excel(uploaded_file)
    results = []

    progress = st.progress(0)
    total = len(df)

    for idx, row in df.iterrows():
        if stop_flag:
            break

        company = str(row[0])
        emails, phones, error = extract_contacts(company)

        results.append({
            "Company": company,
            "Emails": ", ".join(emails) if emails else "Not Found",
            "Phones": ", ".join(phones) if phones else "Not Found",
            "Error": error if error else ""
        })

        # Adaptive delay (between 3-6 seconds)
        time.sleep(random.uniform(3, 6))

        progress.progress((idx+1)/total)

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

            # Auto-download Excel file
            output = BytesIO()
            result_df.to_excel(output, index=False)
            st.download_button(
                label="📥 Download Results",
                data=output.getvalue(),
                file_name="contact_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.success("✅ Extraction Completed!")
