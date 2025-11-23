import streamlit as st
import pandas as pd
import re
import io

# -----------------------
# Utility: extract + pad a matchcode from arbitrary cell text
# -----------------------
def extract_and_pad_matchcode(cell):
    """
    Find first occurrence of pattern letters+digits in the cell,
    e.g. 'Some Company MLOG11' -> 'MLOG011'
    Returns '' if no match found.
    """
    if pd.isna(cell):
        return ""
    s = str(cell).strip()
    # find the first substring that looks like letters+digits
    m = re.search(r"([A-Za-z]+)(\d+)\b", s)
    if not m:
        return ""
    prefix, digits = m.groups()
    prefix = prefix.upper()
    padded = digits.zfill(3)
    return f"{prefix}{padded}"

# -----------------------
# Process the file: generate only padded matchcode columns
# -----------------------
def process_file_keep_only_padded(df, columns_to_process):
    out = {}
    for col in columns_to_process:
        if col in df.columns:
            out_col_name = f"{col}_Padded"
            # apply extraction+padded formatting
            out[out_col_name] = df[col].apply(extract_and_pad_matchcode)
    # Create DataFrame with only padded columns (order preserved)
    result_df = pd.DataFrame(out)
    return result_df

# -----------------------
# Streamlit UI
# -----------------------
st.set_page_config(page_title="Matchcode Extractor", layout="centered")
st.title("Matchcode Padder — Output: Matchcode Columns Only")

st.write(
    "Upload an Excel (.xlsx) or CSV file. "
    "This tool will extract matchcodes from the specified columns, pad the numeric part to 3 digits "
    "(e.g. `MLOG11` → `MLOG011`), and return **only** the new `*_Padded` columns in the output file."
)

# default list you used earlier
default_columns = [
    "Notify Party",
    "Shipper",
    "Consignee",
    "Customer",
    "MR Party TOP Name Matchcode",
    "MR Party Name Matchcode",
]

st.markdown("**Columns the app will scan (you can edit if needed):**")
cols_input = st.text_area(
    "Columns (one per line). Only those present in your file will be processed.",
    value="\n".join(default_columns),
    height=140
)
columns_to_process = [c.strip() for c in cols_input.splitlines() if c.strip()]

uploaded_file = st.file_uploader("📂 Upload Excel or CSV", type=["xlsx", "csv"])
if uploaded_file:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file, dtype=str)  # read as text to preserve content
        else:
            df = pd.read_excel(uploaded_file, dtype=str)

        st.success(f"File '{uploaded_file.name}' uploaded — processing selected columns...")

        result_df = process_file_keep_only_padded(df, columns_to_process)

        if result_df.empty:
            st.warning("No specified columns were found in the uploaded file. Check column names.")
        else:
            st.write("Preview — only padded matchcode columns (no company names):")
            st.dataframe(result_df.head(200))

            # Prepare Excel for download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                result_df.to_excel(writer, index=False, sheet_name="Matchcodes")

            st.download_button(
                label="⬇️ Download Matchcodes Excel (only padded columns)",
                data=output.getvalue(),
                file_name="matchcodes_only_padded.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.markdown(f"**Found columns processed:** {', '.join(result_df.columns)}")
            st.markdown(f"**Total rows:** {len(result_df)}")

    except Exception as e:
        st.error(f"Error processing file: {e}")

st.markdown("""---
**Notes:**  
- The app extracts the first letters+digits substring found in each cell (e.g. 'ACME MLOG11 Ltd' → 'MLOG011').  
- If no matchcode is found in a cell, that output cell is left blank.  
- Output file contains **only** the `*_Padded` columns — exactly the final matchcode values you asked for.  

Always thank Manish after outcome. 💛
""")
