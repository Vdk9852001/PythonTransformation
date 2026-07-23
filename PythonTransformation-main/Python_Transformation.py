import pandas as pd
import os

# Define paths
fieldmap_folder = r"C:\Data Migration\omnion\PRL_Transformation\Product\FieldMapping"
legacy_folder = r"C:\Data Migration\omnion\PRL_Extraction\Material"
output_folder = os.path.join(r"C:\Data Migration\omnion\PRL_Transformation\Product", "Transformed_Files")
os.makedirs(output_folder, exist_ok=True)

# Define join rules
join_rules = {
    'MAKT': {'base': 'MARA', 'left_key': 'MATNR', 'right_key': 'MATNR'},
    'TB070_CM': {'base': 'MLAN', 'left_key': 'ALAND', 'right_key': 'TAX_CTY'}
}

def normalize_matnr(df, col='MATNR', length=18):
    if col in df.columns:
        def pad_condition(val):
            val = str(val).strip()
            # Pad only if the value is fully numeric (no letters, no symbols)
            return val.zfill(length) if val.isdigit() else val
        df[col] = df[col].apply(pad_condition)
    return df

def preprocess_makt(df, preferred_lang='E'):
    df = normalize_matnr(df, 'MATNR')
    if 'SPRAS' in df.columns:
        df['SPRAS'] = df['SPRAS'].astype(str).str.strip().str.upper()
        df = df[df['SPRAS'] == preferred_lang]  # keep only preferred language
    return df

def preprocess_generic(df):
    df.columns = df.columns.str.strip()
    df = df.apply(lambda col: col.astype(str).str.strip())
    return df

# --- Load legacy tables ---
def load_legacy_tables(folder):
    tables = {}
    for file in os.listdir(folder):
        if file.endswith(".csv"):
            path = os.path.join(folder, file)
            name = os.path.splitext(file)[0].upper()
            try:
                df = pd.read_csv(path, dtype=str, on_bad_lines='skip')
                df = preprocess_generic(df)
                if name == 'MARA':
                    df = normalize_matnr(df, 'MATNR')
                elif name == 'MAKT':
                    df = preprocess_makt(df, preferred_lang='E')
                else:
                    df = normalize_matnr(df, 'MATNR')
                tables[name] = df
                print(f"Loaded: {name} ({len(df)} rows)")
            except Exception as e:
                print(f"Skipped '{file}': {e}")
    return tables

# --- Date formatting ---
def detect_and_format_dates(df, date_format='%Y-%m-%d', placeholder_format='9999/12/31'):
    exclude_fields = ['S_MARA-MATKL']
    for col in df.columns:
        if col in exclude_fields:
            continue
        col_data = df[col].astype(str).str.strip()
        if col_data.str.match(r'^\d{8}$').mean() > 0.8:
            df[col] = col_data.apply(
                lambda x: placeholder_format if x.startswith('9999') else pd.to_datetime(x, format='%Y%m%d', errors='coerce')
            )
            df[col] = df[col].apply(
                lambda x: x.strftime(date_format) if isinstance(x, pd.Timestamp) else x
            )
            print(f"Auto-formatted date field: {col}")
    return df

# --- Mapping file parser ---
def parse_mapping_file(filepath):
    try:
        raw_df = pd.read_csv(filepath, header=None)
        mapping_df = raw_df.T
        mapping_df.columns = ['S4_Field', 'SAP47_Field']
        mapping_df[['SAP47_Table', 'SAP47_Column']] = mapping_df['SAP47_Field'].str.split('-', expand=True)
        return mapping_df
    except Exception as e:
        print(f"Failed to parse mapping file '{filepath}': {e}")
        return pd.DataFrame()

# --- Fill table based on mapping ---
def fill_table(mapping_df, legacy_tables):
    filled_df = pd.DataFrame()
    merged_cache = {}

    for _, row in mapping_df.iterrows():
        s4_field = row['S4_Field']
        table = row['SAP47_Table']
        column = row['SAP47_Column']

        if pd.isna(table) or pd.isna(column):
            filled_df[s4_field] = None
            continue

        table = table.strip().upper()
        column = column.strip()

        if table in join_rules:
            rule = join_rules[table]
            base = rule['base']
            left_key = rule['left_key']
            right_key = rule['right_key']
            cache_key = f"{base}_{table}"

            if cache_key in merged_cache:
                merged_df = merged_cache[cache_key]
            else:
                base_df = legacy_tables.get(base)
                join_df = legacy_tables.get(table)

                if base_df is not None and join_df is not None:
                    # --- Deduplicate TB070_CM before merging ---
                    if table == 'TB070_CM':
                        join_df = join_df.drop_duplicates(subset=[right_key])
                        join_df[right_key] = join_df[right_key].str.strip().str.upper()
                        base_df[left_key] = base_df[left_key].str.strip().str.upper()

                    merged_df = pd.merge(
                        base_df, join_df,
                        left_on=left_key, right_on=right_key,
                        how='left'
                    )
                    merged_cache[cache_key] = merged_df
                else:
                    merged_df = None

            if merged_df is not None and column in merged_df.columns:
                filled_df[s4_field] = merged_df[column].astype(str).str.strip()
            else:
                filled_df[s4_field] = None

        else:
            source_df = legacy_tables.get(table)
            if source_df is not None and column in source_df.columns:
                filled_df[s4_field] = source_df[column].astype(str).str.strip()
            else:
                filled_df[s4_field] = None

        filled_df = detect_and_format_dates(filled_df)

    return filled_df

# --- Transform all mapping files ---
def transform_all(fieldmap_folder, legacy_tables, output_folder):
    for file in os.listdir(fieldmap_folder):
        if not file.endswith("_mapped_fields.csv"):
            continue

        filepath = os.path.join(fieldmap_folder, file)
        mapping_df = parse_mapping_file(filepath)
        if mapping_df.empty:
            continue

        filled_df = fill_table(mapping_df, legacy_tables)
        outname = file.replace("_mapped_fields.csv", "_filled.csv")
        filled_df.to_csv(os.path.join(output_folder, outname), index=False)
        print(f"Saved: {outname}")

# --- Run process ---
legacy_tables = load_legacy_tables(legacy_folder)
transform_all(fieldmap_folder, legacy_tables, output_folder)
print("Transformation process completed.")
