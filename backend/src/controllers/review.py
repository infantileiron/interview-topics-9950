from src.services import review as service
def list_items(): return service.list_reviews()
def create(data,user): return service.create(data,user)
def decide(id,data,user): return service.decide(id,data,user)
