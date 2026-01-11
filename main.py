from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import sqlite3
import os
import random
import json

# Конфигурация
CHECK_INTERVAL = 30 * 60
DEFAULT_REWARD = 0.10
DEFAULT_DURATION = 30

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('tasks.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Таблица пользователей (добавляем IP и трафик)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            balance REAL DEFAULT 0.0,
            total_traffic_mb REAL DEFAULT 0.0,
            ip_address TEXT DEFAULT 'unknown',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Таблица заданий (расширяем для рандома)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_template TEXT NOT NULL,
            title_template TEXT DEFAULT 'Посетить сайт',
            description_template TEXT DEFAULT '',
            min_duration INTEGER DEFAULT 180,  -- 3 минуты минимум
            max_duration INTEGER DEFAULT 1440, -- 24 минуты максимум
            min_wait INTEGER DEFAULT 900,      -- 15 минут ожидания
            max_wait INTEGER DEFAULT 1800,    -- 30 минут ожидания  
            base_reward REAL DEFAULT 0.10,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица назначений (добавляем IP и трафик)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            assigned_url TEXT NOT NULL,
            assigned_title TEXT NOT NULL,
            assigned_description TEXT NOT NULL,
            visit_duration_sec INTEGER NOT NULL,
            wait_duration_sec INTEGER NOT NULL,
            reward REAL NOT NULL,
            ip_address TEXT DEFAULT 'unknown',
            traffic_used_mb REAL DEFAULT 0.0,
            status TEXT DEFAULT 'assigned',
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    ''')
    
    # Добавляем шаблоны заданий, если их нет
    cursor.execute('SELECT COUNT(*) FROM tasks')
    if cursor.fetchone()[0] == 0:
        task_templates = [
            ('https://www.google.com/search?q={keyword}', 'Поиск в Google', 'Выполните поисковый запрос', 180, 900, 600, 1200, 0.08),
            ('https://www.youtube.com/results?search_query={keyword}', 'Поиск на YouTube', 'Посмотрите видео', 300, 1440, 900, 1800, 0.15),
            ('https://github.com/search?q={keyword}', 'Поиск на GitHub', 'Изучите репозитории', 180, 600, 600, 1200, 0.10),
            ('https://www.amazon.com/s?k={keyword}', 'Поиск на Amazon', 'Посмотрите товары', 240, 1200, 600, 1500, 0.12),
            ('https://twitter.com/search?q={keyword}', 'Поиск в Twitter', 'Посмотрите твиты', 180, 480, 300, 900, 0.07),
        ]
        
        cursor.executemany('''
            INSERT INTO tasks (url_template, title_template, description_template, 
                             min_duration, max_duration, min_wait, max_wait, base_reward) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', task_templates)
    
    conn.commit()
    return conn

# Инициализируем БД при запуске
db_conn = init_db()

# FastAPI приложение
app = FastAPI(title="Advanced Task Tracker API", version="2.0.0")

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
    wait_duration_sec: int
    reward: float

class CompletionRequest(BaseModel):
    device_id: str
    assignment_id: int
    traffic_used_mb: Optional[float] = 0.0

class CompletionResponse(BaseModel):
    status: str
    reward_added: float
    new_balance: float
    total_traffic_mb: float
    next_check_seconds: int

class UserInfoResponse(BaseModel):
    device_id: str
    balance: float
    total_completed: int
    total_traffic_mb: float
    ip_address: str
    created_at: str
    last_seen: str

class AdminUserStats(BaseModel):
    device_id: str
    balance: float
    total_completed: int
    total_traffic_mb: float
    ip_address: str
    created_at: str
    last_seen: str
    is_active: bool

# Вспомогательные функции
def get_client_ip(request: Request) -> str:
    """Получаем IP адрес клиента"""
    if request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0]
    elif request.client:
        return request.client.host
    return "unknown"

def get_or_create_user(device_id: str, ip_address: str = None):
    cursor = db_conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE device_id = ?', (device_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute(
            'INSERT INTO users (device_id, ip_address) VALUES (?, ?)', 
            (device_id, ip_address or 'unknown')
        )
        db_conn.commit()
        cursor.execute('SELECT * FROM users WHERE device_id = ?', (device_id,))
        user = cursor.fetchone()
    else:
        # Обновляем IP и время последнего визита
        cursor.execute(
            'UPDATE users SET ip_address = ?, last_seen = CURRENT_TIMESTAMP WHERE id = ?',
            (ip_address or user[4], user[0])
        )
        db_conn.commit()
    
    return user

