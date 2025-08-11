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
from urllib.parse import urljoin, urlparse

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Streamlit Page Config ---
st.set_page_config(page_title="Contact Scraper", layout="centered")
st.title("📞 Company Contact Scraper")
st.write("Upload an Excel file and select the column containing company names.")

uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

# --- User Agents Pool ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/94.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36"
]

# --- Retry helper ---
def retry_request(func, *args, retries=3, delay=5, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.warning(f"Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
    return None

# --- Get company website ---
def get_company_website(company_name):
    query = f"{company_name} official site"
    try:
        results = retry_request(search, query, num_results=3)
        if results:
            for url in results:
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    return url
        return None
    except Exception as e:
        logging.warning(f"Website retrieval error for '{company_name}': {e}")
        return None

# --- Extract emails & phones from a page ---
def extract_contacts_from_url(url):
    emails, phones = set(), set()
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    }
    def make_request():
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp

    response = retry_request(make_request)
    if not response:
        return [], []

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text()

    emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
    phones = set(re.findall(r"\+?\d[\d\s().-]{7,}\d", text))

    # Filter out generic emails and short numbers
    emails = {e for e in emails if not e.lower().endswith(("@example.com", "@test.com", "@email.com"))}
    phones = {p for p in phones if len(re.sub(r"\D", "", p)) >= 8}

    return list(emails), list(phones)

# --- Try main + contact + about pages ---
def get_full_contacts(website):
    all_emails, all_phones = set(), set()
    candidate_pages = [website]
    for path in ["/contact", "/about", "/contact-us", "/about-us"]:
        candidate_pages.append(urljoin(website, path))

    for page in candidate_pages:
        emails, phones = extract_contacts_from_url(page)
        all_emails.update(emails)
        all_phones.update(phones)

    return list(all_emails), list(all_phones)

# --- Main ---
if uploaded_file:
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
                        emails, phones = get_full_contacts(website)
                        result_df.at[i, "Website"] = website
                        result_df.at[i, "Emails"] = ", ".join(emails) if emails else "Not Found"
                        result_df.at[i, "Phones"] = ", ".join(phones) if phones else "Not Found"
                    else:
                        result_df.at[i, "Website"] = "Not Found"
                        result_df.at[i, "Emails"] = "Not Found"
                        result_df.at[i, "Phones"] = "Not Found"
                except Exception as e:
                    logging.error(f"Error scraping {company}: {e}")
                    result_df.at[i, "Website"] = "Error"
                    result_df.at[i, "Emails"] = "Error"
                    result_df.at[i, "Phones"] = "Error"

                progress.progress((i + 1) / total)

                # Delay to prevent blocking
                time.sleep(random.uniform(5, 10))

            status.text("✅ Scraping completed!")

            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False)
                return output.getvalue()

            file_name = f"{col_option}_contacts_scraped.xlsx"
            st.download_button(
                label="📥 Download Excel",
                data=to_excel(result_df),
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        logging.error(f"Unexpected error during scraping: {e}")
        st.error(f"❌ Unexpected error: {e}")
