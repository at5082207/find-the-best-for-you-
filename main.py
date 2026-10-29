import os, sqlite3, secrets, hashlib, hmac, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data.sqlite3"))
app = FastAPI(title="Find the Best for You API", version="1.0.0",
              description="Backend for government scheme discovery, eligibility, saved schemes and EMI calculations.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

SCHEMES = [
 {"id":"pmmy","name":"Pradhan Mantri Mudra Yojana","category":"Loan / Self Employment","description":"Business loans through participating lenders, subject to lender rules.","url":"https://www.mudra.org.in/"},
 {"id":"pmvishwakarma","name":"PM Vishwakarma","category":"Skill / Business","description":"Support for eligible traditional artisans and craftspeople.","url":"https://pmvishwakarma.gov.in/"},
 {"id":"pmay","name":"Pradhan Mantri Awas Yojana","category":"Housing","description":"Housing assistance under the applicable rural or urban programme.","url":"https://pmaymis.gov.in/"},
 {"id":"scholarship","name":"National Scholarship Portal","category":"Education","description":"Search scholarships and check the current eligibility rules.","url":"https://scholarships.gov.in/"},
 {"id":"udyam","name":"Udyam Registration","category":"MSME / Business","description":"Official MSME registration portal.","url":"https://udyamregistration.gov.in/"},
 {"id":"pmkisan","name":"PM-KISAN","category":"Agriculture","description":"Income support programme for eligible landholding farmer families.","url":"https://pmkisan.gov.in/"},
]
def conn():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c
def init_db():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT, dob TEXT, password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS saved_schemes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, scheme_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id,scheme_id));
        CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, scheme_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Saved for review', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, message TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
