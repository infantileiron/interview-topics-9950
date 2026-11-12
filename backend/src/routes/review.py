from fastapi import APIRouter,Depends
from src.controllers import review as controller
from src.schemas.entities import ReviewInput
from src.services.auth import current,editor,admin
router=APIRouter(prefix="/reviews",tags=["reviews"])
@router.get("")
def list_items(user=Depends(current)): return controller.list_items()
@router.post("",status_code=201)
def create(data:ReviewInput,user=Depends(editor)): return controller.create(data,user)
from src.schemas.entities import DecisionInput
@router.patch("/{id}")
def decide(id:str,data:DecisionInput,user=Depends(admin)): return controller.decide(id,data,user)
