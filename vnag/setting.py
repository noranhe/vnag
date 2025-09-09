from .utility import load_json


# RAG系统默认配置
SETTINGS: dict = {
    "gateway_name": "OpenAI",
    "model_name": "anthropic/claude-3.7-sonnet",
    "max_tokens": 2000,
    "temperature": 0.7
}

SETTING_FILENAME: str = "gateway_setting.json"
SETTINGS.update(load_json(SETTING_FILENAME))
