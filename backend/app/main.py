from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
import os
import csv
import io
import json
import secrets
from fastapi import UploadFile, File
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Integer, String, DateTime, select, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://careerflow:careerflow@localhost:5432/careerflow')
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class Application(Base):
    __tablename__ = 'applications'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default='saved')
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ImportedApplication(Base):
    __tablename__ = 'imported_applications'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(120), default='google_sheet')
    source_row: Mapped[int] = mapped_column(Integer)
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id', ondelete='CASCADE'))
    details: Mapped[str] = mapped_column(String(12000))
    __table_args__ = (UniqueConstraint('source', 'source_row'),)

class Status(str, Enum):
    saved = 'saved'
    applied = 'applied'
    interview = 'interview'
    offer = 'offer'
    rejected = 'rejected'

class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    status: Status = Status.saved
    url: str | None = Field(default=None, max_length=1000)

class ApplicationUpdate(BaseModel):
    status: Status

class ApplicationOut(ApplicationCreate):
    id: int
    created_at: datetime
    model_config = {'from_attributes': True}

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # MVP only; replace with Alembic migrations
    yield

app = FastAPI(title='CareerFlow API', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    with SessionLocal() as session:
        yield session

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.get('/applications', response_model=list[ApplicationOut])
def list_applications(db: Session = Depends(get_db)):
    return db.scalars(select(Application).order_by(Application.created_at.desc())).all()

@app.post('/applications', response_model=ApplicationOut, status_code=201)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)):
    item = Application(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@app.patch('/applications/{application_id}', response_model=ApplicationOut)
def update_application(application_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)):
    item = db.get(Application, application_id)
    if item is None:
        raise HTTPException(404, 'Application not found')
    item.status = payload.status.value
    db.commit()
    db.refresh(item)
    return item

@app.delete('/applications/{application_id}', status_code=204)
def delete_application(application_id: int, db: Session = Depends(get_db)):
    item = db.get(Application, application_id)
    if item is None:
        raise HTTPException(404, 'Application not found')
    db.delete(item)
    db.commit()


@app.post('/imports/google-sheet-csv')
async def import_google_sheet_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import the user's Sheet1 CSV. Reimports update existing imported rows, never duplicate them."""
    raw = await file.read()
    if len(raw) > 8_000_000:
        raise HTTPException(413, 'CSV is too large')
    try:
        content = raw.decode('utf-8-sig')
        rows = list(csv.reader(io.StringIO(content)))
    except (UnicodeDecodeError, csv.Error):
        raise HTTPException(400, 'Please upload a UTF-8 CSV export')
    if not rows or len(rows[0]) < 11 or rows[0][2].strip().upper() != 'COMPANY':
        raise HTTPException(400, 'Expected the Google Sheet with COMPANY in column C and STATUS in column K')
    created = updated = skipped = 0
    for row_number, row in enumerate(rows[1:], start=2):
        def col(n):
            return (row[n].strip() if len(row) > n else '')
        company = col(2)
        if not company:
            skipped += 1
            continue
        raw_status = col(10).lower()
        if 'reject' in raw_status:
            status = 'rejected'
        elif 'offer' in raw_status or raw_status == 'accepted':
            status = 'offer'
        elif 'interview' in raw_status or 'initial call' in raw_status:
            status = 'interview'
        elif raw_status in ('application', 'applied'):
            status = 'applied'
        else:
            status = 'saved'
        details = {name: col(idx) for name, idx in {
            'date':0,'claude_link':1,'role_id':4,'location':5,'salary':6,
            'resume_saved_as':7,'hr_name':8,'hr_email':9,'original_status':10,
            'latest_update':11,'extra_notes':12,'recruiter_reference':13,
            'contact':14,'phone_number':15,'mutual':16,'claude_link_extra':17}.items()}
        existing = db.scalar(select(ImportedApplication).where(
            ImportedApplication.source == 'google_sheet', ImportedApplication.source_row == row_number))
        if existing:
            item = db.get(Application, existing.application_id)
            if item is None:
                skipped += 1
                continue
            updated += 1
        else:
            item = Application(
    		company=company[:120],
    		role=(col(3) or 'Role not specified')[:160],
   		status=status,
    		url=col(1)[:1000] or None
	    )
            db.add(item)
            db.flush()
            existing = ImportedApplication(source='google_sheet', source_row=row_number,
                                           application_id=item.id, details='{}')
            db.add(existing)
            created += 1
        item.company = company[:120]
        item.role = (col(3) or 'Role not specified')[:160]
        item.status = status
        item.url = col(1)[:1000] or None
        existing.details = json.dumps(details)
    db.commit()
    return {'created': created, 'updated': updated, 'skipped': skipped}

@app.get('/applications/{application_id}/import-details')
def import_details(application_id: int, db: Session = Depends(get_db)):
    record = db.scalar(select(ImportedApplication).where(ImportedApplication.application_id == application_id))
    if not record:
        raise HTTPException(404, 'No imported details for this application')
    return json.loads(record.details)


