import streamlit as st
import pandas as pd
import calendar
from datetime import date
import io

st.set_page_config(page_title="BB Promo Architect", layout="wide")

st.title("📦 BigBasket Promo Portal Generator")
st.markdown("Automated promo file generation with manual target price entry.")

# --- 1. Sidebar Config ---
with st.sidebar:
    st.header("1. Calendar Settings")
    target_year = st.selectbox("Year", [2024, 2025, 2026], index=2)
    target_month = st.selectbox("Month", list(range(1, 13)), format_func=lambda x: calendar.month_name[x])
    
    st.divider()
    st.subheader("Classification Rules")
    st.caption("BAU: STR > 20%, DOC < 90")
    st.caption("Liq: STR < 20%, DOC > 90")
    st.caption("SVD: STR > 20%, DOC > 90")
    st.caption("Weekend: STR < 20%, DOC < 90")

# --- 2. Inventory File Upload ---
st.subheader("Step 1: Upload Inventory File")
inv_file = st.file_uploader("Upload CSV/XLSX (must contain: channel_sku, master_sku, location, str, doc)", type=['csv', 'xlsx'])

if inv_file:
    # Load and clean data
    df_inv = pd.read_csv(inv_file) if inv_file.name.endswith('csv') else pd.read_excel(inv_file)
    
    # Simple validation/normalization
    if df_inv['str'].max() > 1:
        df_inv['str'] = df_inv['str'] / 100

    # Get unique products for the form
    unique_products = df_inv[['channel_sku', 'master_sku']].drop_duplicates()
    
    st.divider()
    st.subheader("Step 2: Enter Target Prices for each Product")
    
    # --- 3. Dynamic Form for Price Input ---
    with st.form("price_entry_form"):
        st.info("Enter the discounted price points for each bucket below.")
        
        # We will store the inputs in a dictionary
        price_data = []
        
        # Create columns for headers
        h1, h2, h3, h4, h5 = st.columns([2, 1, 1, 1, 1])
        h1.write("**Product Name (SKU ID)**")
        h2.write("**BAU Price**")
        h3.write("**SVD Price**")
        h4.write("**Weekend Price**")
        h5.write("**Liq. Price**")
        
        for _, row in unique_products.iterrows():
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
            
            c1.write(f"{row['master_sku']} \n ({row['channel_sku']})")
            
            # Using number inputs with keys unique to the SKU
            bau_p = c2.number_input("BAU", key=f"bau_{row['channel_sku']}", label_visibility="collapsed", min_value=0.0, step=1.0)
            svd_p = c3.number_input("SVD", key=f"svd_{row['channel_sku']}", label_visibility="collapsed", min_value=0.0, step=1.0)
            wek_p = c4.number_input("Weekend", key=f"wek_{row['channel_sku']}", label_visibility="collapsed", min_value=0.0, step=1.0)
            liq_p = c5.number_input("Liquidation", key=f"liq_{row['channel_sku']}", label_visibility="collapsed", min_value=0.0, step=1.0)
            
            price_data.append({
                'channel_sku': row['channel_sku'],
                'BAU_Price': bau_p,
                'SVD_Price': svd_p,
                'Weekend_Price': wek_p,
                'Liq_Price': liq_p
            })
            
        submitted = st.form_submit_button("Generate Final Promo File")

    # --- 4. Processing Logic after Submit ---
    if submitted:
        df_price = pd.DataFrame(price_data)
        
        # Classification Function
        def classify(row):
            if row['str'] > 0.20 and row['doc'] < 90: return 'BAU'
            if row['str'] < 0.20 and row['doc'] > 90: return 'Liquidation'
            if row['str'] > 0.20 and row['doc'] > 90: return 'SVD'
            return 'Weekend'

        df_inv['Category'] = df_inv.apply(classify, axis=1)
        
        # Date and Location Prep
        num_days = calendar.monthrange(target_year, target_month)[1]
        all_dates = [date(target_year, target_month, d) for d in range(1, num_days + 1)]
        locations = sorted(df_inv['location'].unique())
        
        promo_rows = []

        for d in all_dates:
            is_svd_period = d.day <= 10
            is_weekend = d.weekday() >= 5
            
            for sku_id in df_inv['channel_sku'].unique():
                sku_data = df_inv[df_inv['channel_sku'] == sku_id]
                sku_name = sku_data['master_sku'].iloc[0]
                
                # Get the prices entered in the form
                p = df_price[df_price['channel_sku'] == sku_id].iloc[0]
                
                # Logic per Price Bucket
                price_buckets = {
                    'SVD': p['SVD_Price'],
                    'BAU': p['BAU_Price'],
                    'Weekend': p['Weekend_Price'],
                    'Liquidation': p['Liq_Price']
                }

                for price_type, price_val in price_buckets.items():
                    active_locs = []
                    
                    for _, row in sku_data.iterrows():
                        if row['Category'] == 'Liquidation' and price_type == 'Liquidation':
                            active_locs.append(row['location'])
                        elif row['Category'] == 'SVD' and price_type == 'SVD' and is_svd_period:
                            active_locs.append(row['location'])
                        elif row['Category'] == 'Weekend' and price_type == 'Weekend' and not is_svd_period and is_weekend:
                            active_locs.append(row['location'])
                        elif row['Category'] == 'BAU' and price_type == 'BAU' and not is_svd_period and not is_weekend:
                            active_locs.append(row['location'])
                    
                    if active_locs:
                        res = {
                            "Date": d.strftime('%Y-%m-%d'),
                            "SKU ID": sku_id,
                            "Product Name": sku_name,
                            "Promo Price": price_val
                        }
                        for loc in locations:
                            res[loc] = "YES" if loc in active_locs else "NO"
                        promo_rows.append(res)

        # Output Generation
        final_df = pd.DataFrame(promo_rows)
        
        st.success("✅ File generated successfully!")
        st.dataframe(final_df.head(10))

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_df.to_excel(writer, index=False, sheet_name='BB_Promo')
        
        st.download_button(
            label="⬇️ Download BigBasket Upload File",
            data=output.getvalue(),
            file_name=f"BB_Promo_{calendar.month_name[target_month]}_{target_year}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
