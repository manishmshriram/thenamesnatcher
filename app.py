# app.py
import streamlit as st
import pandas as pd
import time
from scraper import get_company_website, extract_contacts  # Your Selenium-based functions

st.title("🔍 Company Contact Info Scraper")

uploaded_file = st.file_uploader("📤 Upload Excel File with Company Names", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.write("📄 Preview of Uploaded Data:")
    st.dataframe(df.head())

    if st.button("🚀 Start Scraping"):
        df['Website'] = ''
        df['Emails'] = ''
        df['Phones'] = ''

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, company in enumerate(df[df.columns[0]]):
            status_text.text(f"🔄 Processing {i+1}/{len(df)}: {company}")
            website = get_company_website(company)
            df.at[i, 'Website'] = website if website else 'Not Found'
            if website:
                emails, phones = extract_contacts(website)
                df.at[i, 'Emails'] = ', '.join(emails)
                df.at[i, 'Phones'] = ', '.join(phones)
            progress_bar.progress((i + 1) / len(df))
            time.sleep(2)

        st.success("✅ Scraping Complete!")
        st.dataframe(df)
        df.to_excel("Company_Contacts.xlsx", index=False)
        with open("Company_Contacts.xlsx", "rb") as f:
            st.download_button("📥 Download Results", f, file_name="Company_Contacts.xlsx")
