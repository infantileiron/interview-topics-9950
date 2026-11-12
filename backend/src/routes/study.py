from fastapi import APIRouter,Depends
from src.controllers import study as controller
from src.schemas.entities import TopicStudyInput
from src.services.auth import current,editor,admin
router=APIRouter(prefix="/studies",tags=["studies"])
@router.get("")
def list_items(user=Depends(current)): return controller.list_items()
@router.post("",status_code=201)
def create(data:TopicStudyInput,user=Depends(editor)): return controller.create(data)
