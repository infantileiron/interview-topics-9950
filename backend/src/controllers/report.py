from src.services import report as service
def list_items(): return service.list_reports()
def create(data): return service.create(data)
def download(id): return service.download(id)
