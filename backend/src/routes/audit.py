from fastapi import APIRouter,Depends
from src.services.auth import admin
from src.utils.repository import all_rows
router=APIRouter(prefix='/audit',tags=['audit'])
@router.get('')
def list_audit(user=Depends(admin)):return all_rows('audit')[-200:]
