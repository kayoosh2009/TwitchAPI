import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from datetime import datetime
import os

app = FastAPI()

# Хранилище: ID -> Данные (в памяти сервера)
active_connections = {}

@app.get("/")
async def root():
    return {"status": "online", "message": "Nexus Node Server is running"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Генерируем ID на основе порта подключения
    client_id = f"{websocket.client.host}:{websocket.client.port}"
    print(f"\n[+] ПОДКЛЮЧЕНИЕ: {client_id}")
    
    active_connections[client_id] = {"coins": 0}

    try:
        while True:
            # Получаем данные от узла (телефона)
            data = await websocket.receive_json()
            
            # Начисляем монеты
            active_connections[client_id]["coins"] += 1
            current_coins = active_connections[client_id]["coins"]
            
            # Логируем в консоль Koyeb
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Узел {client_id} | Баланс: {current_coins} NEX")

            # Отправляем ответ
            await websocket.send_json({
                "status": "success", 
                "coins": current_coins
            })

    except WebSocketDisconnect:
        print(f"[-] ОТКЛЮЧЕНИЕ: {client_id}")
        if client_id in active_connections:
            del active_connections[client_id]
    except Exception as e:
        print(f"[!] ОШИБКА: {e}")

if __name__ == "__main__":
    # Koyeb передает порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
