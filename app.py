import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import urllib.parse
import io

# -------------------- Helper Functions --------------------

def google_search(company_name):
    query = f"{company_name} contact site:.com"
    url = f"https://duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        time.sleep(5)
        soup = BeautifulSoup(res.text, "html.parser")
        links = [a['href'] for a in soup.select('.result__a') if 'http' in a['href']]
        return links
    except:
        return []

def extract_contacts(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        res = requests.get(url, headers=headers, timeout=15)
        time.sleep(5)
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text()

        emails = list(set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)))
        phones = list(set(re.findall(r"\+?\d[\d\s().-]{7,}\d", text)))
        return emails, phones
    except:
        return [], []

# -------------------- Streamlit UI --------------------

st.set_page_config(page_title="Contact Finder", layout="centered")
st.title("📄 Excel Contact Scraper - Slow & Accurate")
st.markdown("Upload an Excel file with a column named `Company`. I’ll find emails and phone numbers for each company. Be patient — it takes time for good results (5–10 secs per company).")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        if "Company" not in df.columns:
            st.error("Excel must have a column named 'Company'.")
        else:
            if st.button("🔍 Start Scraping"):
                result_data = []

                for index, row in df.iterrows():
                    company = str(row["Company"])
                    st.info(f"Searching for: **{company}**")

                    links = google_search(company)
                    emails_found = []
                    phones_found = []

                    for link in links[:3]:
                        emails, phones = extract_contacts(link)
                        emails_found.extend(emails)
                        phones_found.extend(phones)
                        time.sleep(5)

                    emails_found = list(set(emails_found))
                    phones_found = list(set(phones_found))

                    result_data.append({
                        "Company": company,
                        "Emails": ", ".join(emails_found) if emails_found else "Not Found",
                        "Phone Numbers": ", ".join(phones_found) if phones_found else "Not Found"
                    })

                result_df = pd.DataFrame(result_data)
                st.success("✅ Scraping Complete!")
                st.dataframe(result_df)

                # Downloadable output
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    result_df.to_excel(writer, index=False, sheet_name='Results')
                    writer.save()
                    st.download_button(
                        label="📥 Download Results as Excel",
                        data=output.getvalue(),
                        file_name='contact_results.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
    except Exception as e:
        st.error(f"Error reading file: {e}")
