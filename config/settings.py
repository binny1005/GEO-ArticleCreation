"""全局配置 — 从 .env + llm_providers.yaml 加载"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 加载 .env
load_dotenv(PROJECT_ROOT / ".env")

# ── 路径 ──
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = Path(os.getenv("GEO_OUTPUT_DIR", PROJECT_ROOT / "output"))
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# ── LLM 通用参数 (对齐百炼原始配置) ──
DEFAULT_LLM_PARAMS = {
    "temperature": 1.0,
    "top_p": 0.8,
    "max_tokens": 4096,
}

ANALYTICAL_LLM_PARAMS = {
    "temperature": 0.7,
    "top_p": 0.8,
    "max_tokens": 4096,
}

# ── 默认值 ──
DEFAULT_ENTRY_COUNT = 20
DEFAULT_ARTICLE_MIN_LENGTH = 800
DEFAULT_ARTICLE_MAX_LENGTH = 2000
DEFAULT_TITLE_LENGTH = 30
