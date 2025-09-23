import streamlit as st
import pandas as pd
import requests
import re
import time
from bs4 import BeautifulSoup
from googlesearch import search

# --- Function to extract contacts from a page ---
def extract_contacts(url):
    emails, phones = set(), set()
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(" ", strip=True)

            # Regex for emails
            emails.update(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))

            # Regex for phone numbers (international format friendly)
            phones.update(re.findall(r"\+?\d[\d\s().-]{7,}\d", text))
    except Exception as e:
        pass
    return list(emails), list(phones)

# --- Function to scrape a company ---
def scrape_company(company_name, delay=5):
    results = []
    query = f"{company_name} contact OR about"
    
    # Search top 8 results
    for i, url in enumerate(search(query, num_results=8)):
        time.sleep(delay)  # Slow down for accuracy
        emails, phones = extract_contacts(url)
        if emails or phones:
            results.append({"Company": company_name, "URL": url, "Emails": ", ".join(emails), "Phones": ", ".join(phones)})
    return results

# --- Streamlit UI ---
st.title("📞 Company Contact Finder (Accurate Mode)")
company = st.text_input("Enter Company Name:")

if st.button("Search"):
    if company.strip():
        st.info(f"🔍 Searching for '{company}' ... Please wait, it may take ~30–60 sec")
        data = scrape_company(company, delay=5)  # 5 sec delay for accuracy
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df)

            # Download option
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download Results as CSV", data=csv, file_name="contacts.csv", mime="text/csv")
        else:
            st.error("No contact info found. Try a different company.")
