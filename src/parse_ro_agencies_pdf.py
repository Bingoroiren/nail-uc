# -*- coding: utf-8 -*-
"""
Parser danh sach cong ty & ma dinh danh (Cod Fiscal / CUI) tu cac tep PDF chinh thuc tai Romania:
1. Inspectia Muncii - Lista agentilor de plasare a fortei de munca in strainatate
2. Ministerul Muncii (MMSS) - Registrul National al Agentilor de Munca Temporara (AMT)

Tuan thu quy chuan workspace (GEMINI.md / data-standards):
- Xuat CSV UTF-8 with BOM (utf-8-sig), tuyet doi khong xuat Excel.
- Khong luu danh sach den Permanent Blacklist.
- Giu nguyen ma dinh danh (CUI/CIF) dang chuoi, khong mat ky tu.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

import pandas as pd
import pdfplumber

BASE_DIR = Path(__file__).resolve().parent.parent
RO_DIR = BASE_DIR / "ro_romania"

PDF1_PATH = RO_DIR / "inspectiamuncii_lista_ag_ian_2025.pdf"
PDF2_CANDIDATE_NAMES = (
    "Reg-Nat-al-AMT-la-31.01.2026.pdf",
    "mmuncii_reg_nat_amt_2026_01_31.pdf",
)

OUT_PDF1_RAW = BASE_DIR / "RO_AGCY_PDF1_0RAW.csv"
OUT_PDF2_RAW = BASE_DIR / "RO_AGCY_PDF2_0RAW.csv"
OUT_MERGED_RAW = BASE_DIR / "RO_AGCY_PDF0_0RAW.csv"
OUT_UNIQ_CUI = RO_DIR / "RO_AGCY_COMPANIES_CUI.csv"

# Fallback 9-column x-boundaries measured from Inspectia Muncii PDF page 1 header
FALLBACK_IM_BOUNDS = [15.0, 46.5, 109.1, 239.7, 300.0, 360.2, 537.6, 574.7, 743.9, 845.0]

PERMANENT_BLACKLIST_COMPANIES = (
    "scandi standard",
    "scandi-standard",
    "scandi standart",
    "biliarta",
    "daigre",
)


def clean_text(val) -> str:
    """Collapse weird whitespace, NBSP and invisible control chars."""
    if val is None:
        return ""
    s = str(val)
    for bad in ("\u00a0", "\xa0", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        s = s.replace(bad, " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_blacklisted_company(name: str) -> bool:
    """Permanent company exclusion check (Rule 12 / GEMINI.md)."""
    if not name or not isinstance(name, str):
        return False
    n = unicodedata.normalize("NFKD", name).lower()
    n_clean = "".join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def join_cell_words(words_in_cell: list[dict]) -> str:
    """Group cell words into horizontal visual lines (~3.5pt tolerance) and sort left-to-right."""
    if not words_in_cell:
        return ""
    lines: list[list[dict]] = []
    for w in sorted(words_in_cell, key=lambda x: x["top"]):
        if not lines or abs(w["top"] - lines[-1][0]["top"]) > 3.5:
            lines.append([w])
        else:
            lines[-1].append(w)
    ordered_tokens: list[str] = []
    for ln in lines:
        ln.sort(key=lambda x: x["x0"])
        ordered_tokens.extend(w["text"] for w in ln)
    return clean_text(" ".join(ordered_tokens))


def col_index_for_x(x_mid: float, bounds: list[float]) -> int:
    """Map horizontal word midpoint into one of the fixed column intervals."""
    num_cols = len(bounds) - 1
    for i in range(num_cols):
        if bounds[i] <= x_mid < bounds[i + 1]:
            return i
    return num_cols - 1 if x_mid >= bounds[-1] else 0


def detect_im_column_bounds(first_page) -> list[float]:
    """Read exact 9-column vertical bounds from page 1 header table, widening outer edges."""
    tables = [t for t in first_page.find_tables() if t.rows and len(t.rows[0].cells) == 9]
    if not tables:
        return FALLBACK_IM_BOUNDS
    hdr_table = max(tables, key=lambda t: len(t.rows))
    cells = hdr_table.rows[0].cells
    bounds = [15.0] + [round(float(c[2]), 2) for c in cells[:-1]] + [845.0]
    if len(bounds) != 10:
        return FALLBACK_IM_BOUNDS
    return bounds


def normalize_cui(raw_cui: str) -> str:
    """Clean Cod fiscal / CUI string while preserving digits cleanly."""
    s = clean_text(raw_cui)
    if not s or s == "0":
        return ""
    # Handle optional 'RO' VAT prefix followed by spaces/digits
    m = re.fullmatch(r"(?:RO\s*)?(\d{4,12})", s, flags=re.I)
    if m:
        prefix = "RO" if s.upper().startswith("RO") else ""
        return f"{prefix}{m.group(1)}"
    return s


def extract_inspectia_muncii_pdf(pdf_path: Path) -> list[dict]:
    """Extract all valid agencies & CUI codes using row bboxes + fixed X-column intervals."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"Khong tim thay file PDF: {pdf_path}")

    records: list[dict] = []
    skipped_placeholder = 0
    skipped_blacklist = 0

    with pdfplumber.open(pdf_path) as pdf:
        bounds = detect_im_column_bounds(pdf.pages[0])
        for page_no, page in enumerate(pdf.pages, 1):
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            tables = [t for t in page.find_tables() if t.rows and len(t.rows[0].cells) == 9]
            if not tables:
                continue
            table = max(tables, key=lambda t: len(t.rows))

            for r_idx, row in enumerate(table.rows):
                if page_no == 1 and r_idx == 0:
                    continue
                y0, y1 = row.bbox[1], row.bbox[3]
                bins: list[list[dict]] = [[] for _ in range(9)]
                for w in words:
                    ym = 0.5 * (w["top"] + w["bottom"])
                    if y0 <= ym <= y1:
                        xm = 0.5 * (w["x0"] + w["x1"])
                        bins[col_index_for_x(xm, bounds)].append(w)

                cells = [join_cell_words(b) for b in bins]
                nr_crt = cells[0].rstrip(".")
                if not nr_crt.isdigit():
                    continue

                company = cells[2]
                cui = normalize_cui(cells[4])
                if not company or company == "0":
                    skipped_placeholder += 1
                    continue
                if is_blacklisted_company(company):
                    skipped_blacklist += 1
                    continue

                records.append(
                    {
                        "No.": len(records) + 1,
                        "Cong_Ty": company,
                        "Ma_Dinh_Danh_CUI": cui,
                        "So_TT_PDF": nr_crt,
                        "ITM_Tinh": cells[1],
                        "Ngay_Dang_Ky": "" if cells[3] == "0" else cells[3],
                        "Dia_Chi_Tru_So": "" if cells[5] == "0" else cells[5],
                        "Ma_Tinh": "" if cells[6] == "0" else cells[6],
                        "Chi_Nhanh_Diem_LV": "" if cells[7] == "0" else cells[7],
                        "Tinh_Diem_LV": "" if cells[8] == "0" else cells[8],
                        "Nguon_PDF": "Inspectia Muncii (31.01.2025)",
                    }
                )

    print(
        f"[PDF1 Inspectia Muncii] Extracted {len(records)} valid rows "
        f"(skipped placeholder='0': {skipped_placeholder}, blacklist: {skipped_blacklist})"
    )
    return records


