from src.services import run as service
from src.utils import repository as repo
def list_items(): return service.list_runs()
def detail(id): return repo.get("runs",id)
def create(data): return service.create(data)
