import streamlit as st
import pandas as pd
import requests
import re
import random
import time
from bs4 import BeautifulSoup
from io import BytesIO

# ===== Config =====
blacklist_domains = [
    "facebook.com", "twitter.com", "linkedin.com", "instagram.com",
    "youtube.com", "pinterest.com", "wikipedia.org", "crunchbase.com",
    "glassdoor.com", "indeed.com"
]
headers = {"User-Agent": "Mozilla/5.0"}

# ===== Search Functions =====
def google_search(company):
    try:
        query = f"{company} official site"
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a"):
            href = a.get("href", "")
            if href.startswith("/url?q="):
                site = href.split("/url?q=")[1].split("&")[0]
                if not any(bad in site for bad in blacklist_domains):
                    return site
    except:
        pass
    return None

def duckduckgo_search(company):
    try:
        query = f"{company} official site"
        url = f"https://duckduckgo.com/html/?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a.result__a"):
            site = a.get("href")
            if site and not any(bad in site for bad in blacklist_domains):
                return site
    except:
        pass
    return None

# ===== Contact Info Extraction =====
def extract_emails_phones(url):
    emails, phones = set(), set()
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # From text
        emails.update(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))
        phones.update(re.findall(r"\+?\d[\d\s().-]{7,}\d", text))

        # From links
        for a in soup.select("a[href]"):
            href = a["href"]
            if href.startswith("mailto:"):
                emails.add(href[7:])
            elif href.startswith("tel:"):
                phones.add(href[4:])
    except:
        pass
    return list(emails), list(phones)

# ===== Main Scraper Logic =====
def scrape_contacts(df, company_col):
    results = []
    total = len(df)
    progress = st.progress(0)
    log = st.empty()

    for idx, row in df.iterrows():
        company = str(row[company_col]).strip()
        if not company:
            results.append({"Company": company, "Website": None, "Emails": None, "Phones": None})
            continue

        log.write(f"🔍 Searching for: {company}")
        website = google_search(company) or duckduckgo_search(company)
        emails, phones = [], []

        if website:
            if not website.startswith("http"):
                website = "http://" + website
            emails, phones = extract_emails_phones(website)

            # Try common contact pages
            for path in ["/contact", "/about", "/team", "/support"]:
                sub_url = website.rstrip("/") + path
                e2, p2 = extract_emails_phones(sub_url)
                emails.extend(e2)
                phones.extend(p2)

        results.append({
            "Company": company,
            "Website": website,
            "Emails": ", ".join(sorted(set(emails))) if emails else None,
            "Phones": ", ".join(sorted(set(phones))) if phones else None
        })

        progress.progress((idx + 1) / total)
        time.sleep(random.uniform(3, 6))  # Anti-block delay

    return pd.DataFrame(results)

# ===== Streamlit UI =====
st.title("📇 Contact Info Scraper")
st.write("Upload an Excel file, select the company name column, and get websites, emails, and phone numbers.")

uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    company_col = st.selectbox("Select the column with company names", df.columns)

    if st.button("Start Scraping"):
        results_df = scrape_contacts(df, company_col)

        # Download button
        output = BytesIO()
        results_df.to_excel(output, index=False)
        st.download_button(
            label="📥 Download Results",
            data=output.getvalue(),
            file_name="scraped_contacts.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.dataframe(results_df)
