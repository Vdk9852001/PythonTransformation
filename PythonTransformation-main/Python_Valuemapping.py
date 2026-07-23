import pandas as pd
import os
from datetime import datetime

# ---------------------------------------------------------
# Feature 1: Global Log File
# ---------------------------------------------------------
log_folder = "logs"
os.makedirs(log_folder, exist_ok=True)
log_file = os.path.join(log_folder, "mapping_log.txt")

def write_log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message)

# ---------------------------------------------------------
# Feature 3: Unmapped Summary Collector
# ---------------------------------------------------------
unmapped_summary = []   # Will export to CSV at end

# ---------------------------------------------------------
# Function: Apply value mapping safely
# ---------------------------------------------------------
def apply_value_mapping(series, mapping_dict, field_name, file_name):
    series_str = series.astype(str).str.replace(r'\.0$', '', regex=True)
    mapped_series = series_str.map(mapping_dict)

    # Detect unmapped values
    unmapped = series_str[~series_str.isin(mapping_dict.keys())].dropna().unique()

    if len(unmapped) > 0:
        write_log(f"Unmapped values in file '{file_name}', column '{field_name}': {unmapped}")

        # Add to summary table
        unmapped_summary.append({
            "File": file_name,
            "Column": field_name,
            "Unmapped Values": ", ".join(unmapped),
            "Count": len(unmapped)
        })

    return mapped_series

# ---------------------------------------------------------
# Function: Update existing WAERS column based on BWKEY
# ---------------------------------------------------------
def update_waers(df, file_name):
    # Identify WAERS column
    waers_col = None
    for col in df.columns:
        if col.upper().endswith("WAERS"):
            waers_col = col
            break

    if waers_col is None:
        write_log(f"No WAERS column found in {file_name}, skipping WAERS update.")
        return df

    # Identify BWKEY column (normalize)
    bwkey_col = None
    for col in df.columns:
        if col.upper().endswith("BWKEY"):
            bwkey_col = col
            break

    if bwkey_col is None:
        write_log(f"BWKEY column not found in {file_name}, cannot update WAERS.")
        return df

    bwkey_series = df[bwkey_col].astype(str).str.strip().str.upper()

    waers_map = {
        "USD": ["USP1", "USP2", "USP3", "USP4", "UPS5", "USP6"],
        "CNY": ["CNP1", "CNP2"],
        "CHF": ["CHP1","CHP2"],
        "EUR": ["DEP1"],
        "SGD": ["SGP1", "SGP2", "SGP3"],
        "MXN": ["MXP1", "MXP2"]
    }

    plant_to_currency = {
        plant: currency
        for currency, plants in waers_map.items()
        for plant in plants
    }

    df[waers_col] = bwkey_series.map(plant_to_currency)

    unmapped = bwkey_series[df[waers_col].isna()].unique()
    if len(unmapped) > 0:
        write_log(f"Unmapped BWKEY values for WAERS in {file_name}: {unmapped}")

    return df

def update_mlast(df, file_name):
    # Find MLAST column (e.g., S_MBEW-MLAST)
    mlast_col = None
    for col in df.columns:
        if col.upper().endswith("MLAST"):
            mlast_col = col
            break

    if mlast_col is None:
        write_log(f"MLAST column not found in {file_name}, skipping MLAST update.")
        return df

    # Set MLAST = 3
    df[mlast_col] = 3
    write_log(f"MLAST updated to 3 for {file_name}")

    return df
def update_curtp(df, file_name):
    # Find CURTP column (e.g., S_MBEW-CURTP)
    curtp_col = None
    for col in df.columns:
        if col.upper().endswith("CURTP"):
            curtp_col = col
            break

    if curtp_col is None:
        write_log(f"MLAST column not found in {file_name}, skipping MLAST update.")
        return df

    # Set CURTP = 10
    df[curtp_col] = 10
    write_log(f"MLAST updated to 3 for {file_name}")

    return df
