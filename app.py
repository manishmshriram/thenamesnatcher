import streamlit as st
import pandas as pd
import requests
import re
from bs4 import BeautifulSoup
from googlesearch import search
import random
import time

# --- Slower, safer scraping function ---
def scrape_contacts(company_name):
    contacts = []
    try:
        for url in search(f"{company_name} contact OR about", num_results=5):
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, "html.parser")

                text = soup.get_text()
                emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
                phones = re.findall(r"\+?\d[\d\s\-\(\)]{7,}\d", text)

                for email in emails:
                    contacts.append({
                        "Company": company_name,
                        "Type": "Email",
                        "Value": email,
                        "Source": url
                    })
                for phone in phones:
                    contacts.append({
                        "Company": company_name,
                        "Type": "Phone",
                        "Value": phone,
                        "Source": url
                    })

            except Exception:
                continue

            # --- Slowdown to avoid blocking (5–15 sec random sleep) ---
            time.sleep(random.randint(5, 15))

    except Exception:
        pass
    return contacts


# --- Streamlit UI ---
st.title("📞 Contact Scraper")
st.write("Upload an Excel file with company names (first column). The app will fetch emails and phone numbers.")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
    company_column = df.columns[0]

    results = []
   progress_text = st.empty()
progress_bar = st.progress(0)

for i, company in enumerate(df[company_column]):
    progress_text.text(f"🔍 Processing {i+1}/{len(df)}: {company}")
    contacts = scrape_contacts(company)
    results.extend(contacts)
    progress_bar.progress((i + 1) / len(df))


    if results:
        output_df = pd.DataFrame(results)
        st.success("✅ Scraping completed!")

        st.dataframe(output_df)

        # --- Download button ---
        output_file = "Company_Contacts.xlsx"
        output_df.to_excel(output_file, index=False)
        with open(output_file, "rb") as f:
            st.download_button("📥 Download Excel", f, file_name=output_file)
