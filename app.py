import streamlit as st
import pandas as pd
import re
import time
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from io import BytesIO

# ——— Page config & custom CSS ———
st.set_page_config(page_title="Company Contact Scraper", page_icon="📞", layout="wide")
st.markdown("""
    <style>
      .css-18e3th9 {  /* main background */
        background-color: #f5f5f5;
      }
      .stButton>button {  /* green buttons */
        background-color: #28a745;
        color: white;
        border-radius: 8px;
        padding: 0.6em 1.2em;
      }
    </style>
""", unsafe_allow_html=True)

st.title("📞 Company Contact Scraper")
st.write("Upload an Excel file with company names, and I'll fetch sites, emails & phones—slowly, but accurately! 🙌")

# ——— Helper functions ———
def get_company_website(company_name):
    query = f"{company_name} official site"
    try:
        # Updated search function without 'num'
        for url in search(query, stop=1, pause=2):
            return url
    except Exception as e:
        st.error(f"Search error for “{company_name}”: {e}")
    return None

def extract_contacts(url):
    emails, phones = set(), set()
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if resp.status_code == 200:
            text = BeautifulSoup(resp.text, 'html.parser').get_text()
            emails = set(re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text))
            phones = set(re.findall(r'\+?\d{1,4}?[ .\-\(]?\d{2,4}\)?[ .\-\d]{3,8}', text))
    except Exception as e:
        st.warning(f"Error scraping {url}: {e}")
    return list(emails), list(phones)

# ——— File upload & processing ———
uploaded = st.file_uploader("📂 Upload your Excel (.xlsx)", type="xlsx")
if uploaded:
    df = pd.read_excel(uploaded)
    col = df.columns[0]
    df['Website'], df['Emails'], df['Phones'] = '', '', ''
    prog = st.progress(0)
    status = st.empty()

    for i, name in enumerate(df[col]):
        status.text(f"⏳ ({i+1}/{len(df)}) {name}")
        site = get_company_website(name)
        df.at[i,'Website'] = site or 'Not Found'
        if site:
            ems, phs = extract_contacts(site)
            df.at[i,'Emails'] = ', '.join(ems) or 'No Emails'
            df.at[i,'Phones'] = ', '.join(phs) or 'No Phones'
        prog.progress((i+1)/len(df))
        time.sleep(5)  # slow it down on purpose

    status.text("✅ Scraping complete—enjoy your data!")
    st.dataframe(df)

    # ——— Prepare download ———
    output = convert_df(df)

    st.download_button(
        label="📥 Download Results",
        data=output,
        file_name="Company_Contacts.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # ——— Humorous sign‑off ———
    st.markdown("""
    ---
    **Download complete!**  
    👨‍💻 Manish is a Genius—no cap!  
    Now go forth, slay those leads, and remember to thank Manish! 🎉
    """)

else:
    st.info("Please upload an Excel file (.xlsx) to begin scraping.")