init_db()
def now(): return datetime.now(timezone.utc).isoformat()
def password_hash(password, salt): return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()
def public_user(row): return {"id":row["id"],"name":row["name"],"email":row["email"],"phone":row["phone"],"dob":row["dob"]}
def make_session(uid):
    token=secrets.token_urlsafe(36); digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        c.execute("INSERT INTO sessions VALUES(?,?,?)",(digest,uid,(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()))
    return token
def current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Login required")
    token=authorization[7:].strip(); digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        row=c.execute("SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>?",(digest,now())).fetchone()
    if not row: raise HTTPException(401,"Session expired. Please log in again.")
    return row

class Register(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    email:EmailStr
    password:str=Field(min_length=8,max_length=128)
    phone:str=Field(min_length=7,max_length=20)
    dob:str=Field(min_length=4,max_length=20)
class Login(BaseModel):
    email:EmailStr
    password:str=Field(min_length=1,max_length=128)
class SearchRequest(BaseModel):
    query:str=Field(min_length=1,max_length=200)
class EMIRequest(BaseModel):
    principal:float=Field(gt=0,le=1000000000)
    annual_rate:float=Field(ge=0,le=100)
    months:int=Field(gt=0,le=600)
class EligibilityRequest(BaseModel):
    age:int=Field(ge=0,le=120)
    annual_income:float=Field(ge=0)
    category:str="General"
    state:str="Uttar Pradesh"
    purpose:str="education"
class SaveRequest(BaseModel):
    scheme_id:str=Field(min_length=1,max_length=100)
class FeedbackRequest(BaseModel):
    message:str=Field(min_length=3,max_length=3000)

@app.get("/api/health")
def health(): return {"status":"ok","service":"Find the Best for You API","time":now()}
@app.post("/api/auth/register")
def register(data:Register):
    email=str(data.email).lower().strip(); salt=secrets.token_hex(16); hashed=password_hash(data.password,salt)
    try:
        with conn() as c:
            cur=c.execute("INSERT INTO users(name,email,phone,dob,password_hash,salt,created_at) VALUES(?,?,?,?,?,?,?)",
              (data.name.strip(),email,data.phone.strip(),data.dob,hashed,salt,now()))
            uid=cur.lastrowid
    except sqlite3.IntegrityError: raise HTTPException(409,"An account with this email already exists.")
    return {"token":make_session(uid),"user":{"id":uid,"name":data.name.strip(),"email":email,"phone":data.phone.strip(),"dob":data.dob}}
@app.post("/api/auth/login")
def login(data:Login):
    with conn() as c: row=c.execute("SELECT * FROM users WHERE email=?",(str(data.email).lower().strip(),)).fetchone()
    if not row or not hmac.compare_digest(password_hash(data.password,row["salt"]),row["password_hash"]):
        raise HTTPException(401,"Email or password is incorrect.")
    return {"token":make_session(row["id"]),"user":public_user(row)}
@app.post("/api/auth/logout")
def logout(user=Depends(current_user),authorization: str=Header(...)):
    token=authorization[7:].strip()
    with conn() as c: c.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
    return {"ok":True}
@app.get("/api/me")
def me(user=Depends(current_user)): return {"user":public_user(user)}
@app.get("/api/schemes")
def list_schemes(q:str="", category:str=""):
    q=q.strip().lower(); category=category.strip().lower()
    items=[x for x in SCHEMES if (not q or q in (x["name"]+" "+x["category"]+" "+x["description"]).lower()) and (not category or category in x["category"].lower())]
    return {"count":len(items),"schemes":items}
@app.post("/api/search")
def search(data:SearchRequest):
    q=data.query.lower().strip()
    matches=[x for x in SCHEMES if any(term in (x["name"]+" "+x["category"]+" "+x["description"]).lower() for term in q.split())]
    return {"query":data.query,"count":len(matches),"results":matches,"message":"These are catalogue matches. Confirm current rules on the official scheme website."}
@app.post("/api/emi")
def calculate_emi(data:EMIRequest):
    r=data.annual_rate/1200
    emi=data.principal/data.months if r==0 else data.principal*r*(1+r)**data.months/((1+r)**data.months-1)
    total=emi*data.months
    return {"monthly_emi":round(emi,2),"total_interest":round(total-data.principal,2),"total_payment":round(total,2),"principal":data.principal,"annual_rate":data.annual_rate,"months":data.months}
@app.post("/api/eligibility")
def eligibility(data:EligibilityRequest):
    # This is a preliminary matching helper, not an official eligibility decision.
    matches=[]
    for item in SCHEMES:
        hay=(item["name"]+" "+item["category"]+" "+item["description"]).lower()
        if data.purpose.lower() in hay or (data.purpose.lower()=="business" and any(w in hay for w in ["business","msme","loan"])) or (data.purpose.lower()=="education" and "education" in hay):
            matches.append(item)
    return {"preliminary_matches":matches,"disclaimer":"This is only a preliminary search. Eligibility depends on official scheme rules and documents. Verify on the official portal."}
@app.get("/api/saved")
def saved(user=Depends(current_user)):
    with conn() as c: rows=c.execute("SELECT scheme_id,created_at FROM saved_schemes WHERE user_id=? ORDER BY id DESC",(user["id"],)).fetchall()
    return {"items":[dict(r) for r in rows]}
@app.post("/api/saved")
def save(data:SaveRequest,user=Depends(current_user)):
    if not any(x["id"]==data.scheme_id for x in SCHEMES): raise HTTPException(404,"Scheme not found in current catalogue.")
    with conn() as c: c.execute("INSERT OR IGNORE INTO saved_schemes(user_id,scheme_id,created_at) VALUES(?,?,?)",(user["id"],data.scheme_id,now()))
    return {"ok":True,"items":saved(user)["items"]}
@app.delete("/api/saved/{scheme_id}")
def unsave(scheme_id:str,user=Depends(current_user)):
    with conn() as c: c.execute("DELETE FROM saved_schemes WHERE user_id=? AND scheme_id=?",(user["id"],scheme_id))
    return {"ok":True}
@app.get("/api/applications")
def applications(user=Depends(current_user)):
    with conn() as c: rows=c.execute("SELECT id,scheme_id,status,created_at FROM applications WHERE user_id=? ORDER BY id DESC",(user["id"],)).fetchall()
    return {"items":[dict(r) for r in rows]}
@app.post("/api/applications")
def add_application(data:SaveRequest,user=Depends(current_user)):
    if not any(x["id"]==data.scheme_id for x in SCHEMES): raise HTTPException(404,"Scheme not found in current catalogue.")
    with conn() as c:
        c.execute("INSERT INTO applications(user_id,scheme_id,status,created_at) VALUES(?,?,?,?)",(user["id"],data.scheme_id,"Saved for review",now()))
        row=c.execute("SELECT id,scheme_id,status,created_at FROM applications WHERE id=last_insert_rowid()").fetchone()
    return {"application":dict(row)}
@app.post("/api/feedback")
def feedback(data:FeedbackRequest,user=Depends(current_user)):
    with conn() as c: c.execute("INSERT INTO feedback(user_id,message,created_at) VALUES(?,?,?)",(user["id"],data.message.strip(),now()))
    return {"ok":True,"message":"Feedback received"}
@app.post("/api/documents/check")
async def check_document(file:UploadFile=File(...),user=Depends(current_user)):
    allowed={"application/pdf","image/jpeg","image/png","application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/msword"}
    if file.content_type not in allowed: raise HTTPException(415,"Upload a PDF, image, DOC or DOCX file.")
    content=await file.read(8*1024*1024+1)
    if len(content)>8*1024*1024: raise HTTPException(413,"Maximum file size is 8 MB.")
    # No file is saved. OCR and document interpretation are not enabled in this MVP.
    return {"filename":file.filename,"size_bytes":len(content),"received":True,"message":"File received and discarded. OCR/document analysis is not enabled yet."}

FRONTEND=ROOT/"frontend"
if FRONTEND.exists(): app.mount("/static",StaticFiles(directory=FRONTEND),name="static")
@app.get("/")
def home():
    file=FRONTEND/"index.html"
    if not file.exists(): raise HTTPException(404,"Frontend file is missing.")
    return FileResponse(file)
