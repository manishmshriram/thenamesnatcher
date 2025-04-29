import streamlit as st
import pandas as pd
import re
import time
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from io import BytesIO

st.set_page_config(page_title="Company Contact Scraper", page_icon="📞", layout="wide")
st.title("📞 Company Contact Scraper")
st.write("Upload an Excel file with company names. This version is **accurate but slow** (~2-3 sec per company).")

def get_company_website(company_name):
    query = f"{company_name} official site"
    try:
        for url in search(query, num=1, stop=1, pause=2):  # Use both num and stop
            return url
    except Exception as e:
        st.error(f"Search error for “{company_name}”: {e}")
    return None

def extract_contacts(url):
    emails, phones = set(), set()
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            text = BeautifulSoup(resp.text, 'html.parser').get_text()
            emails = set(re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text))
            phones = set(re.findall(r'\+?\d{1,4}?[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}', text))
    except Exception as e:
        st.warning(f"Error scraping {url}: {e}")
    return list(emails), list(phones)

def convert_df(df):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return buffer

uploaded = st.file_uploader("📂 Upload your Excel (.xlsx)", type="xlsx")
if uploaded:
    df = pd.read_excel(uploaded)
    col = df.columns[0]
    df['Website'], df['Emails'], df['Phones'] = '', '', ''
    prog = st.progress(0)
    status = st.empty()

    for i, name in enumerate(df[col]):
        status.text(f"🔍 ({i+1}/{len(df)}) Processing: {name}")
        site = get_company_website(name)
        df.at[i, 'Website'] = site if site else 'Not Found'
        if site:
            ems, phs = extract_contacts(site)
            df.at[i, 'Emails'] = ', '.join(ems) if ems else 'No Emails'
            df.at[i, 'Phones'] = ', '.join(phs) if phs else 'No Phones'
        prog.progress((i+1)/len(df))
        time.sleep(2)  # Keep slow delay for accuracy

    status.text("✅ Scraping complete!")
    st.dataframe(df)

    output = convert_df(df)
    st.download_button(
        label="📥 Download Results",
        data=output,
        file_name="Company_Contacts_Accurate.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Please upload an Excel file (.xlsx) to begin.")
