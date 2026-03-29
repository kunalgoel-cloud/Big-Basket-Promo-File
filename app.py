import streamlit as st
import pandas as pd
import calendar
from datetime import date
import io

st.set_page_config(page_title="BigBasket Promo Architect", layout="wide")

st.title("📦 BigBasket Promo Portal Generator")
st.markdown("Automated promo file generation based on inventory health (STR/DOC) and date buckets.")

# --- 1. Inputs: Time and Prices ---
with st.sidebar:
    st.header("Configuration")
    target_year = st.selectbox("Year", [2025, 2026], index=1)
    target_month = st.selectbox("Month", list(range(1, 13)), format_func=lambda x: calendar.month_name[x])
    
    st.divider()
    st.subheader("Classification Rules")
    st.caption("BAU: STR > 20%, DOC < 90")
    st.caption("Liquidation: STR < 20%, DOC > 90")
    st.caption("SVD: STR > 20%, DOC > 90")
    st.caption("Weekend: STR < 20%, DOC < 90")

# --- 2. File Uploads ---
col1, col2 = st.columns(2)
with col1:
    inv_file = st.file_uploader("Upload Inventory Metrics (STR/DOC)", type=['csv', 'xlsx'])
with col2:
    price_file = st.file_uploader("Upload Target Prices (SKU ID, BAU, Weekend, SVD, Liq)", type=['csv', 'xlsx'])

if inv_file and price_file:
    # Load Data
    df_inv = pd.read_csv(inv_file) if inv_file.name.endswith('csv') else pd.read_excel(inv_file)
    df_price = pd.read_csv(price_file) if price_file.name.endswith('csv') else pd.read_excel(price_file)
    
    # Pre-processing
    # Ensure STR is decimal
    if df_inv['str'].max() > 1:
        df_inv['str'] = df_inv['str'] / 100

    def classify(row):
        if row['str'] > 0.20 and row['doc'] < 90: return 'BAU'
        if row['str'] < 0.20 and row['doc'] > 90: return 'Liquidation'
        if row['str'] > 0.20 and row['doc'] > 90: return 'SVD'
        return 'Weekend'

    df_inv['Category'] = df_inv.apply(classify, axis=1)
    
    # Date Generation
    num_days = calendar.monthrange(target_year, target_month)[1]
    all_dates = [date(target_year, target_month, d) for d in range(1, num_days + 1)]
    locations = sorted(df_inv['location'].unique())
    
    promo_rows = []

    # Processing Logic
    for d in all_dates:
        # Determine current date type
        is_svd_period = d.day <= 10
        is_weekend = d.weekday() >= 5 # Sat=5, Sun=6
        
        # We group by SKU to see which price buckets are active for this date
        for sku_id in df_inv['channel_sku'].unique():
            sku_data = df_inv[df_inv['channel_sku'] == sku_id]
            sku_name = sku_data['master_sku'].iloc[0]
            
            # Fetch prices from the Price Mapping file
            price_map = df_price[df_price['channel_sku'] == sku_id]
            if price_map.empty: continue
            p = price_map.iloc[0]

            # Logic: We might need multiple rows per SKU if different locations have different statuses
            # However, usually we can group by the 'Applied Price'
            
            available_prices = {
                'SVD': p.get('SVD_Price'),
                'BAU': p.get('BAU_Price'),
                'Weekend': p.get('Weekend_Price'),
                'Liquidation': p.get('Liq_Price')
            }

            # Map Category to applicable Date logic
            for price_type, price_val in available_prices.items():
                active_locs_for_this_price = []
                
                for _, row in sku_data.iterrows():
                    # Liquidation is always active if classified as such
                    if row['Category'] == 'Liquidation' and price_type == 'Liquidation':
                        active_locs_for_this_price.append(row['location'])
                    # SVD active only in first 10 days
                    elif row['Category'] == 'SVD' and price_type == 'SVD' and is_svd_period:
                        active_locs_for_this_price.append(row['location'])
                    # Weekend active only on weekends 11+
                    elif row['Category'] == 'Weekend' and price_type == 'Weekend' and not is_svd_period and is_weekend:
                        active_locs_for_this_price.append(row['location'])
                    # BAU active only on weekdays 11+
                    elif row['Category'] == 'BAU' and price_type == 'BAU' and not is_svd_period and not is_weekend:
                        active_locs_for_this_price.append(row['location'])
                
                if active_locs_for_this_price:
                    res = {
                        "Date": d.strftime('%Y-%m-%d'),
                        "SKU ID": sku_id,
                        "Product Name": sku_name,
                        "Promo Price": price_val
                    }
                    for loc in locations:
                        res[loc] = "YES" if loc in active_locs_for_this_price else "NO"
                    promo_rows.append(res)

    final_df = pd.DataFrame(promo_rows)

    # --- 3. Output Preview & Download ---
    st.subheader("Final Promo File Preview")
    st.dataframe(final_df.head(20))

    # Excel Download
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        final_df.to_excel(writer, index=False, sheet_name='BigBasket_Upload')
    
    st.download_button(
        label="Download Promo File (.xlsx)",
        data=output.getvalue(),
        file_name=f"BB_Promo_{calendar.month_name[target_month]}_{target_year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
