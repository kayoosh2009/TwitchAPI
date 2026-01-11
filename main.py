from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
import uuid

from database import get_db, init_default_data
from models import User, Task, Assignment
from config import CHECK_INTERVAL, DEFAULT_REWARD, DEFAULT_DURATION

# Pydantic модели для запросов/ответов
from pydantic import BaseModel

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
    created_at: datetime

class TaskCreateRequest(BaseModel):
    title: str
    url: str
    description: str = ""
    visit_duration_sec: int = DEFAULT_DURATION
    reward: float = DEFAULT_REWARD

app = FastAPI(title="Task Tracker API", version="1.0.0")

# Настраиваем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене заменить на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    db = next(get_db())
    init_default_data(db)
    print("Сервер запущен и готов к работе")

@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Task Tracker API", 
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/user/{device_id}", response_model=UserInfoResponse)
async def get_user_info(device_id: str, db: Session = Depends(get_db)):
    """Получить информацию о пользователе"""
    user = db.query(User).filter(User.device_id == device_id).first()
    
    if not user:
        # Создаем нового пользователя
        user = User(device_id=device_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # Считаем выполненные задания
    completed_count = db.query(Assignment).filter(
        Assignment.user_id == user.id,
        Assignment.status == "completed"
    ).count()
    
    return UserInfoResponse(
        device_id=user.device_id,
        balance=user.balance,
        total_completed=completed_count,
        created_at=user.created_at
    )

@app.get("/get-task/{device_id}", response_model=TaskAssignmentResponse)
async def get_task(device_id: str, db: Session = Depends(get_db)):
    """Получить задание для выполнения"""
    # Находим или создаем пользователя
    user = db.query(User).filter(User.device_id == device_id).first()
    if not user:
        user = User(device_id=device_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # Проверяем, нет ли активных заданий у пользователя
    active_assignment = db.query(Assignment).filter(
        Assignment.user_id == user.id,
        Assignment.status == "assigned"
    ).first()
    
    if active_assignment:
        # Если есть активное задание, возвращаем его
        return TaskAssignmentResponse(
            assignment_id=active_assignment.id,
            title=active_assignment.task.title,
            url=active_assignment.task.url,
            description=active_assignment.task.description,
            visit_duration_sec=active_assignment.task.visit_duration_sec,
            reward=active_assignment.task.reward
        )
    
    # Ищем подходящее задание (которое пользователь еще не выполнял)
    completed_tasks = db.query(Assignment.task_id).filter(
        Assignment.user_id == user.id,
        Assignment.status == "completed"
    )
    
    available_task = db.query(Task).filter(
        Task.is_active == True,
        ~Task.id.in_(completed_tasks) if completed_tasks.count() > 0 else True
    ).first()
    
    if not available_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Нет доступных заданий"
        )
    
    # Создаем новое назначение
    assignment = Assignment(
        user_id=user.id,
        task_id=available_task.id,
        status="assigned"
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    
    return TaskAssignmentResponse(
        assignment_id=assignment.id,
        title=available_task.title,
        url=available_task.url,
        description=available_task.description,
        visit_duration_sec=available_task.visit_duration_sec,
        reward=available_task.reward
    )

@app.post("/complete-task", response_model=CompletionResponse)
async def complete_task(request: CompletionRequest, db: Session = Depends(get_db)):
    """Отметить задание как выполненное"""
    # Находим назначение
    assignment = db.query(Assignment).filter(Assignment.id == request.assignment_id).first()
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Назначение не найдено"
        )
    
    # Проверяем, что назначение принадлежит пользователю
    if assignment.user.device_id != request.device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Назначение не принадлежит пользователю"
        )
    
    # Проверяем, что задание еще не выполнено
    if assignment.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Задание уже выполнено"
        )
    
    # Обновляем статус
    assignment.status = "completed"
    assignment.completed_at = datetime.utcnow()
    
    # Начисляем награду
    user = assignment.user
    user.balance += assignment.task.reward
    
    db.commit()
    
    return CompletionResponse(
        status="success",
        reward_added=assignment.task.reward,
        new_balance=user.balance
    )

# Админские эндпоинты
@app.post("/admin/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(request: TaskCreateRequest, db: Session = Depends(get_db)):
    """Создать новое задание (админ)"""
    task = Task(
        title=request.title,
        url=request.url,
        description=request.description,
        visit_duration_sec=request.visit_duration_sec,
        reward=request.reward
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    return {
        "message": "Задание создано",
        "task_id": task.id,
        "title": task.title
    }

@app.get("/admin/tasks", response_model=List[TaskAssignmentResponse])
async def get_all_tasks(db: Session = Depends(get_db)):
    """Получить все задания (админ)"""
    tasks = db.query(Task).filter(Task.is_active == True).all()
    
    return [
        TaskAssignmentResponse(
            assignment_id=task.id,  # Для совместимости, но это ID задачи, а не назначения
            title=task.title,
            url=task.url,
            description=task.description,
            visit_duration_sec=task.visit_duration_sec,
            reward=task.reward
        )
        for task in tasks
    ]

@app.get("/admin/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Статистика системы (админ)"""
    total_users = db.query(User).count()
    total_tasks = db.query(Task).count()
    total_completed = db.query(Assignment).filter(Assignment.status == "completed").count()
    total_rewards = db.query(User).with_entities(db.func.sum(User.balance)).scalar() or 0
    
    return {
        "total_users": total_users,
        "total_tasks": total_tasks,
        "total_completed_assignments": total_completed,
        "total_rewards_issued": total_rewards
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
