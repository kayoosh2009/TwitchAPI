import os
from dotenv import load_dotenv

load_dotenv()

# Настройки базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# Настройки приложения
CHECK_INTERVAL = 30 * 60  # 30 минут в секундах
DEFAULT_REWARD = 0.10     # Награда по умолчанию
DEFAULT_DURATION = 30     # Длительность посещения по умолчанию (сек)
