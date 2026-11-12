from src.services import lexicon as service
def list_items():return service.list_lexicons()
def create(data):return service.create(data)
