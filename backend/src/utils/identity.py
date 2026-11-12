import uuid
from datetime import datetime, timezone
def new_id(prefix):
    return prefix + "-" + uuid.uuid4().hex[:12]
def now():
    return datetime.now(timezone.utc).isoformat()
