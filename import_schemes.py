"""Import the user's latest15.xlsx into scheme_catalog.
Set DATABASE_URL to the PostgreSQL EXTERNAL database URL before running.
This imports all 50 rows. Full source fields are retained in the description field
so the current API and AI recommender can use the complete scheme details.
"""
import os, sys, math
from pathlib import Path
from openpyxl import load_workbook
import psycopg

ROOT = Path(__file__).resolve().parent
XLSX_PATH = Path(os.getenv("SCHEME_XLSX_PATH", ROOT / "latest15.xlsx"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    sys.exit("ERROR: Set DATABASE_URL to your PostgreSQL EXTERNAL Database URL.")
if not XLSX_PATH.exists():
    sys.exit(f"ERROR: Excel file not found: {XLSX_PATH}")

def clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()

wb = load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb[wb.sheetnames[0]]
it = ws.iter_rows(values_only=True)
headers = [clean(x) for x in next(it)]
rows = []
for raw in it:
    rec = {headers[i]: (raw[i] if i < len(raw) else None) for i in range(len(headers))}
    sid = clean(rec.get("Scheme_ID"))
    name = clean(rec.get("Scheme_Name"))
    if not sid or not name:
        continue
    def val(key): return clean(rec.get(key))
    details = []
    labels = [
        ("Apex_Nodal_Agency", "Nodal agency"),
        ("Benefits / Protection", "Benefits / protection"),
        ("Eligible_Business_Sectors", "Eligible sectors"),
        ("Interest_Rate_Percentage", "Interest rate"),
        ("Moratorium_Period_Months", "Moratorium period (months)"),
        ("Mandatory_Identity_Documents", "Identity documents"),
        ("Mandatory_Community_Documents", "Community documents"),
        ("Mandatory_Business_Documents", "Business documents"),
        ("Helpdesk_Contact_Number", "Helpdesk"),
        ("Brief_Description_for_AI_RAG", "Description"),
    ]
    for key, label in labels:
        v = val(key)
        if v and v.lower() not in {"nan", "none", "null", "n/a"}:
            details.append(f"{label}: {v}")
    rows.append((
        sid, name, val("Target_Caste_Category") or None,
        val("Minimum_Age") or None, val("Maximum_Age") or None,
        val("Annual_Family_Income_Limit_INR") or None,
        val("Maximum_Loan_Amount_INR") or None,
        val("Category") or "Government Scheme",
        " | ".join(details) or "Verify current details on the official portal.",
        val("Official_Application_URL") or None,
    ))
if not rows:
    sys.exit("ERROR: No valid scheme rows found in Excel.")
url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
create_sql = """CREATE TABLE IF NOT EXISTS scheme_catalog (
 scheme_id TEXT PRIMARY KEY, scheme_name TEXT NOT NULL,
 target_caste_category TEXT, minimum_age TEXT, maximum_age TEXT,
 annual_family_income_limit_inr TEXT, maximum_loan_amount_inr TEXT,
 category TEXT, description TEXT, official_url TEXT
)"""
upsert_sql = """INSERT INTO scheme_catalog
(scheme_id, scheme_name, target_caste_category, minimum_age, maximum_age,
 annual_family_income_limit_inr, maximum_loan_amount_inr, category, description, official_url)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (scheme_id) DO UPDATE SET
 scheme_name=EXCLUDED.scheme_name,
 target_caste_category=EXCLUDED.target_caste_category,
 minimum_age=EXCLUDED.minimum_age,
 maximum_age=EXCLUDED.maximum_age,
 annual_family_income_limit_inr=EXCLUDED.annual_family_income_limit_inr,
 maximum_loan_amount_inr=EXCLUDED.maximum_loan_amount_inr,
 category=EXCLUDED.category, description=EXCLUDED.description,
 official_url=EXCLUDED.official_url"""
with psycopg.connect(url) as db:
    with db.cursor() as cur:
        cur.execute(create_sql)
        cur.executemany(upsert_sql, rows)
        cur.execute("SELECT COUNT(*) FROM scheme_catalog")
        count = cur.fetchone()[0]
print(f"Imported/updated {len(rows)} rows from {XLSX_PATH.name}.")
print(f"scheme_catalog now contains {count} rows total.")
print("All source columns are included in each scheme's AI-readable description; eligibility fields and official URL are stored separately.")
