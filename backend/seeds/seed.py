"""Deterministic seed corpus.

The corpus is designed for the leak tests, not for demos. It contains a
compensation document readable only by HR and Admin carrying a canary phrase
that appears nowhere else, plus a public document that everyone can read.

Both are necessary. Without the public document you cannot distinguish a working
filter from one that blocks everything, and a filter that blocks everything
passes every negative test you can write.
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionLocal, engine
from app.models import Base, Document, Role, Tenant, User
from app.services.ingest import Labels, ingest_document

CANARY = "Project Nightingale severance multiplier is 2.4x base salary"

ROLES = [("Admin", 100), ("HR", 60), ("Engineering", 40), ("Intern", 10)]

USERS = [
    ("admin@acme.test", "Admin"),
    ("hr@acme.test", "HR"),
    ("eng@acme.test", "Engineering"),
    ("intern@acme.test", "Intern"),
]

DOCS = [
    (
        "Executive_Compensation_2026.md",
        ["HR"], 60,
        f"""# Executive compensation review 2026

## Severance provisions

{CANARY}. This applies to all officers listed in schedule B.

## Base salary bands

The chief executive officer band for fiscal 2026 is 940,000 dollars, reviewed
annually by the compensation committee.
""",
    ),
    (
        "Employee_Handbook.md",
        ["Intern", "Engineering", "HR"], 0,
        """# Employee handbook

## Expenses

The travel allowance is 300 dollars per trip. Submit receipts within 30 days.

## Facilities

The coffee machine is on floor two. Parking passes are issued by facilities.
""",
    ),
    (
        "Q3_Hiring_Plan.md",
        ["Engineering", "HR"], 40,
        """# Q3 hiring plan

Engineering will open 12 requisitions in Q3, weighted toward platform and
security. Two are backfills.
""",
    ),
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.name == "acme"))).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(id=uuid.uuid4(), name="acme")
            db.add(tenant)
            await db.commit()

        role_ids: dict[str, uuid.UUID] = {}
        for name, level in ROLES:
            existing = (await db.execute(
                select(Role).where(Role.tenant_id == tenant.id, Role.name == name)
            )).scalar_one_or_none()
            if existing is None:
                existing = Role(id=uuid.uuid4(), tenant_id=tenant.id,
                                name=name, clearance_level=level)
                db.add(existing)
                await db.commit()
            role_ids[name] = existing.id

        admin_id = None
        for email, role_name in USERS:
            existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if existing is None:
                existing = User(id=uuid.uuid4(), tenant_id=tenant.id, email=email,
                                hashed_password=hash_password("devpassword"),
                                role_id=role_ids[role_name])
                db.add(existing)
                await db.commit()
            if role_name == "Admin":
                admin_id = existing.id

        for filename, roles, clearance, text in DOCS:
            existing = (await db.execute(
                select(Document).where(Document.filename == filename)
            )).scalar_one_or_none()
            if existing:
                continue
            doc_id = uuid.uuid4()
            db.add(Document(id=doc_id, tenant_id=tenant.id, filename=filename,
                            storage_key=f"seed://{filename}", uploaded_by=admin_id,
                            min_clearance=clearance, status="pending"))
            await db.commit()
            await ingest_document(db, document_id=str(doc_id), tenant_id=str(tenant.id),
                                  filename=filename, raw_text=text,
                                  labels=Labels(roles, clearance))

    print("seeded. canary phrase:")
    print(f'  "{CANARY}"')
    print("verify with:")
    print(f'  python scripts/verify_rbac.py --canary "Project Nightingale severance"')


if __name__ == "__main__":
    asyncio.run(main())