def find_valid_pdf2() -> Path | None:
    """Locate a valid downloaded MMSS/AMT PDF in ro_romania/."""
    candidates = [RO_DIR / name for name in PDF2_CANDIDATE_NAMES]
    if RO_DIR.exists():
        for p in sorted(RO_DIR.glob("*.pdf")):
            if p.name != PDF1_PATH.name and p not in candidates:
                candidates.append(p)
    for p in candidates:
        if p.exists() and p.is_file():
            with open(p, "rb") as fp:
                if fp.read(5) == b"%PDF-":
                    return p
    return None


def _norm_hdr(text: str) -> str:
    n = unicodedata.normalize("NFKD", clean_text(text)).lower()
    return "".join(c for c in n if not unicodedata.combining(c))


def extract_ro_phones(raw_phone: str) -> tuple[str, str]:
    """Extract normalized Romanian phone/fax numbers, always prefixed with single quote (')."""
    s = clean_text(raw_phone)
    if not s or s == "0":
        return "", ""
    # Priority: compact 9-10 digits -> area-code+subscriber -> 3+ grouped blocks
    pattern = re.compile(
        r"(?:\+?40|0040|0)(?:"
        r"\d{8,10}"
        r"|\d{1,3}[ ./-]\d{5,8}"
        r"|\d{2,3}(?:[ ./-]\d{2,4}){2,3}"
        r")"
    )
    cleaned: list[str] = []
    seen: set[str] = set()
    for m in pattern.finditer(s):
        token = m.group(0)
        digits = re.sub(r"\D", "", token)
        if digits.startswith("0040"):
            digits = "+40" + digits[4:]
        elif token.strip().startswith("+40"):
            digits = "+40" + digits[2:]
        elif digits.startswith("40") and len(digits) >= 11:
            digits = "+40" + digits[2:]
        if 9 <= len(re.sub(r"\D", "", digits)) <= 13 and digits not in seen:
            seen.add(digits)
            cleaned.append(f"'{digits}")
    primary = cleaned[0] if cleaned else ""
    return primary, "; ".join(cleaned)