# ---------------------------------------------------------
# Function: Update ENTITLED based on LGNUM
# ---------------------------------------------------------
def update_entitled(df, file_name):
    # Identify LGNUM column
    lgnum_col = None
    for col in df.columns:
        if col.upper().endswith("LGNUM"):
            lgnum_col = col
            break

    if lgnum_col is None:
        write_log(f"LGNUM column not found in {file_name}, skipping ENTITLED update.")
        return df

    # Identify ENTITLED column
    entitled_col = None
    for col in df.columns:
        if col.upper().endswith("ENTITLED"):
            entitled_col = col
            break

    if entitled_col is None:
        write_log(f"ENTITLED column not found in {file_name}, skipping ENTITLED update.")
        return df

    # Normalize LGNUM values
    lgnum_series = df[lgnum_col].astype(str).str.strip().str.upper()

    # Mapping rules
    entitled_map = {
        "BRN1": "20000036",
        "MAT1": "20000036",
        "PU01": "40000003",
        "PU02": "20000035",
        "SH02": "20000037"
    }

    # Apply mapping
    df[entitled_col] = lgnum_series.map(entitled_map)

    # Log unmapped LGNUM values
    unmapped = lgnum_series[df[entitled_col].isna()].unique()
    if len(unmapped) > 0:
        write_log(f"Unmapped LGNUM values for ENTITLED in {file_name}: {unmapped}")

    write_log(f"ENTITLED updated for {file_name}")
    return df

    
# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------
filled_folder = r"C:\Data Migration\omnion\PRL_Transformation\Product\Transformed_Files"
value_map_file = r"C:\Data Migration\omnion\PRL_Transformation\Product\Template\ValueMapping.xlsx"
output_folder = r"C:\Data Migration\omnion\PRL_Transformation\Product\Full_Transformed"

os.makedirs(output_folder, exist_ok=True)

# ---------------------------------------------------------
# Load value mappings from Excel (multi-sheet)
# ---------------------------------------------------------
value_mappings = {}
if os.path.exists(value_map_file):
    xls = pd.ExcelFile(value_map_file)
    for sheet_name in xls.sheet_names:
        df = xls.parse(sheet_name, dtype=str)
        df.columns = [str(col).strip() for col in df.columns]

        if 'SAP47_Value' in df.columns and 'S4_Value' in df.columns:
            map_key = sheet_name.strip().upper()
            keys = df['SAP47_Value'].astype(str)
            values = df['S4_Value'].astype(str)

            mapping_dict = dict(zip(keys, values))
            value_mappings[map_key] = mapping_dict

            write_log(f"Loaded mapping sheet: {map_key} ({len(mapping_dict)} entries)")

# ---------------------------------------------------------
# Process each _filled.csv file
# ---------------------------------------------------------
for file in os.listdir(filled_folder):
    if not file.endswith("_filled.csv"):
        continue

    file_path = os.path.join(filled_folder, file)
    df = pd.read_csv(file_path)
    df.columns = [str(col).strip() for col in df.columns]

    write_log(f"Processing file: {file}")

    mapped_columns = 0
    unmapped_columns = 0

    # ---------------------------------------------------------
    # Apply all value mappings first
    # ---------------------------------------------------------
    for col in df.columns:
        map_key = str(col).strip().split('-')[-1].upper()
        normalized_key = "WERK" if "WERK" in map_key else map_key

        if normalized_key in value_mappings:
            df[col] = apply_value_mapping(df[col], value_mappings[normalized_key], col, file)
            mapped_columns += 1
        else:
            unmapped_columns += 1

    # ---------------------------------------------------------
    # AFTER all value mappings → update WAERS
    # ---------------------------------------------------------
    if file.startswith(("S_MBEW", "S_MBEW_CURRENT", "S_MBEW_FUTURE")):
        df = update_waers(df, file)
        df= update_mlast(df, file)
        df = update_curtp(df, file)
        write_log(f"WAERS updated for {file}")
    
    # Update ENTITLED only for warehouse tables
    if file.upper().startswith(("S_MATLWH", "S_MATLWHST")):
        df = update_entitled(df, file)

    # ---------------------------------------------------------
    # Save mapped file
    # ---------------------------------------------------------
    output_name = file.replace("_filled.csv", "_mapped.csv")
    output_path = os.path.join(output_folder, output_name)
    df.to_csv(output_path, index=False)

    # ---------------------------------------------------------
    # Per-file summary
    # ---------------------------------------------------------
    write_log(
        f"Summary for {file}: "
        f"Mapped Columns = {mapped_columns}, "
        f"Unmapped Columns = {unmapped_columns}"
    )

    write_log(f"Mapped output saved: {output_name}\n")

# ---------------------------------------------------------
# Export unmapped summary report
# ---------------------------------------------------------
if unmapped_summary:
    summary_df = pd.DataFrame(unmapped_summary)
    summary_path = os.path.join(log_folder, "unmapped_summary.csv")
    summary_df.to_csv(summary_path, index=False)
    write_log(f"Unmapped summary exported: {summary_path}")
else:
    write_log("No unmapped values found across all files.")

write_log("All filled outputs mapped using value_mapping.xlsx.")
