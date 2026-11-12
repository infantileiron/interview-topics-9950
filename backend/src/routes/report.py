from fastapi import APIRouter,Depends
from src.controllers import report as controller
from src.schemas.entities import ReportInput
from src.services.auth import current,editor,admin
router=APIRouter(prefix="/reports",tags=["reports"])
@router.get("")
def list_items(user=Depends(current)): return controller.list_items()
@router.post("",status_code=201)
def create(data:ReportInput,user=Depends(editor)): return controller.create(data)
from fastapi.responses import Response
@router.get("/{id}/download")
def download(id:str,user=Depends(current)):
    return Response(controller.download(id),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{id}.csv"'})
