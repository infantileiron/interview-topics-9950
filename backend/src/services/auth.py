from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer
from src.utils import repository as repo
from src.constants.enums import Role
from src.utils.security import verify_password, token, verify_token
security = HTTPBearer(auto_error=False)
def login(data):
    users = [u for u in repo.all_rows("users") if u["email"] == data.email.lower()]
    if not users or not verify_password(data.password, users[0]["password_hash"]):
        raise HTTPException(401, "账号或密码不正确")
    user = users[0]
    return {"access_token":token(user), "token_type":"bearer", "user":{"email":user["email"],"role":user["role"],"name":user["name"]}}
def current(request: Request, credentials=Depends(security)):
    if not credentials: raise HTTPException(401, "请先登录")
    claims = verify_token(credentials.credentials)
    user = repo.get("users", claims["sub"])
    request.state.actor = user["email"]
    return {k:user[k] for k in ("email","name","role")}
def editor(user=Depends(current)):
    if user["role"] not in (Role.ADMIN.value,Role.ANALYST.value): raise HTTPException(403, "此操作需要分析员权限")
    return user
def admin(user=Depends(current)):
    if user["role"] != Role.ADMIN.value: raise HTTPException(403, "复核决定需要管理员权限")
    return user
