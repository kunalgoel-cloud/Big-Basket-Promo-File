import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
import io

st.set_page_config(page_title="BB Promo Architect", layout="wide")

# --- BIG BASKET TEMPLATE CONSTANTS ---
BB_HEADERS = [
    'Code', 'Product Description', 'Start Date (DD-MM-YYYY)', 'End Date (DD-MM-YYYY)', 
    'Discount Type', 'Discount Value', 'Redemption Limit - Qty Per Campaign', 'Pan India', 
    'ANDHRA PRADESH', 'TELANGANA', 'ASSAM', 'BIHAR', 'CHHATTISGARH', 'GUJARAT', 
    'HARYANA_DELHI&GURGAON', 'JHARKHAND', 'KARNATAKA', 'KERALA', 'MADHYA PRADESH', 
    'MAHARASHTRA - Mumbai', 'MAHARASHTRA - Pune', 'ORISSA', 'PUNJAB', 'RAJASTHAN', 
    'TAMIL NADU', 'UTTAR PRADESH_Noida', 'WEST BENGAL'
]

STATE_COLUMNS = BB_HEADERS[8:] # All state columns starting from Andhra Pradesh

# Default mapping based on your file
DEFAULT_MAP = {
    'Mumbai-DC': 'MAHARASHTRA - Mumbai',
    'Pune-DC': 'MAHARASHTRA - Pune',
    'Bangalore-DC': 'KARNATAKA',
    'Bangalore-DC2': 'KARNATAKA',
    'Hyderabad-DC': 'TELANGANA',
    'Kolkata-DC': 'WEST BENGAL',
    'Chennai-DC': 'TAMIL NADU',
    'Ahmedabad-DC': 'GUJARAT',
    'Delhi-DC': 'HARYANA_DELHI&GURGAON',
    'Gurgaon-DC': 'HARYANA_DELHI&GURGAON'
}

st.title("📦 BigBasket Promo Portal Generator")

# --- Step 1: Upload & Date Config ---
with st.sidebar:
    st.header("1. Settings")
    year = st.selectbox("Year", [2025, 2026], index=1)
    month = st.selectbox("Month", list(range(1, 13)), format_func=lambda x: calendar.month_name[x])
    st.divider()
    inv_file = st.file_uploader("Upload Inventory CSV", type=['csv'])

