#!/usr/bin/env python3
"""Extract and gate the 2024 non-leap provincial load shape from Figshare XLSX.

The source workbook is the CC BY 4.0 data record associated with:
Yi et al., Scientific Data (2026), doi:10.1038/s41597-026-07327-8.
The workbook contains 8,784 hourly rows for leap year 2024. 29 February is
removed deterministically to align with the model's frozen 8,760-hour VRE year.
The source values are hourly GWh (numerically equal to mean GW in each hour).
Only the within-province hourly shape is used downstream; target-year annual
energy remains locked to the V17T2R5 2033 model input.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
EXPECTED_MD5 = "bf730a545bc297b20d6a7ff93571992a"
EXPECTED_SHA256 = "a93ff6d4a2f4f8c36538fdc4704e2e88bef16347d217c456a99a7a97d56a19e0"
EXPECTED_SHEET = "xl/worksheets/sheet11.xml"
EXPECTED_PROVINCES = [
    "Anhui", "Beijing", "Chongqing", "Fujian", "Guangdong", "Gansu",
    "Guangxi", "Guizhou", "Hainan", "Hebei", "Henan", "Heilongjiang",
    "Hunan", "Hubei", "Jilin", "Jiangsu", "Jiangxi", "Liaoning",
    "Inner_Mongolia", "Ningxia", "Qinghai", "Shaanxi", "Sichuan",
    "Shandong", "Shanghai", "Shanxi", "Tianjin", "Xinjiang", "Tibet",
    "Yunnan", "Zhejiang",
]


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def column_index(cell_ref: str) -> int:
    match = re.match(r"[A-Z]+", cell_ref)
    if match is None:
        raise ValueError(f"Invalid XLSX cell reference: {cell_ref}")
    result = 0
    for char in match.group(0):
        result = result * 26 + ord(char) - 64
    return result - 1


def shared_strings(zf: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in item.iter(NS + "t")) for item in root]


def worksheet_rows(zf: zipfile.ZipFile, member: str):
    strings = shared_strings(zf)
    with zf.open(member) as fh:
        for _, element in ET.iterparse(fh, events=("end",)):
            if element.tag != NS + "row":
                continue
            cells: dict[int, str] = {}
            for cell in element.findall(NS + "c"):
                idx = column_index(cell.attrib["r"])
                cell_type = cell.attrib.get("t")
                node = cell.find(NS + "v")
                raw = "" if node is None else node.text or ""
                if cell_type == "s" and raw:
                    value = strings[int(raw)]
                elif cell_type == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                else:
                    value = raw
                cells[idx] = value
            last = max(cells, default=-1)
            yield [cells.get(i, "") for i in range(last + 1)]
            element.clear()


def normalize_header(text: str) -> str:
    english = text.split("(", 1)[0].strip()
    return english.replace(" ", "_")


def excel_datetime(serial: str) -> datetime:
    return datetime(1899, 12, 30) + timedelta(days=float(serial))


def extract(source: Path, output: Path, audit_csv: Path) -> None:
    md5 = digest(source, "md5")
    sha256 = digest(source, "sha256")
    if md5 != EXPECTED_MD5 or sha256 != EXPECTED_SHA256:
        raise ValueError(
            "Figshare source hash mismatch: "
            f"md5={md5}, sha256={sha256}; expected {EXPECTED_MD5}, {EXPECTED_SHA256}"
        )

    with zipfile.ZipFile(source) as zf:
        rows = worksheet_rows(zf, EXPECTED_SHEET)
        header = next(rows)
        if not header or header[0].strip() != "Unit: GWh":
            raise ValueError(f"Unexpected first header: {header[:3]}")
        provinces = [normalize_header(x) for x in header[1:32]]
        if provinces != EXPECTED_PROVINCES:
            raise ValueError(f"Unexpected province order: {provinces}")

        parsed: list[tuple[datetime, list[float]]] = []
        for row_number, row in enumerate(rows, start=2):
            if len(row) < 32:
                raise ValueError(f"Row {row_number} has only {len(row)} populated columns")
            stamp = excel_datetime(row[0])
            values = [float(v) for v in row[1:32]]
            if not all(v > 0.0 for v in values):
                raise ValueError(f"Row {row_number} contains non-positive provincial load")
            parsed.append((stamp, values))

    if len(parsed) != 8784:
        raise ValueError(f"Expected 8784 source hours for leap-year 2024, got {len(parsed)}")
    expected_start = datetime(2024, 1, 1, 0)
    for i, (stamp, _) in enumerate(parsed):
        if stamp != expected_start + timedelta(hours=i):
            raise ValueError(f"Non-continuous source timestamp at row {i + 2}: {stamp!s}")
    if parsed[-1][0] != datetime(2024, 12, 31, 23):
        raise ValueError(f"Unexpected final timestamp: {parsed[-1][0]!s}")

    nonleap = [(stamp, values) for stamp, values in parsed if not (stamp.month == 2 and stamp.day == 29)]
    if len(nonleap) != 8760:
        raise ValueError(f"Leap-day filter did not produce 8760 rows: {len(nonleap)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["model_hour", "source_timestamp_cst_assumed", *[f"{p}_load_gw" for p in provinces]])
        for hour, (stamp, values) in enumerate(nonleap, start=1):
            writer.writerow([hour, stamp.strftime("%Y-%m-%d %H:%M:%S"), *[format(v, ".15g") for v in values]])

    audits: list[dict[str, object]] = []
    columns = list(zip(*[values for _, values in nonleap]))
    for province, values in zip(provinces, columns):
        annual_twh = sum(values) / 1000.0
        audits.append({
            "province_en": province,
            "hours": len(values),
            "minimum_load_gw": min(values),
            "maximum_load_gw": max(values),
            "annual_energy_twh_source_reconstruction": annual_twh,
            "null_count": 0,
            "positive_values_pass": True,
        })
    with audit_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(audits[0]))
        writer.writeheader()
        writer.writerows(audits)

    print(f"PASS: extracted {len(nonleap)} non-leap hours x {len(provinces)} provinces")
    print(f"source_md5={md5}")
    print(f"source_sha256={sha256}")
    print(f"processed_sha256={digest(output, 'sha256')}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=root / "data" / "raw" / "load" / "figshare_29832701_Data_output.xlsx",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "data" / "processed" / "figshare_load_2024_31province_8760_nonleap.csv",
    )
    parser.add_argument(
        "--audit-csv",
        type=Path,
        default=root / "audits" / "FIGSHARE_2024_LOAD_DATA_QUALITY_AUDIT.csv",
    )
    args = parser.parse_args()
    extract(args.source.resolve(), args.output.resolve(), args.audit_csv.resolve())


if __name__ == "__main__":
    main()