def split_amt_company_name(raw_name: str) -> tuple[str, str]:
    """Extract clean current legal name and optional former-name note from AMT PDF 2."""
    s = clean_text(raw_name)
    if not s:
        return "", ""

    # Pattern 1: "Schimbat denumirea în NEW_NAME [(date)] [începând cu ...] din OLD_NAME"
    m1 = re.match(
        r"^Schimbat\s+denumirea\s+[îi]n\s+(.+?)\s+"
        r"(?:\(\d{2}\.\d{2}\.\d{4}\)\s*)?"
        r"(?:[îi]ncep[âa]nd\s+cu[^,]*,?\s*)?"
        r"(?:\(\d{2}\.\d{2}\.\d{4}\)\s*)?din\s+(.+)$",
        s,
        flags=re.I,
    )
    if m1:
        old = clean_text(m1.group(2).strip(" ,;-"))
        return clean_text(m1.group(1).strip(" ,;-")), old

    # Pattern 2: "NEW_NAME (Schimbare/schimbat denumire[a] din OLD_NAME)" or without parens
    m2 = re.match(
        r"^(.+?)\s*\(?(?:Schimbare|Schimbat[ăa]?)\s+denumire[aă]?\s+din\s+(.+)$",
        s,
        flags=re.I,
    )
    if m2:
        new_name = clean_text(m2.group(1).strip(" ,;-("))
        old_name = clean_text(m2.group(2).strip(" ,;-"))
        # Drop unmatched trailing ')' left over from an outer "(Schimbare denumire din ...)" wrapper
        if old_name.endswith(")") and old_name.count(")") > old_name.count("("):
            old_name = old_name[:-1].strip()
        return new_name, old_name

    return s, ""


