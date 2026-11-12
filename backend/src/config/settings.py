import os
from pathlib import Path
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/interview-topics.sqlite")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "interview-topics-development-secret-change-this")
SEED_DEMO = os.getenv("SEED_DEMO", "true").lower() == "true"
TASK_MODE = os.getenv("TASK_MODE", "redis")
ARTIFACT_DIR = Path(os.getenv("ARTIFACT_DIR", "/tmp/interview-topics-artifacts"))
