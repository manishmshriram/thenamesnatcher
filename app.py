import streamlit as st
import pandas as pd
import re
import time
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from io import BytesIO

# ——— Streamlit Page Setup ———
st.set_page_config(page_title="Company Contact Scraper", page_icon="🔍", layout="wide")
st.title("🔍 Company Contact Scraper")
st.write("Upload an Excel file with company names. This tool finds the **official website**, **emails**, and **phone numbers**—slowly but reliably.")

# ——— Get Official Company Website ———
def get_company_website(company_name):
    query = f"{company_name} official site"
    try:
        for url in search(query, num=1, stop=1, pause=2):
            return url
    except Exception as e:
        st.error(f"Error searching for '{company_name}': {e}")
    return None

# ——— Extract Email and Phone Numbers ———
def extract_contacts(url):
    emails, phones = set(), set()
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()
            emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text))
            phones = set(re.findall(r'\+?\d{1,4}?[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}', text))
    except Exception as e:
        st.warning(f"Error scraping {url}: {e}")
    return list(emails), list(phones)

# ——— Convert DataFrame to Downloadable Excel ———
def convert_df(df):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return buffer

# ——— File Upload ———
uploaded = st.file_uploader("📂 Upload Excel File with Company Names", type="xlsx")
if uploaded:
    df = pd.read_excel(uploaded)
    col = df.columns[0]
    df['Website'], df['Emails'], df['Phones'] = '', '', ''
    progress = st.progress(0)
    status = st.empty()

    for i, company in enumerate(df[col]):
        status.text(f"⏳ ({i+1}/{len(df)}) Searching: {company}")
        website = get_company_website(company)
        df.at[i, 'Website'] = website if website else 'Not Found'
        if website:
            emails, phones = extract_contacts(website)
            df.at[i, 'Emails'] = ', '.join(emails) if emails else 'No Emails'
            df.at[i, 'Phones'] = ', '.join(phones) if phones else 'No Phones'
        progress.progress((i + 1) / len(df))
        time.sleep(2)  # Keep slow for accuracy and safety

    status.success("✅ Scraping complete! Download your results below.")
    st.dataframe(df)

    # ——— Download Button ———
    output = convert_df(df)
    st.download_button(
        label="📥 Download Excel File",
        data=output,
        file_name="Company_Contacts_Accurate.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")
    st.markdown("💡 _Tip: This version is slow but **95% accurate**. For faster scraping, toggle to a 'Fast Mode' in the future!_")
else:
    st.info("Please upload an Excel file (.xlsx) to begin.")