def extract_mmuncii_amt_pdf(pdf_path: Path) -> list[dict]:
    """Extract and merge all multi-page AMT register records from Reg-Nat-al-AMT PDF."""
    merged_raw: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = [t for t in (page.extract_tables() or []) if t and len(t[0]) == 8]
            if not tables:
                continue
            table = tables[0]
            for raw_row in table:
                c = [clean_text(x) for x in raw_row]
                if not any(c):
                    continue
                c0 = c[0].rstrip(".")
                if c0 in ("Nr. crt", "Nr. crt.", "0") or c[1].lower().startswith("denumirea agentului"):
                    continue

                # Start a new record if row has Nr. crt. OR a non-empty Codul fiscal (e.g. unnumbered #38)
                if c0.isdigit() or bool(c[3]):
                    merged_raw.append(
                        {
                            "nr": c0,
                            "name": c[1],
                            "addr": c[2],
                            "cui": c[3],
                            "phone": c[4],
                            "auth": c[5],
                            "ext": c[6],
                            "withdrawn": c[7],
                        }
                    )
                elif merged_raw:
                    cur = merged_raw[-1]
                    for idx, key in (
                        (1, "name"),
                        (2, "addr"),
                        (4, "phone"),
                        (5, "auth"),
                        (6, "ext"),
                        (7, "withdrawn"),
                    ):
                        if c[idx]:
                            cur[key] = clean_text(f"{cur[key]} {c[idx]}") if cur[key] else c[idx]

    records: list[dict] = []
    skipped_blacklist = 0
    for item in merged_raw:
        clean_name, former_name = split_amt_company_name(item["name"])
        if not clean_name or clean_name == "0":
            continue
        if is_blacklisted_company(clean_name) or is_blacklisted_company(item["name"]):
            skipped_blacklist += 1
            continue

        cui = normalize_cui(item["cui"])
        primary_phone, all_phones = extract_ro_phones(item["phone"])
        status = "Retrasa / Expirata" if item["withdrawn"] else "Activ"

        records.append(
            {
                "No.": len(records) + 1,
                "Cong_Ty": clean_name,
                "Ma_Dinh_Danh_CUI": cui,
                "SDT": primary_phone,
                "Tat_Ca_SDT": all_phones,
                "So_TT_PDF": item["nr"],
                "ITM_Tinh": "",
                "Ngay_Dang_Ky": item["ext"],
                "Dia_Chi_Tru_So": item["addr"],
                "Ma_Tinh": "",
                "Chi_Nhanh_Diem_LV": item["auth"],
                "Tinh_Diem_LV": "",
                "Trang_Thai_AMT": status,
                "Ten_Khac_Hoac_Cu": former_name,
                "Ghi_Chu_Trang_Thai": item["withdrawn"],
                "Nguon_PDF": "Ministerul Muncii AMT (31.01.2026)",
            }
        )

    with_cui = sum(1 for r in records if r["Ma_Dinh_Danh_CUI"])
    print(
        f"[PDF2 MMSS AMT] Extracted {len(records)} merged rows "
        f"(With CUI: {with_cui}, blacklist skipped: {skipped_blacklist})"
    )
    return records


def _company_richness_key(name: str) -> tuple[int, int]:
    """Prefer full legal names containing SRL/SA over abbreviated duplicates."""
    has_legal = 1 if re.search(r"\bS\.?R\.?L\.?\b|\bS\.?A\.?\b", name, re.I) else 0
    return (has_legal, len(name))


def deduplicate_by_cui(records: list[dict]) -> list[dict]:
    """Consolidate duplicate CUI entries across counties and registries cleanly."""
    grouped: dict[str, dict] = {}
    order: list[str] = []

    for rec in records:
        cui_digits = re.sub(r"\D", "", rec.get("Ma_Dinh_Danh_CUI", ""))
        key = f"CUI:{cui_digits}" if cui_digits else f"NAME:{_norm_hdr(rec['Cong_Ty'])}"

        alt_names = [clean_text(x) for x in rec.get("Ten_Khac_Hoac_Cu", "").split("|") if clean_text(x)]
        if key not in grouped:
            grouped[key] = {
                "Cong_Ty": rec["Cong_Ty"],
                "Ma_Dinh_Danh_CUI": rec["Ma_Dinh_Danh_CUI"],
                "SDT": rec.get("SDT", ""),
                "ITM_Tinh": [rec["ITM_Tinh"]] if rec.get("ITM_Tinh") else [],
                "Ngay_Dang_Ky": rec.get("Ngay_Dang_Ky", ""),
                "Dia_Chi_Tru_So": rec.get("Dia_Chi_Tru_So", ""),
                "Ma_Tinh": [rec["Ma_Tinh"]] if rec.get("Ma_Tinh") else [],
                "Trang_Thai_AMT": rec.get("Trang_Thai_AMT", ""),
                "Nguon_PDF": [rec["Nguon_PDF"]] if rec.get("Nguon_PDF") else [],
                "Ten_Khac": alt_names,
                "Count": 1,
            }
            order.append(key)
        else:
            cur = grouped[key]
            cur["Count"] += 1
            cand_name = rec["Cong_Ty"]
            if cand_name != cur["Cong_Ty"]:
                if _company_richness_key(cand_name) > _company_richness_key(cur["Cong_Ty"]):
                    if cur["Cong_Ty"] not in cur["Ten_Khac"]:
                        cur["Ten_Khac"].append(cur["Cong_Ty"])
                    cur["Cong_Ty"] = cand_name
                elif cand_name not in cur["Ten_Khac"]:
                    cur["Ten_Khac"].append(cand_name)
            for an in alt_names:
                if an != cur["Cong_Ty"] and an not in cur["Ten_Khac"]:
                    cur["Ten_Khac"].append(an)
            for field in ("ITM_Tinh", "Ma_Tinh", "Nguon_PDF"):
                val = rec.get(field, "")
                if val and val not in cur[field]:
                    cur[field].append(val)
            if not cur["SDT"] and rec.get("SDT"):
                cur["SDT"] = rec["SDT"]
            if not cur["Trang_Thai_AMT"] and rec.get("Trang_Thai_AMT"):
                cur["Trang_Thai_AMT"] = rec["Trang_Thai_AMT"]
            if not cur["Dia_Chi_Tru_So"] and rec.get("Dia_Chi_Tru_So"):
                cur["Dia_Chi_Tru_So"] = rec["Dia_Chi_Tru_So"]

    unique_rows: list[dict] = []
    for idx, k in enumerate(order, 1):
        g = grouped[k]
        unique_rows.append(
            {
                "No.": idx,
                "Cong_Ty": g["Cong_Ty"],
                "Ma_Dinh_Danh_CUI": g["Ma_Dinh_Danh_CUI"],
                "SDT": g["SDT"],
                "Trang_Thai_AMT": g["Trang_Thai_AMT"],
                "ITM_Tinh": " | ".join(g["ITM_Tinh"]),
                "Ma_Tinh": " | ".join(g["Ma_Tinh"]),
                "Ngay_Dang_Ky": g["Ngay_Dang_Ky"],
                "Dia_Chi_Tru_So": g["Dia_Chi_Tru_So"],
                "So_Ban_Ghi_PDF": g["Count"],
                "Ten_Khac_Hoac_Cu": " | ".join(g["Ten_Khac"]),
                "Nguon_PDF": " | ".join(g["Nguon_PDF"]),
            }
        )
    return unique_rows


