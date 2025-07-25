import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'DeepSeek_2024_SecureKey_KPI_Drive_v2.1'

    # Настройки для авторизации
    LOGIN_USERNAME = 'deepseek_kpi-drive'
    LOGIN_PASSWORD = 'Dsk_2024_KPI_Secure_Pass_671B!'

    # Настройки сессии
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = 'deepseek_chat:'
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # Очень большие таймауты для CPU-модели (4+ часа)
    SEND_FILE_MAX_AGE_DEFAULT = 18000  # 5 часов для статических файлов

    # Таймауты для запросов (в секундах)
    REQUEST_TIMEOUT = 18000  # 5 часов
    AI_RESPONSE_TIMEOUT = 18000  # 5 часов для AI ответов

    # Настройки загрузки файлов
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'txt', 'csv', 'json', 'md', 'py', 'js', 'html', 'xml'}

    # Настройки DeepSeek
    DEEPSEEK_MODEL = 'deepseek-r1:8b'
    MAX_CONTEXT_TOKENS = 128000

    # Настройки сервера
    SERVER_HOST = '0.0.0.0'
    SERVER_PORT = int(os.environ.get('PORT', 5050))
    DEBUG = True

    # Настройки для работы за прокси
    PREFERRED_URL_SCHEME = 'https'
    SERVER_NAME = 'ai.kpi-drive.ru'