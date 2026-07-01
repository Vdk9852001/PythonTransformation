import pandas as pd
import os

# Input template and output folder
template_path = r"C:\DataMigration\omnion\PRL_Transformation\Product\Template\Product_Template.xlsx"
output_folder = r"C:\DataMigration\omnion\PRL_Transformation\Product\FieldMapping"
os.makedirs(output_folder, exist_ok=True)

# Load template
df = pd.read_excel(template_path)
df.columns = df.columns.str.strip()
df = df[['S4_Table', 'S4_Field', 'S47_Table', 'S47_Field']]  # Adjust if needed
df.columns = ['S4_Table', 'S4_Field', 'SAP47_Table', 'SAP47_Field']

# Filter out invalid mappings
invalid_values = ["No", "NO", "no", "No Direct mapping from 4.7", "TBD", "", None]
df = df[~df['SAP47_Table'].isin(invalid_values)]
df = df[~df['SAP47_Field'].isin(invalid_values)]

# Group by S4_Table
grouped = df.groupby('S4_Table')

# Generate mapped_fields.csv for each S4_Table
for s4_table, group in grouped:
    s4_row = [f"{s4_table}-{field}" for field in group['S4_Field']]
    sap47_row = [f"{table}-{field}" for table, field in zip(group['SAP47_Table'], group['SAP47_Field'])]

    output_df = pd.DataFrame([s4_row, sap47_row])
    output_path = os.path.join(output_folder, f"{s4_table}_mapped_fields.csv")
    output_df.to_csv(output_path, index=False, header=False)
    print(f"Created: {output_path}")

print("All field maps generated successfully.")
