from fastapi import APIRouter,Depends
from src.controllers import lexicon as controller
from src.schemas.entities import LexiconInput
from src.services.auth import current,editor
router=APIRouter(prefix='/lexicons',tags=['lexicons'])
@router.get('')
def list_items(user=Depends(current)):return controller.list_items()
@router.post('',status_code=201)
def create(data:LexiconInput,user=Depends(editor)):return controller.create(data)