def generate_random_task(task_template):
    """Генерирует случайное задание на основе шаблона"""
    keywords = ["technology", "programming", "science", "news", "education", 
                "sports", "music", "movies", "games", "travel", "food", "health"]
    
    keyword = random.choice(keywords)
    url = task_template[1].replace('{keyword}', keyword)  # url_template
    title = task_template[2].replace('{keyword}', keyword)  # title_template
    description = task_template[3].replace('{keyword}', keyword)  # description_template
    
    duration = random.randint(task_template[4], task_template[5])  # min_duration, max_duration
    wait_time = random.randint(task_template[6], task_template[7])  # min_wait, max_wait
    reward = task_template[8]  # base_reward
    
    # Немного варьируем награду
    reward_variation = random.uniform(0.8, 1.2)
    reward = round(reward * reward_variation, 2)
    
    return {
        'url': url,
        'title': title,
        'description': description,
        'duration': duration,
        'wait_time': wait_time,
        'reward': reward
    }

# Эндпоинты
@app.get("/")
async def root():
    return {"message": "Advanced Task Tracker API", "version": "2.0.0"}

@app.get("/user/{device_id}", response_model=UserInfoResponse)
async def get_user_info(device_id: str, request: Request):
    ip_address = get_client_ip(request)
    user = get_or_create_user(device_id, ip_address)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Считаем выполненные задания
    cursor = db_conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM assignments 
        WHERE user_id = ? AND status = 'completed'
    ''', (user[0],))
    total_completed = cursor.fetchone()[0]
    
    return UserInfoResponse(
        device_id=user[1],
        balance=user[2],
        total_completed=total_completed,
        total_traffic_mb=user[3],
        ip_address=user[4],
        created_at=user[5],
        last_seen=user[6]
    )

@app.get("/get-task/{device_id}", response_model=TaskAssignmentResponse)
async def get_task(device_id: str, request: Request):
    cursor = db_conn.cursor()
    ip_address = get_client_ip(request)
    
    # Находим или создаем пользователя
    user = get_or_create_user(device_id, ip_address)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Проверяем активные задания
    cursor.execute('''
        SELECT a.* FROM assignments a 
        WHERE a.user_id = ? AND a.status = 'assigned'
        ORDER BY a.assigned_at DESC LIMIT 1
    ''', (user[0],))
    active_assignment = cursor.fetchone()
    
    if active_assignment:
        return TaskAssignmentResponse(
            assignment_id=active_assignment[0],
            title=active_assignment[4],
            url=active_assignment[3],
            description=active_assignment[5],
            visit_duration_sec=active_assignment[6],
            wait_duration_sec=active_assignment[7],
            reward=active_assignment[8]
        )
    
    # Ищем задания, которые пользователь еще не выполнял
    cursor.execute('''
        SELECT t.* FROM tasks t 
        WHERE t.is_active = 1 
        AND t.id NOT IN (
            SELECT task_id FROM assignments 
            WHERE user_id = ? AND status = 'completed'
        )
        ORDER BY RANDOM() LIMIT 1
    ''', (user[0],))
    
    task_template = cursor.fetchone()
    
    if not task_template:
        # Если все задания выполнены, выбираем любое активное
        cursor.execute('SELECT * FROM tasks WHERE is_active = 1 ORDER BY RANDOM() LIMIT 1')
        task_template = cursor.fetchone()
        
    if not task_template:
        raise HTTPException(status_code=404, detail="No tasks available")
    
    # Генерируем случайное задание
    task_data = generate_random_task(task_template)
    
    # Создаем назначение
    cursor.execute('''
        INSERT INTO assignments 
        (user_id, task_id, assigned_url, assigned_title, assigned_description, 
         visit_duration_sec, wait_duration_sec, reward, ip_address) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user[0], task_template[0], task_data['url'], task_data['title'], 
          task_data['description'], task_data['duration'], task_data['wait_time'],
          task_data['reward'], ip_address))
    
    assignment_id = cursor.lastrowid
    db_conn.commit()
    
    return TaskAssignmentResponse(
        assignment_id=assignment_id,
        title=task_data['title'],
        url=task_data['url'],
        description=task_data['description'],
        visit_duration_sec=task_data['duration'],
        wait_duration_sec=task_data['wait_time'],
        reward=task_data['reward']
    )

