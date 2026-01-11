from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
from config import DATABASE_URL
import os

# Корректировка URL для Render (если нужно)
def get_database_url():
    if DATABASE_URL.startswith("postgres://"):
        return DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return DATABASE_URL

# Создаем движок БД
engine = create_engine(
    get_database_url(),
    connect_args={"check_same_thread": False} if "sqlite" in get_database_url() else {}
)

# Создаем таблицы
Base.metadata.create_all(bind=engine)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Зависимость для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_default_data(db):
    """Инициализация тестовых данных"""
    from models import Task
    
    # Проверяем, есть ли уже задания
    existing_tasks = db.query(Task).count()
    if existing_tasks == 0:
        # Добавляем тестовые задания
        default_tasks = [
            Task(
                title="Посетить Google",
                url="https://www.google.com",
                description="Перейдите на сайт Google и оставайтесь на нем указанное время",
                visit_duration_sec=30,
                reward=0.10
            ),
            Task(
                title="Посетить YouTube",
                url="https://www.youtube.com",
                description="Перейдите на YouTube и просмотрите рекомендации",
                visit_duration_sec=45,
                reward=0.15
            ),
            Task(
                title="Посетить GitHub",
                url="https://github.com",
                description="Ознакомьтесь с популярными репозиториями",
                visit_duration_sec=25,
                reward=0.08
            )
        ]
        
        db.add_all(default_tasks)
        db.commit()
        print("Добавлены тестовые задания")
