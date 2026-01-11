from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import sqlite3
import os

# Конфигурация
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tasks.db")
CHECK_INTERVAL = 30 * 60
DEFAULT_REWARD = 0.10
DEFAULT_DURATION = 30

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            balance REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Таблица заданий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT 'Посетить сайт',
            url TEXT NOT NULL,
            description TEXT DEFAULT '',
            visit_duration_sec INTEGER DEFAULT 30,
            reward REAL DEFAULT 0.10,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица назначений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            status TEXT DEFAULT 'assigned',
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    ''')
    
    # Добавляем тестовые задания, если их нет
    cursor.execute('SELECT COUNT(*) FROM tasks')
    if cursor.fetchone()[0] == 0:
        test_tasks = [
            ('Посетить Google', 'https://www.google.com', 'Перейдите на сайт Google', 30, 0.10),
            ('Посетить YouTube', 'https://www.youtube.com', 'Просмотрите рекомендации', 45, 0.15),
            ('Посетить GitHub', 'https://github.com', 'Ознакомьтесь с репозиториями', 25, 0.08)
        ]
        
        cursor.executemany('''
            INSERT INTO tasks (title, url, description, visit_duration_sec, reward) 
            VALUES (?, ?, ?, ?, ?)
        ''', test_tasks)
    
    conn.commit()
    conn.close()

# Инициализируем БД при запуске
init_db()

# FastAPI приложение
app = FastAPI(title="Task Tracker API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic модели
class TaskAssignmentResponse(BaseModel):
    assignment_id: int
    title: str
    url: str
    description: str
    visit_duration_sec: int
    reward: float

class CompletionRequest(BaseModel):
    device_id: str
    assignment_id: int

class CompletionResponse(BaseModel):
    status: str
    reward_added: float
    new_balance: float

class UserInfoResponse(BaseModel):
    device_id: str
    balance: float
    total_completed: int
    created_at: str

class TaskCreateRequest(BaseModel):
    title: str
    url: str
    description: Optional[str] = ""
    visit_duration_sec: int = DEFAULT_DURATION
    reward: float = DEFAULT_REWARD

# Функции для работы с БД
def get_db_connection():
    conn = sqlite3.connect('tasks.db')
    conn.row_factory = sqlite3.Row  # Чтобы возвращать dict-like объекты
    return conn

def get_or_create_user(device_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE device_id = ?', (device_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute(
            'INSERT INTO users (device_id) VALUES (?)', 
            (device_id,)
        )
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE device_id = ?', (device_id,))
        user = cursor.fetchone()
    
    conn.close()
    return dict(user) if user else None

# Эндпоинты
@app.get("/")
async def root():
    return {"message": "Task Tracker API", "version": "1.0.0"}

@app.get("/user/{device_id}", response_model=UserInfoResponse)
async def get_user_info(device_id: str):
    user = get_or_create_user(device_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Считаем выполненные задания
    cursor.execute('''
        SELECT COUNT(*) FROM assignments 
        WHERE user_id = ? AND status = 'completed'
    ''', (user['id'],))
    total_completed = cursor.fetchone()[0]
    
    conn.close()
    
    return UserInfoResponse(
        device_id=user['device_id'],
        balance=user['balance'],
        total_completed=total_completed,
        created_at=user['created_at']
    )

@app.get("/get-task/{device_id}", response_model=TaskAssignmentResponse)
async def get_task(device_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Находим или создаем пользователя
    user = get_or_create_user(device_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Проверяем активные задания
    cursor.execute('''
        SELECT a.id as assignment_id, t.* 
        FROM assignments a 
        JOIN tasks t ON a.task_id = t.id 
        WHERE a.user_id = ? AND a.status = 'assigned'
    ''', (user['id'],))
    active_assignment = cursor.fetchone()
    
    if active_assignment:
        conn.close()
        return TaskAssignmentResponse(
            assignment_id=active_assignment['assignment_id'],
            title=active_assignment['title'],
            url=active_assignment['url'],
            description=active_assignment['description'],
            visit_duration_sec=active_assignment['visit_duration_sec'],
            reward=active_assignment['reward']
        )
    
    # Ищем новое задание (которое пользователь еще не выполнял)
    cursor.execute('''
        SELECT t.* FROM tasks t 
        WHERE t.is_active = TRUE 
        AND t.id NOT IN (
            SELECT task_id FROM assignments 
            WHERE user_id = ? AND status = 'completed'
        )
        LIMIT 1
    ''', (user['id'],))
    
    task = cursor.fetchone()
    
    if not task:
        conn.close()
        raise HTTPException(status_code=404, detail="No tasks available")
    
    # Создаем назначение
    cursor.execute('''
        INSERT INTO assignments (user_id, task_id, status) 
        VALUES (?, ?, 'assigned')
    ''', (user['id'], task['id']))
    
    assignment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return TaskAssignmentResponse(
        assignment_id=assignment_id,
        title=task['title'],
        url=task['url'],
        description=task['description'],
        visit_duration_sec=task['visit_duration_sec'],
        reward=task['reward']
    )

@app.post("/complete-task", response_model=CompletionResponse)
async def complete_task(request: CompletionRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Находим пользователя
    user = get_or_create_user(request.device_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Находим назначение
    cursor.execute('''
        SELECT a.*, t.reward 
        FROM assignments a 
        JOIN tasks t ON a.task_id = t.id 
        WHERE a.id = ? AND a.user_id = ?
    ''', (request.assignment_id, user['id']))
    
    assignment = cursor.fetchone()
    
    if not assignment:
        conn.close()
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    if assignment['status'] == 'completed':
        conn.close()
        raise HTTPException(status_code=400, detail="Task already completed")
    
    # Обновляем статус и начисляем награду
    cursor.execute('''
        UPDATE assignments SET status = 'completed', completed_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (request.assignment_id,))
    
    new_balance = user['balance'] + assignment['reward']
    cursor.execute('UPDATE users SET balance = ? WHERE id = ?', (new_balance, user['id']))
    
    conn.commit()
    conn.close()
    
    return CompletionResponse(
        status="success",
        reward_added=assignment['reward'],
        new_balance=new_balance
    )

# Админские эндпоинты
@app.post("/admin/tasks")
async def create_task(request: TaskCreateRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO tasks (title, url, description, visit_duration_sec, reward) 
        VALUES (?, ?, ?, ?, ?)
    ''', (request.title, request.url, request.description, 
          request.visit_duration_sec, request.reward))
    
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"message": "Task created", "task_id": task_id}

@app.get("/admin/stats")
async def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tasks')
    total_tasks = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM assignments WHERE status = "completed"')
    total_completed = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(balance) FROM users')
    total_rewards = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        "total_users": total_users,
        "total_tasks": total_tasks,
        "total_completed_assignments": total_completed,
        "total_rewards_issued": total_rewards
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
