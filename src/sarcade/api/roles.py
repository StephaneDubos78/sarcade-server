"""Who am I, and the lists of administrators and PCO (console)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sarcade import roles
from sarcade.access.verify import identity_of
from sarcade.security import journal

from .deps import get_db

router = APIRouter(prefix="/api/v0.1")


def checked_email(request: Request) -> str | None:
    identity = identity_of(request)
    return identity.email.strip().lower() if identity is not None and identity.email else None


def require_pco(request: Request, db: Session = Depends(get_db)) -> str | None:
    """PCO or administrator when the email is checked (Cloudflare Access).
    Without a checked email (local network without Access) the server
    cannot know who calls: the previous behaviour is kept."""
    email = checked_email(request)
    if email is None:
        return None
    if "pco" not in roles.roles_of(db, email):
        journal.record(db, "rights", "pco_required", "failure",
                       details={"path": request.url.path[:120], "email": email})
        db.commit()
        raise HTTPException(status_code=403, detail="pco_required")
    return email


def require_admin_email(request: Request, db: Session = Depends(get_db)) -> str:
    email = checked_email(request)
    if email is None or "admin" not in roles.roles_of(db, email):
        raise HTTPException(status_code=403, detail="admin_required")
    return email


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    email = checked_email(request)
    return {"email": email, "checked": email is not None, "roles": roles.roles_of(db, email)}


class RolesIn(BaseModel):
    admins: list[str]
    pco: list[str]


@router.get("/admin/roles")
def get_roles(_admin: str = Depends(require_admin_email), db: Session = Depends(get_db)):
    return {**roles.stored(db), "env_admins": roles.env_admins()}


@router.put("/admin/roles")
def put_roles(body: RolesIn, admin: str = Depends(require_admin_email), db: Session = Depends(get_db)):
    try:
        out = roles.save(db, body.admins, body.pco)
    except roles.InvalidRoles as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    journal.record(db, "admin", "roles_changed", "success",
                   details={"by": admin, "admins": len(out["admins"]), "pco": len(out["pco"])})
    db.commit()
    return {**out, "env_admins": roles.env_admins()}
