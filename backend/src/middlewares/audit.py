from starlette.middleware.base import BaseHTTPMiddleware
from src.utils import repository as repo
from src.utils.identity import new_id, now
class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method in ("POST", "PATCH", "DELETE"):
            try:
                repo.put("audit", {"id":new_id("audit"),"created_at":now(),"method":request.method,"path":request.url.path,"status":response.status_code,"actor":getattr(request.state,"actor","anonymous")})
            except Exception:
                import logging
                logging.getLogger(__name__).exception("audit write failed")
        return response
