import streamlit as st
import pandas as pd
import time
import re
import requests
import random
from bs4 import BeautifulSoup
from io import BytesIO

# ---------------------------------------------
# USER AGENTS (for anti-blocking)
# ---------------------------------------------
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile'
]

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(r'\+?\d[\d\s().-]{6,}\d')

# =============================================
#  SEARCH ENGINE FALLBACK SYSTEM
# =============================================

def google_search(company):
    """Uses Google lightweight search API-style fallback."""
    try:
        url = f"https://www.google.com/search?q={company}+official+website"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        r = requests.get(url, headers=headers, timeout=6)
        soup = BeautifulSoup(r.text, "html.parser")
        # find first result link
        a = soup.find("a", href=True)
        if a and "http" in a["href"]:
            return a["href"]
    except:
        return None
    return None


def duckduckgo_search(company):
    """DuckDuckGo JSON API (free, no key needed)."""
    try:
        url = f"https://duckduckgo.com/html/?q={company}+official+website"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        r = requests.get(url, headers=headers, timeout=6)
        soup = BeautifulSoup(r.text, "html.parser")
        result = soup.find("a", {"class": "result__a"}, href=True)
        if result:
            return result["href"]
    except:
        return None
    return None


def bing_search(company):
    """Public scrape of Bing HTML (works without API key)."""
    try:
        url = f"https://www.bing.com/search?q={company}+official+website"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        r = requests.get(url, headers=headers, timeout=6)
        soup = BeautifulSoup(r.text, "html.parser")
        result = soup.find("li", {"class": "b_algo"})
        if result:
            a = result.find("a", href=True)
            if a:
                return a["href"]
    except:
        return None
    return None


def find_best_site(company):
    """3-level fallback search system."""
    for engine in [google_search, duckduckgo_search, bing_search]:
        url = engine(company)
        if url and url.startswith("http"):
            return url
    return None


# =============================================
#  CONTACT EXTRACTION
# =============================================

def extract_contacts(url):
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        r = requests.get(url, headers=headers, timeout=10)
        text = BeautifulSoup(r.text, "html.parser").get_text(" ")

        emails = set(EMAIL_REGEX.findall(text))
        phones = set(PHONE_REGEX.findall(text))

        return ", ".join(sorted(emails)), ", ".join(sorted(phones))
    except:
        return "", ""


# =============================================
#  STREAMLIT UI
# =============================================

st.set_page_config(page_title="Contact Extractor", layout="wide")

st.title("📇 Company Contact Scraper (Block-Proof Edition)")
st.write("Upload a file with **Company Name** in first column. The app finds the official website, extracts email IDs and phone numbers, and gives you an Excel output.")

uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

start = st.button("▶ Start Extraction")
stop = st.button("🛑 Cancel Process")

# stop flag
if "stop_flag" not in st.session_state:
    st.session_state.stop_flag = False

if stop:
    st.session_state.stop_flag = True
    st.warning("Stopping after current company...")


if start and uploaded_file:
    st.session_state.stop_flag = False   # reset
    df = pd.read_excel(uploaded_file)
    companies = df.iloc[:, 0].astype(str).fillna("").tolist()

    df["Website"] = ""
    df["Emails"] = ""
    df["Phones"] = ""

    progress = st.progress(0)
    status = st.empty()

    for i, company in enumerate(companies):

        if st.session_state.stop_flag:
            status.info("🛑 Stopped by user.")
            break

        status.write(f"🔍 Searching: **{company}**")

        # FIND THE OFFICIAL SITE
        site = find_best_site(company)

        if not site:
            df.at[i, "Website"] = "Not Found"
        else:
            df.at[i, "Website"] = site
            emails, phones = extract_contacts(site)
            df.at[i, "Emails"] = emails
            df.at[i, "Phones"] = phones

        progress.progress((i + 1) / len(companies))
        time.sleep(random.uniform(1.5, 3.0))  # anti-block delay

    # DOWNLOAD
    out = BytesIO()
    df.to_excel(out, index=False)
    out.seek(0)

    st.success("✅ Extraction Completed!")
    st.download_button("⬇️ Download Results", out, "Company_Contacts.xlsx")

elif start and not uploaded_file:
    st.error("Please upload an Excel file first.")
