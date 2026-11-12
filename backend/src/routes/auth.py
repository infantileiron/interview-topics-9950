from fastapi import APIRouter,Depends
from src.controllers import auth
from src.schemas.entities import LoginInput
from src.services.auth import current,admin
router=APIRouter(prefix="/auth",tags=["auth"])
@router.post("/login")
def login(data:LoginInput): return auth.login(data)
@router.get("/me")
def me(user=Depends(current)): return user
from src.utils.repository import all_rows
@router.get("/audit")
def audit(user=Depends(admin)): return all_rows("audit")[-100:]
