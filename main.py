from fastapi import FastAPI, HTTPException
from datetime import datetime
import pytz

app = FastAPI()

# --- НАСТРОЙКИ ---
# Твой часовой пояс (важно, так как сервер Render живет по времени UTC)
TIMEZONE = pytz.timezone('Europe/Moscow') 

# Переключатель "Красная кнопка". По умолчанию True (работаем).
# Если ты вызовешь /admin/stop, станет False (отмена смены).
WORK_ALLOWED = True

def is_time_window_open():
    """Проверяет, попадаем ли мы сейчас в рабочее время"""
    now = datetime.now(TIMEZONE)
    weekday = now.weekday() # 0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс
    
    # Время в формате (Часы, Минуты)
    current_time = (now.hour, now.minute)

    # 1. Вторник (1) с 19:00 до 20:30
    if weekday == 1:
        return (19, 0) <= current_time < (20, 30)
    
    # 2. Пятница (4) с 19:00 до 20:30
    if weekday == 4:
        return (19, 0) <= current_time < (20, 30)
    
    # 3. Суббота (5) с 18:20 до 20:30
    if weekday == 5:
        return (18, 20) <= current_time < (20, 30)

    return False

@app.get("/")
def home():
    now = datetime.now(TIMEZONE)
    status = "ОТКРЫТО" if is_time_window_open() and WORK_ALLOWED else "ЗАКРЫТО"
    return {"server_time": now.strftime("%Y-%m-%d %H:%M"), "status": status, "manual_allow": WORK_ALLOWED}

# --- ДЛЯ ТЕЛЕФОНОВ ---
@app.get("/check_in")
def check_in():
    """Сюда стучится телефон, когда проснулся"""
    if not WORK_ALLOWED:
        return {"action": "ABORT", "reason": "Админ отменил смену"}
    
    if not is_time_window_open():
        return {"action": "ABORT", "reason": "Вне расписания"}

    return {"action": "WORK", "task": "Ожидаю прокси..."}

# --- ПАНЕЛЬ УПРАВЛЕНИЯ (ДЛЯ ТЕБЯ) ---
@app.get("/admin/stop")
def admin_stop():
    """Нажми, чтобы отменить работу сегодня"""
    global WORK_ALLOWED
    WORK_ALLOWED = False
    return {"status": "Смена отменена. Телефоны получат отказ."}

@app.get("/admin/start")
def admin_start():
    """Нажми, чтобы снова разрешить работу"""
    global WORK_ALLOWED
    WORK_ALLOWED = True
    return {"status": "Смена разрешена."}