class ApplicationDetailsUpdate(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(max_length=160)
    status: Status
    url: str | None = Field(default=None, max_length=1000)
    details: dict[str, str] = Field(default_factory=dict)

@app.get('/applications-with-details')
def list_applications_with_details(db: Session = Depends(get_db)):
    records = db.execute(select(Application, ImportedApplication).outerjoin(
        ImportedApplication, ImportedApplication.application_id == Application.id
    ).order_by(Application.id.desc())).all()
    return [dict(id=item.id, company=item.company, role=item.role, status=item.status,
                 url=item.url, created_at=item.created_at.isoformat(),
                 details=json.loads(imported.details) if imported else {})
            for item, imported in records]

@app.put('/applications/{application_id}/full')
def update_full_application(application_id: int, payload: ApplicationDetailsUpdate, db: Session = Depends(get_db)):
    item = db.get(Application, application_id)
    if item is None:
        raise HTTPException(404, 'Application not found')
    item.company = payload.company
    item.role = payload.role
    item.status = payload.status.value
    item.url = payload.url
    imported = db.scalar(select(ImportedApplication).where(ImportedApplication.application_id == application_id))
    if not imported:
        imported = ImportedApplication(source='manual', source_row=application_id,
                                       application_id=application_id, details='{}')
        db.add(imported)
    imported.details = json.dumps({str(k): str(v)[:5000] for k,v in payload.details.items()})
    db.commit()
    return {'updated': True}


# Integration endpoints for a trusted automation client. The existing browser API
# remains local-development only; do not publish this server as-is.
DETAIL_KEYS = {
    'date', 'claude_link', 'role_id', 'location', 'salary',
    'resume_saved_as', 'hr_name', 'hr_email', 'original_status',
    'latest_update', 'extra_notes', 'recruiter_reference', 'contact',
    'phone_number', 'mutual', 'claude_link_extra',
}


def require_integration_key(authorization: str | None = Header(default=None)):
    expected = os.getenv('CAREERFLOW_API_KEY', '')
    if not expected or not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Valid integration API key required')
    if not secrets.compare_digest(authorization[7:], expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Invalid integration API key')


class IntegrationApplication(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=160)
    status: Status = Status.applied
    url: str | None = Field(default=None, max_length=1000)
    details: dict[str, str] = Field(default_factory=dict)


class IntegrationPatch(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=160)
    status: Status | None = None
    url: str | None = Field(default=None, max_length=1000)
    details: dict[str, str] | None = None


def sanitize_details(details: dict[str, str]) -> dict[str, str]:
    unknown = set(details) - DETAIL_KEYS
    if unknown:
        raise HTTPException(422, f'Unknown details fields: {sorted(unknown)}')
    return {key: value[:5000] for key, value in details.items()}


def full_record(db: Session, item: Application) -> dict:
    imported = db.scalar(select(ImportedApplication).where(ImportedApplication.application_id == item.id))
    return dict(id=item.id, company=item.company, role=item.role,
                status=item.status, url=item.url,
                created_at=item.created_at.isoformat(),
                details=json.loads(imported.details) if imported else {})


def find_duplicate(db: Session, company: str, role: str, role_id: str):
    # Only match a precise company+role combination; when a requisition ID is
    # supplied, require it to match too so distinct openings are preserved.
    candidates = db.scalars(select(Application).where(
        Application.company.ilike(company.strip()),
        Application.role.ilike(role.strip()))).all()
    for candidate in candidates:
        imported = db.scalar(select(ImportedApplication).where(
            ImportedApplication.application_id == candidate.id))
        details = json.loads(imported.details) if imported else {}
        if role_id:
            if details.get('role_id', '').strip().casefold() == role_id.strip().casefold():
                return candidate
        elif not details.get('role_id', '').strip():
            return candidate
    return None


@app.get('/api/applications', dependencies=[Depends(require_integration_key)])
def integration_list(db: Session = Depends(get_db)):
    return [full_record(db, item) for item in db.scalars(select(Application).order_by(Application.id.desc())).all()]


@app.get('/api/applications/{application_id}', dependencies=[Depends(require_integration_key)])
def integration_get(application_id: int, db: Session = Depends(get_db)):
    item = db.get(Application, application_id)
    if item is None:
        raise HTTPException(404, 'Application not found')
    return full_record(db, item)


@app.post('/api/applications', status_code=201, dependencies=[Depends(require_integration_key)])
def integration_create(payload: IntegrationApplication, db: Session = Depends(get_db)):
    details = sanitize_details(payload.details)
    duplicate = find_duplicate(db, payload.company, payload.role, details.get('role_id', ''))
    if duplicate is not None:
        raise HTTPException(409, detail={'message': 'Possible duplicate application', 'existing_id': duplicate.id})
    item = Application(company=payload.company.strip(), role=payload.role.strip(),
                       status=payload.status.value, url=payload.url)
    db.add(item)
    db.flush()
    db.add(ImportedApplication(source='integration', source_row=item.id,
                               application_id=item.id, details=json.dumps(details)))
    db.commit()
    db.refresh(item)
    return full_record(db, item)


@app.patch('/api/applications/{application_id}', dependencies=[Depends(require_integration_key)])
def integration_update(application_id: int, payload: IntegrationPatch, db: Session = Depends(get_db)):
    item = db.get(Application, application_id)
    if item is None:
        raise HTTPException(404, 'Application not found')
    updates = payload.model_dump(exclude_unset=True)
    for key in ('company', 'role', 'url'):
        if key in updates:
            setattr(item, key, updates[key])
    if 'status' in updates and updates['status'] is not None:
        item.status = updates['status'].value
    if 'details' in updates and updates['details'] is not None:
        incoming = sanitize_details(updates['details'])
        imported = db.scalar(select(ImportedApplication).where(
            ImportedApplication.application_id == item.id))
        if imported is None:
            imported = ImportedApplication(source='integration', source_row=item.id,
                                           application_id=item.id, details='{}')
            db.add(imported)
        current = json.loads(imported.details)
        current.update(incoming)
        imported.details = json.dumps(current)
    db.commit()
    db.refresh(item)
    return full_record(db, item)
