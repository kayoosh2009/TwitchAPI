from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
import uvicorn
import json
from datetime import datetime

app = FastAPI()

# Здесь храним данные всех подключенных телефонов
# Структура: { "client_id": {данные...} }
connected_devices = {}

# --- АДМИН ПАНЕЛЬ (Визуальная часть) ---
@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    # Генерируем простую таблицу HTML
    rows = ""
    for client_id, data in connected_devices.items():
        rows += f"""
        <tr>
            <td>{client_id}</td>
            <td>{data.get('ip', 'Unknown')}</td>
            <td>{data.get('limit_gb', '5.0')} GB</td>
            <td>{data.get('battery', 0)}%</td>
            <td>{data.get('signal', 'N/A')}</td>
            <td>{data.get('usage_30m', 0)} MB</td>
            <td style="color: green">Онлайн</td>
        </tr>
        """
    
    html_content = f"""
    <html>
        <head>
            <title>Proxy Admin Panel</title>
            <meta http-equiv="refresh" content="5"> <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; background: #f4f4f9; }}
                h1 {{ color: #333; }}
                table {{ width: 100%; border-collapse: collapse; background: white; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>📱 Панель управления устройствами</h1>
            <table>
                <tr>
                    <th>ID Устройства</th>
                    <th>IP Адрес</th>
                    <th>Лимит (Неделя)</th>
                    <th>Батарея</th>
                    <th>Сила Сигнала</th>
                    <th>Расход (30 мин)</th>
                    <th>Статус</th>
                </tr>
                {rows}
            </table>
            <p>Всего устройств онлайн: {len(connected_devices)}</p>
        </body>
    </html>
    """
    return html_content

# --- ТОЧКА ВХОДА ДЛЯ ТЕЛЕФОНОВ (Техническая часть) ---
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    
    # Получаем IP адрес подключившегося
    client_ip = websocket.client.host
    
    # Инициализируем данные устройства при подключении
    connected_devices[client_id] = {
        "ip": client_ip,
        "limit_gb": 5.0,     # По умолчанию даем 5 ГБ
        "battery": 0,
        "signal": "Unknown",
        "usage_30m": 0,
        "socket": websocket  # Сохраняем соединение, чтобы отправлять команды
    }
    
    print(f"[+] Устройство {client_id} подключилось ({client_ip})")

    try:
        while True:
            # Ждем JSON данные от телефона (обновление статуса)
            data = await websocket.receive_text()
            status_update = json.loads(data)
            
            # Обновляем информацию в базе
            if client_id in connected_devices:
                connected_devices[client_id].update({
                    "battery": status_update.get("battery"),
                    "signal": status_update.get("signal"),
                    "usage_30m": status_update.get("usage")
                })
                
    except Exception as e:
        print(f"[-] Устройство {client_id} отключилось: {e}")
        # Удаляем из списка, если отключился
        if client_id in connected_devices:
            del connected_devices[client_id]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