if inv_file:
    df_inv = pd.read_csv(inv_file)
    unique_locations = df_inv['location'].unique()
    
    # --- Step 2: Editable DC to State Mapping ---
    st.subheader("Step 1: Map Locations to BB State Columns")
    with st.expander("Edit Location Mapping", expanded=True):
        map_data = []
        for loc in unique_locations:
            map_data.append({
                "Inventory Location": loc,
                "BB State Column": DEFAULT_MAP.get(loc, "KARNATAKA") # Defaulting to Karnataka if unknown
            })
        
        # Editable data editor
        edited_map_df = st.data_editor(
            pd.DataFrame(map_data),
            column_config={
                "BB State Column": st.column_config.SelectboxColumn(
                    "BB State Column",
                    options=STATE_COLUMNS,
                    required=True,
                )
            },
            num_rows="fixed",
            hide_index=True
        )
        # Convert back to dictionary
        FINAL_MAP = dict(zip(edited_map_df["Inventory Location"], edited_map_df["BB State Column"]))

    # --- Step 3: Price Input Form ---
    st.divider()
    st.subheader("Step 2: Enter SKU Level Target Prices")
    unique_products = df_inv[['channel_sku', 'master_sku']].drop_duplicates()
    
    with st.form("price_entry"):
        sku_prices = {}
        h = st.columns([2, 1, 1, 1, 1])
        h[0].write("**Product**")
        h[1].write("**BAU**")
        h[2].write("**SVD**")
        h[3].write("**Weekend**")
        h[4].write("**Liq.**")

        for _, p_row in unique_products.iterrows():
            r = st.columns([2, 1, 1, 1, 1])
            sid = p_row['channel_sku']
            r[0].write(f"{p_row['master_sku']} \n ({sid})")
            p1 = r[1].number_input("BAU", key=f"bau_{sid}", label_visibility="collapsed")
            p2 = r[2].number_input("SVD", key=f"svd_{sid}", label_visibility="collapsed")
            p3 = r[3].number_input("Wek", key=f"wek_{sid}", label_visibility="collapsed")
            p4 = r[4].number_input("Liq", key=f"liq_{sid}", label_visibility="collapsed")
            sku_prices[sid] = {'BAU': p1, 'SVD': p2, 'Weekend': p3, 'Liq': p4}
        
        generate = st.form_submit_button("Generate BB Upload File")

    # --- Step 4: Logic & File Generation ---
    if generate:
        num_days = calendar.monthrange(year, month)[1]
        start_dt = date(year, month, 1)
        end_dt = date(year, month, num_days)
        
        final_rows = []

        for sku in unique_products['channel_sku'].unique():
            sku_inv = df_inv[df_inv['channel_sku'] == sku]
            sku_name = sku_inv['master_sku'].iloc[0]
            
            # Temporary storage to group days
            day_by_day = []
            
            # Loop through every day of the month
            curr = start_dt
            while curr <= end_dt:
                is_svd_day = curr.day <= 10
                is_weekend = curr.weekday() >= 5
                
                # For each price point, see which states qualify
                price_points = sku_prices[sku]
                
                for p_type, p_val in price_points.items():
                    active_states = []
                    for _, row in sku_inv.iterrows():
                        # Determine Category
                        cat = 'BAU'
                        if row['str'] < 0.20 and row['doc'] > 90: cat = 'Liq'
                        elif row['str'] > 0.20 and row['doc'] > 90: cat = 'SVD' if is_svd_day else 'BAU'
                        elif row['str'] < 0.20 and row['doc'] < 90: cat = 'Weekend' if is_weekend else 'BAU'
                        
                        if cat == p_type:
                            active_states.append(FINAL_MAP.get(row['location']))
                    
                    if active_states:
                        day_by_day.append({
                            'Date': curr,
                            'Price': p_val,
                            'States': sorted(list(set(active_states)))
                        })
                curr += timedelta(days=1)

            # Consolidate daily rows into Date Ranges (Start -> End)
            if day_by_day:
                grouped = []
                entry = day_by_day[0]
                start = entry['Date']
                
                for i in range(1, len(day_by_day)):
                    prev = day_by_day[i-1]
                    nxt = day_by_day[i]
                    
                    # If price or state list changes, or gap in dates, break the range
                    if (nxt['Price'] != prev['Price'] or 
                        nxt['States'] != prev['States'] or 
                        nxt['Date'] != prev['Date'] + timedelta(days=1)):
                        
                        grouped.append({'s': start, 'e': prev['Date'], 'p': prev['Price'], 'st': prev['States']})
                        start = nxt['Date']
                
                grouped.append({'s': start, 'e': day_by_day[-1]['Date'], 'p': day_by_day[-1]['Price'], 'st': day_by_day[-1]['States']})

                # Create the final BB Format rows
                for g in grouped:
                    out_row = {col: "" for col in BB_HEADERS}
                    out_row['Code'] = sku
                    out_row['Product Description'] = sku_name
                    out_row['Start Date (DD-MM-YYYY)'] = g['s'].strftime('%d-%m-%Y')
                    out_row['End Date (DD-MM-YYYY)'] = g['e'].strftime('%d-%m-%Y')
                    out_row['Discount Type'] = 'fixed'
                    out_row['Discount Value'] = g['p']
                    out_row['Pan India'] = 'No'
                    for s in g['st']: 
                        if s in out_row: out_row[s] = 'Yes'
                    final_rows.append(out_row)

        output_df = pd.DataFrame(final_rows)
        st.success(f"Generated {len(output_df)} promo lines!")
        st.dataframe(output_df)

        # Download
        csv = output_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download BigBasket CSV", csv, f"BB_Promo_{month}_{year}.csv", "text/csv")
