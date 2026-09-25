import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    APP_NAME: str = "NexusFlow AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # LLM Settings (Supports OpenAI, Anthropic, or Local Deterministic Engine)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    DEFAULT_PLANNER_MODEL: str = os.getenv("DEFAULT_PLANNER_MODEL", "gpt-4o")
    
    # Server Settings
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", 8000))
    
    # Execution Settings
    AUTO_APPROVE_LOW_RISK: bool = True
    ENABLE_SELF_HEALING: bool = True
    MAX_SELF_HEALING_RETRIES: int = 3
    STEP_TIMEOUT_SEC: int = 30
    MAX_STEP_RETRIES: int = 2
    STEP_RETRY_BACKOFF_SEC: float = 0.2
    # SafeGuard fail-safe: auto-REJECT gated actions when no human responds
    APPROVAL_TIMEOUT_SEC: float = float(os.getenv("APPROVAL_TIMEOUT_SEC", "120"))
    
    # Workspace & Telemetry Paths
    WORKSPACE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    LOGS_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "eval", "reports"))

settings = Settings()
os.makedirs(settings.LOGS_DIR, exist_ok=True)