@app.post("/complete-task", response_model=CompletionResponse)
async def complete_task(request: CompletionRequest, http_request: Request):
    cursor = db_conn.cursor()
    ip_address = get_client_ip(http_request)
    
    # Находим пользователя
    user = get_or_create_user(request.device_id, ip_address)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Находим назначение
    cursor.execute('''
        SELECT a.* FROM assignments a 
        WHERE a.id = ? AND a.user_id = ?
    ''', (request.assignment_id, user[0]))
    
    assignment = cursor.fetchone()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    if assignment[11] == 'completed':  # status
        raise HTTPException(status_code=400, detail="Task already completed")
    
    # Обновляем статус и трафик
    cursor.execute('''
        UPDATE assignments SET 
        status = 'completed', 
        completed_at = CURRENT_TIMESTAMP,
        traffic_used_mb = ?,
        ip_address = ?
        WHERE id = ?
    ''', (request.traffic_used_mb or 10.0, ip_address, request.assignment_id))
    
    # Обновляем пользователя (баланс и трафик)
    new_balance = user[2] + assignment[8]  # reward
    total_traffic = user[3] + (request.traffic_used_mb or 10.0)
    
    cursor.execute('''
        UPDATE users SET 
        balance = ?,
        total_traffic_mb = ?,
        last_seen = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (new_balance, total_traffic, user[0]))
    
    db_conn.commit()
    
    return CompletionResponse(
        status="success",
        reward_added=assignment[8],
        new_balance=new_balance,
        total_traffic_mb=total_traffic,
        next_check_seconds=assignment[7]  # wait_duration_sec
    )

# Админские эндпоинты
@app.get("/admin/users", response_model=List[AdminUserStats])
async def get_all_users():
    cursor = db_conn.cursor()
    cursor.execute('''
        SELECT u.device_id, u.balance, u.total_traffic_mb, u.ip_address, 
               u.created_at, u.last_seen, u.is_active,
               COUNT(CASE WHEN a.status = 'completed' THEN 1 END) as completed_count
        FROM users u
        LEFT JOIN assignments a ON u.id = a.user_id
        GROUP BY u.id
        ORDER BY u.last_seen DESC
    ''')
    
    users = []
    for user in cursor.fetchall():
        users.append(AdminUserStats(
            device_id=user[0],
            balance=user[1],
            total_completed=user[7] or 0,
            total_traffic_mb=user[2],
            ip_address=user[3],
            created_at=user[4],
            last_seen=user[5],
            is_active=bool(user[6])
        ))
    
    return users

@app.get("/admin/stats")
async def get_stats():
    cursor = db_conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tasks WHERE is_active = 1')
    active_tasks = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM assignments WHERE status = "completed"')
    total_completed = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(balance) FROM users')
    total_rewards = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT SUM(total_traffic_mb) FROM users')
    total_traffic = cursor.fetchone()[0] or 0
    
    # Активные пользователи (были онлайн последние 24 часа)
    cursor.execute('''
        SELECT COUNT(*) FROM users 
        WHERE last_seen > datetime('now', '-24 hours')
    ''')
    active_users_24h = cursor.fetchone()[0]
    
    return {
        "total_users": total_users,
        "active_users_24h": active_users_24h,
        "active_tasks": active_tasks,
        "total_completed_assignments": total_completed,
        "total_rewards_issued": round(total_rewards, 2),
        "total_traffic_used_mb": round(total_traffic, 2)
    }

@app.post("/admin/tasks")
async def create_task(url_template: str, title_template: str = "Посетить сайт", 
                     description_template: str = "", min_duration: int = 180,
                     max_duration: int = 1440, min_wait: int = 900, 
                     max_wait: int = 1800, base_reward: float = 0.10):
    cursor = db_conn.cursor()
    
    cursor.execute('''
        INSERT INTO tasks 
        (url_template, title_template, description_template, min_duration, 
         max_duration, min_wait, max_wait, base_reward) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (url_template, title_template, description_template, min_duration,
          max_duration, min_wait, max_wait, base_reward))
    
    task_id = cursor.lastrowid
    db_conn.commit()
    
    return {"message": "Task template created", "task_id": task_id}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
