from fastapi import APIRouter,Depends
from src.controllers import run as controller
from src.schemas.entities import RunInput
from src.services.auth import current,editor,admin
router=APIRouter(prefix="/runs",tags=["runs"])
@router.get("")
def list_items(user=Depends(current)): return controller.list_items()
@router.post("",status_code=201)
def create(data:RunInput,user=Depends(editor)): return controller.create(data)
@router.get("/{id}")
def detail(id:str,user=Depends(current)): return controller.detail(id)
