import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
class ErrorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try: return await call_next(request)
        except ValueError as exc: return JSONResponse({"detail":str(exc)}, status_code=422)
        except Exception:
            logging.getLogger(__name__).exception("request failed")
            return JSONResponse({"detail":"服务暂时不可用，请重试；未完成的计算可重新提交"}, status_code=500)
