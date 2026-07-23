# SAP 4.7 to S/4HANA Product Migration

This pipeline loads SAP 4.7 CSV extracts, builds a correctly grained dataset for
each migration worksheet, applies field and value mappings, runs product business
rules, and populates an existing SAP Migration Cockpit Excel 2003 XML
(SpreadsheetML) template.

The writer preserves the workbook and all untouched worksheets, styles, columns,
and help rows. `Introduction`, `Field List`, and rows styled `INTRO` or
`INTRO_UT` are never populated.

## Inputs

- A folder containing extracts such as `MARA.csv`, `MAKT.csv`, `MARC.csv`,
  `MBEW.csv`, `MLAN.csv`, `MARM.csv`, `MLGN.csv`, and `MLGT.csv`.
- A field mapping `.xlsx` with `S4_Table`, `S4_Field`, `S47_Table`, and
  `S47_Field` columns. `S4_Table` must identify the corresponding SAP worksheet.
  A folder of the legacy two-row `*_mapped_fields.csv` files is also accepted.
- An optional value mapping `.xlsx`. Each sheet name is a target field name and
  contains `SAP47_Value` and `S4_Value`.
- The original SAP Migration Cockpit `.xml` SpreadsheetML template.

## Run

### Desktop application

On macOS, double-click `run_app.command`. It uses the bundled, tested Python
runtime and avoids conflicts with other Python or Anaconda installations.

Alternatively:

```shell
python app.py
```

Select the source folder, mapping files, original SAP XML template, and output
location, then choose **Generate SAP XML**. Transformation runs in the
background so the window remains responsive. Progress, logs, validation errors,
and the final observation count are shown in the application.

### Command line

```shell
python migrate.py \
  --source-folder /path/to/extracts \
  --field-mapping /path/to/Product_Field_Mapping.xlsx \
  --value-mapping /path/to/ValueMapping.xlsx \
  --sap-template /path/to/Product_Template.xml \
  --output /path/to/Product_Migration.xml
```

The run also creates a log and `migration_errors.csv`. Add
`--show-error-dialog` for a desktop warning when observations were collected.

## Implemented rules

- `WAERS` is derived from `BWKEY`.
- `MLAST` is always `3`.
- `CURTP` is always `10`.
- `ENTITLED` is derived from `LGNUM`.
- Value mappings use `map(...).fillna(original)`, and every nonblank unmapped
  value is included in the error report.

Entity joins are built independently per worksheet to avoid a global Cartesian
product. The most detailed referenced source table anchors each worksheet; other
tables enrich it through the available SAP keys.
