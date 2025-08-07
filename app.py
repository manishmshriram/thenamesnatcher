import streamlit as st
import pandas as pd
import re
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import time
from io import BytesIO
import random

# --- Streamlit Page Setup ---
st.set_page_config(page_title="Contact Scraper", layout="centered")
st.title("📞 Company Contact Scraper")
st.write("Upload an Excel file with **one column** of company names.")

uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

# --- User Agent List ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Linux x86_64)",
]

# --- Helper Functions ---
def get_company_website(company_name):
    query = f"{company_name} official website"
    try:
        for url in search(query, num_results=1):
            return url
    except Exception as e:
        st.warning(f"Google Search failed for '{company_name}': {e}")
        return None

def extract_contacts(url):
    emails, phones = set(), set()
    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            st.warning(f"❌ Blocked or error ({response.status_code}) at {url}")
            return [], []

        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()

        emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
        phones = set(re.findall(r"\+?\d[\d\s().-]{7,}\d", text))

        emails = {e for e in emails if not e.endswith('@example.com')}
        phones = {p for p in phones if len(p) >= 8}
    except Exception as e:
        st.warning(f"Error scraping {url}: {e}")
    return list(emails), list(phones)

# --- Main Logic ---
if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)

        # Validate structure
        if df.shape[1] != 1:
            st.error("❌ Excel file must have **only one column** with company names.")
        else:
            company_column = df.columns[0]
            df["Website"] = ""
            df["Emails"] = ""
            df["Phones"] = ""

            progress = st.progress(0)
            status = st.empty()

            for i, company in enumerate(df[company_column]):
                status.text(f"🔎 {i+1}/{len(df)}: {company}")
                try:
                    website = get_company_website(company)
                    df.at[i, "Website"] = website if website else "Not Found"

                    if website:
                        emails, phones = extract_contacts(website)
                        df.at[i, "Emails"] = ", ".join(emails) if emails else "Not Found"
                        df.at[i, "Phones"] = ", ".join(phones) if phones else "Not Found"
                except Exception as e:
                    st.warning(f"Error on {company}: {e}")
                progress.progress((i + 1) / len(df))
                time.sleep(2)

            status.text("✅ Scraping completed!")
            st.write(df)

            # Excel export
            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                return output.getvalue()

            st.download_button(
                label="📥 Download Results as Excel",
                data=to_excel(df),
                file_name="contacts_scraped.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")
