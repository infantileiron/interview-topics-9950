from src.services import dataset as service
def list_items(): return service.list_datasets()
def detail(id): return service.detail(id)
def create(data): return service.create(data)
