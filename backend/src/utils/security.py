import base64, hashlib, hmac, json, secrets, time
from fastapi import HTTPException
from src.config.settings import JWT_SECRET
def encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()
def decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return salt + ":" + digest
def verify_password(password, stored):
    return hmac.compare_digest(hash_password(password, stored.split(":")[0]), stored)
def token(user):
    header = encode(json.dumps({"alg":"HS256","typ":"JWT"}, separators=(",",":")).encode())
    body = encode(json.dumps({"sub":user["email"],"role":user["role"],"exp":int(time.time())+28800}, separators=(",",":")).encode())
    signature = encode(hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"
def verify_token(value):
    try:
        a,b,c = value.split(".")
        if json.loads(decode(a)) != {"alg":"HS256","typ":"JWT"}: raise ValueError()
        expected = encode(hmac.new(JWT_SECRET.encode(), f"{a}.{b}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(c, expected): raise ValueError()
        data = json.loads(decode(b))
        if data["exp"] <= time.time(): raise ValueError()
        return data
    except Exception:
        raise HTTPException(401, "登录已过期，请重新登录")
