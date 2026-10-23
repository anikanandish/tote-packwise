import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AdminCodeIn, LoginIn, RegisterIn, WorkerLoginIn
from ..config import settings
from ..security import (Principal, admin_throttle, check_admin_code, check_worker_code, create_session, end_session,
                        hash_password, require_principal, verify_password)
from ..services import audit

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


@router.post("/register", status_code=201, summary="Create a customer account")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=body.email, name=body.name.strip(), password_hash=hash_password(body.password), role="customer")
    db.add(user)
    db.commit()
    token = create_session(db, "customer", user)
    return {"token": token, "role": "customer", "user": _user_out(user)}


@router.post("/login", summary="Sign in a TOTE customer with email + password")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password.")
    if user.role != "customer":
        # Admin access is only through the admin access code in the PackWise admin console.
        raise HTTPException(403, "This account cannot sign in to the shop. Administrators use the PackWise admin console.")
    token = create_session(db, user.role, user)
    return {"token": token, "role": user.role, "user": _user_out(user)}


@router.post("/worker", summary="Warehouse worker access with the shared worker code")
def worker_login(body: WorkerLoginIn, db: Session = Depends(get_db)):
    if not check_worker_code(body.code.strip()):
        audit.log(db, "auth", "worker_login_failed", f"worker:{body.worker_name}")
        db.commit()
        raise HTTPException(401, "That worker code is not valid.")
    name = body.worker_name.strip()
    token = create_session(db, "worker", worker_name=name)
    audit.log(db, "auth", "worker_login", f"worker:{name}")
    db.commit()
    return {"token": token, "role": "worker", "user": {"name": name, "role": "worker"}}


@router.post("/admin", summary="Open the admin console with the admin access code (ADMIN_ACCESS_CODE)")
def admin_login(body: AdminCodeIn, request: Request, db: Session = Depends(get_db)):
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    wait = admin_throttle.locked_for(key, now)
    if wait > 0:
        raise HTTPException(429, f"Too many wrong codes. Try again in {int(wait) + 1} seconds.")
    if not settings.admin_access_code:
        raise HTTPException(503, "The admin console is locked: ADMIN_ACCESS_CODE is not set in backend/.env.")
    if not check_admin_code(body.code.strip()):
        admin_throttle.fail(key, now)
        audit.log(db, "auth", "admin_login_failed", "admin:console", client=key)   # the code is never logged
        db.commit()
        raise HTTPException(401, "That admin access code is not valid.")
    admin_throttle.clear(key)
    token = create_session(db, "admin", worker_name="Administrator")
    audit.log(db, "auth", "admin_login", "admin:console", client=key)
    db.commit()
    return {"token": token, "role": "admin", "user": {"name": "Administrator", "role": "admin"}}


@router.get("/me", summary="Who is signed in")
def me(p: Principal = Depends(require_principal)):
    if p.user:
        return {"role": p.role, "user": _user_out(p.user)}
    return {"role": p.role, "user": {"name": p.worker_name, "role": p.role}}


@router.post("/logout", summary="End the current session")
def logout(p: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    end_session(db, p.token)
    return {"ok": True}
