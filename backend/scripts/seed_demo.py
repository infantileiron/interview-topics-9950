import json
from src.services.seed import seed
if __name__=='__main__':print(json.dumps(seed(),ensure_ascii=False))
