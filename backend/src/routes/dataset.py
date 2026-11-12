from fastapi import APIRouter,Depends
from src.controllers import dataset as controller
from src.schemas.entities import DatasetInput
from src.services.auth import current,editor,admin
router=APIRouter(prefix="/datasets",tags=["datasets"])
@router.get("")
def list_items(user=Depends(current)): return controller.list_items()
@router.post("",status_code=201)
def create(data:DatasetInput,user=Depends(editor)): return controller.create(data)
@router.get("/{id}")
def detail(id:str,user=Depends(current)): return controller.detail(id)

from src.schemas.entities import RenameDataset
@router.patch('/{id}')
def rename(id:str,data:RenameDataset,user=Depends(editor)):
 from src.services.dataset import rename
 return rename(id,data)
