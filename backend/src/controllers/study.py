from src.services import study as service
def list_items(): return service.list_studies()
def create(data): return service.create(data)
