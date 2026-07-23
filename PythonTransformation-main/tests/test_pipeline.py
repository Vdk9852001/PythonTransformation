from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from sap_migration import MigrationPipeline, PipelineConfig

SS = "urn:schemas-microsoft-com:office:spreadsheet"
NS = {"ss": SS}

TEMPLATE = """<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles><Style ss:ID="INTRO"/><Style ss:ID="DATA"/></Styles>
 <Worksheet ss:Name="Introduction"><Table><Row ss:StyleID="INTRO"><Cell><Data ss:Type="String">Help</Data></Cell></Row></Table></Worksheet>
 <Worksheet ss:Name="Valuation Data"><Table ss:ExpandedRowCount="3">
  <Row ss:StyleID="INTRO"><Cell><Data ss:Type="String">Do not edit</Data></Cell></Row>
  <Row><Cell><Data ss:Type="String">MATNR</Data></Cell><Cell><Data ss:Type="String">BWKEY</Data></Cell><Cell><Data ss:Type="String">WAERS</Data></Cell><Cell><Data ss:Type="String">MLAST</Data></Cell><Cell><Data ss:Type="String">CURTP</Data></Cell></Row>
  <Row ss:StyleID="DATA"><Cell><Data ss:Type="String"></Data></Cell><Cell><Data ss:Type="String"></Data></Cell><Cell><Data ss:Type="String"></Data></Cell><Cell><Data ss:Type="String"></Data></Cell><Cell><Data ss:Type="String"></Data></Cell></Row>
 </Table></Worksheet>
</Workbook>"""


class PipelineTest(unittest.TestCase):
    def test_preserves_template_and_populates_cloned_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            extracts = root / "extracts"
            extracts.mkdir()
            pd.DataFrame(
                [{"MATNR": "123", "BWKEY": "USP1"}, {"MATNR": "ABC", "BWKEY": "UNKNOWN"}]
            ).to_csv(extracts / "MBEW.csv", index=False)
            pd.DataFrame(
                [
                    {"S4_Table": "Valuation Data", "S4_Field": "MATNR", "S47_Table": "MBEW", "S47_Field": "MATNR"},
                    {"S4_Table": "Valuation Data", "S4_Field": "BWKEY", "S47_Table": "MBEW", "S47_Field": "BWKEY"},
                    {"S4_Table": "Valuation Data", "S4_Field": "WAERS", "S47_Table": "No", "S47_Field": "No"},
                    {"S4_Table": "Valuation Data", "S4_Field": "MLAST", "S47_Table": "No", "S47_Field": "No"},
                    {"S4_Table": "Valuation Data", "S4_Field": "CURTP", "S47_Table": "No", "S47_Field": "No"},
                ]
            ).to_excel(root / "mapping.xlsx", index=False)
            (root / "template.xml").write_text(TEMPLATE, encoding="utf-8")

            output = root / "result.xml"
            pipeline = MigrationPipeline(
                PipelineConfig(extracts, root / "mapping.xlsx", root / "template.xml", output)
            )
            pipeline.run()

            tree = ET.parse(output)
            self.assertIn("mso-application", output.read_text(encoding="utf-8"))
            worksheets = tree.getroot().findall("ss:Worksheet", NS)
            self.assertEqual(len(worksheets), 2)
            intro = worksheets[0].find(".//ss:Data", NS)
            self.assertEqual(intro.text, "Help")
            rows = worksheets[1].findall(".//ss:Row", NS)
            self.assertEqual(len(rows), 4)
            first_values = [node.text or "" for node in rows[2].findall(".//ss:Data", NS)]
            second_values = [node.text or "" for node in rows[3].findall(".//ss:Data", NS)]
            self.assertEqual(first_values, ["000000000000000123", "USP1", "USD", "3", "10"])
            self.assertEqual(second_values, ["ABC", "UNKNOWN", "", "3", "10"])
            self.assertEqual(rows[2].get(f"{{{SS}}}StyleID"), "DATA")
            self.assertTrue((root / "migration_errors.csv").exists())


if __name__ == "__main__":
    unittest.main()
