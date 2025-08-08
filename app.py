import streamlit as st
import pandas as pd
import re
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import time
import random
import logging
from io import BytesIO

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# --- Streamlit Setup ---
st.set_page_config(page_title="Contact Scraper", layout="centered")
st.title("📞 Company Contact Scraper")
st.write("Upload an Excel file and select the column containing company names.")

uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

# --- User Agent Pool ---
USER_AGENTS = [
    # Expanded list for more variety
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/94.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36",
    # Add more if desired
]

# --- Retry Decorator for Requests ---
def retry_request(func, *args, retries=3, delay=10, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.warning(f"Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
    return None

# --- Scraping Functions ---
def get_company_website(company_name):
    query = f"{company_name} official website"
    try:
        # Using retry wrapper around search to handle transient errors
        results = retry_request(search, query, num_results=1)
        if results:
            for url in results:
                logging.info(f"Found website for {company_name}: {url}")
                return url
        return None
    except Exception as e:
        logging.warning(f"Website retrieval error for '{company_name}': {e}")
        return None

def extract_contacts(url):
    emails, phones = set(), set()
    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
        }
        # Retry requests.get wrapped in retry_request for robustness
        def make_request():
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp

        response = retry_request(make_request)
        if response is None:
            logging.warning(f"Failed to get a valid response from {url}")
            return [], []

        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()

        # Regex for emails and phones with basic filters
        emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
        phones = set(re.findall(r"\+?\d[\d\s().-]{7,}\d", text))

        # Exclude generic emails and obviously invalid phones
        emails = {e for e in emails if not e.endswith('@example.com')}
        phones = {p for p in phones if len(p) >= 8}
    except Exception as e:
        logging.warning(f"Contact extraction error for '{url}': {e}")
        return [], []
    return list(emails), list(phones)

# --- Main Logic ---
if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        col_option = st.selectbox("Select the column with company names:", df.columns)

        if st.button("Start Scraping"):
            result_df = df.copy()
            result_df["Website"] = ""
            result_df["Emails"] = ""
            result_df["Phones"] = ""

            progress = st.progress(0)
            status = st.empty()

            total = len(df)
            for i, company in enumerate(result_df[col_option]):
                status.text(f"🔎 {i+1}/{total}: {company}")
                logging.info(f"Processing [{i+1}/{total}]: {company}")
                try:
                    website = get_company_website(company)
                    if website:
                        logging.info(f"Scraping contacts from {website}")
                        emails, phones = extract_contacts(website)
                        result_df.at[i, "Website"] = website
                        result_df.at[i, "Emails"] = ", ".join(emails) if emails else "Not Found"
                        result_df.at[i, "Phones"] = ", ".join(phones) if phones else "Not Found"
                    else:
                        logging.info(f"Website not found for {company}")
                        result_df.at[i, "Website"] = "Not Found"
                        result_df.at[i, "Emails"] = "Not Found"
                        result_df.at[i, "Phones"] = "Not Found"
                except Exception as e:
                    logging.error(f"Error scraping {company}: {e}")
                    result_df.at[i, "Website"] = "Error"
                    result_df.at[i, "Emails"] = "Error"
                    result_df.at[i, "Phones"] = "Error"

                progress.progress((i + 1) / total)

                # Random delay between 10 and 60 seconds after each company
                sleep_time = random.randint(5, 10)
                logging.info(f"Sleeping for {sleep_time} seconds.")
                time.sleep(sleep_time)

            status.text("✅ Scraping completed!")
            st.write(result_df)

            # Export to Excel helper
            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                return output.getvalue()

            file_name = f"{col_option}_contacts_scraped.xlsx"

            st.success("✅ Ready for download!")
            st.download_button(
                label="📥 Download Excel",
                data=to_excel(result_df),
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        logging.error(f"Unexpected error during scraping: {e}")
        st.error(f"❌ Unexpected error: {e}")