def export_csv(records: list[dict], out_path: Path) -> None:
    """Write CSV strictly encoded as UTF-8 with BOM (utf-8-sig)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records).fillna("")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  -> Saved {len(df)} rows to {out_path}")


def main() -> None:
    os.makedirs(RO_DIR, exist_ok=True)
    all_records: list[dict] = []

    if PDF1_PATH.exists():
        pdf1_records = extract_inspectia_muncii_pdf(PDF1_PATH)
        export_csv(pdf1_records, OUT_PDF1_RAW)
        all_records.extend(pdf1_records)
    else:
        print(f"[WARN] Missing PDF1: {PDF1_PATH}")

    pdf2_path = find_valid_pdf2()
    if pdf2_path:
        pdf2_records = extract_mmuncii_amt_pdf(pdf2_path)
        if pdf2_records:
            export_csv(pdf2_records, OUT_PDF2_RAW)
            all_records.extend(pdf2_records)
            merged_out = [dict(r) for r in all_records]
            for idx, r in enumerate(merged_out, 1):
                r["No."] = idx
            export_csv(merged_out, OUT_MERGED_RAW)
    else:
        print(
            "\n[NOTICE] Chua tim thay file PDF thu 2 (mmuncii.gov.ro - Reg-Nat-al-AMT-la-31.01.2026.pdf).\n"
            "  Link nay dang bat cong kiem tra trinh duyet anti-bot ('Verifying your browser...' HTTP 503).\n"
            "  Hay mo link trong trinh duyet cua ban va luu file PDF vao:\n"
            f"    {RO_DIR / PDF2_CANDIDATE_NAMES[0]}\n"
            "  Sau do chay lai script nay de tu dong boc tach & gop ca 2 danh sach."
        )

    if all_records:
        unique_rows = deduplicate_by_cui(all_records)
        export_csv(unique_rows, OUT_UNIQ_CUI)
        with_cui = sum(1 for r in unique_rows if r["Ma_Dinh_Danh_CUI"])
        print(
            f"\n[SUMMARY] Unique companies: {len(unique_rows)} | With CUI: {with_cui} | Missing CUI: {len(unique_rows) - with_cui}"
        )


if __name__ == "__main__":
    main()

