import streamlit as st
import pandas as pd
from extractor import extract_contacts_bulk

st.set_page_config(page_title="Lead Extractor", layout="wide")

st.title("Lead Creation: Company Website & Contact Extractor")

uploaded_file = st.file_uploader("Upload CSV/Excel with 'Company' and optional 'Country' columns", type=['csv','xlsx'])
batch_size = st.number_input('How many companies per batch?', min_value=1, max_value=20, value=10, step=1)
delay = st.slider('Delay between requests (seconds):', 2, 10, 4, 1)

if uploaded_file:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('csv') else pd.read_excel(uploaded_file)
    st.write("First 5 companies:", df.head())
    run = st.button("Start Extraction")
    if run:
        results = extract_contacts_bulk(df, batch_size=batch_size, delay=delay)
        st.success("Extraction complete!")
        st.dataframe(results)
        st.download_button("Download CSV", results.to_csv(index=False), "results.csv")
