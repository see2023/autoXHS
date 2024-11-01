import logging
from typing import Dict
from fastapi import WebSocket

class WebsocketService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WebsocketService, cls).__new__(cls)
            active_connections: Dict[str, WebSocket] = dict()
            cls._instance.active_connections = active_connections
        return cls._instance
        
    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logging.info(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
        
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logging.info(f"Client {client_id} disconnected. Remaining connections: {len(self.active_connections)}")
            
    async def send_message(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logging.error(f"Error sending message to client {client_id}: {e}")
                self.disconnect(client_id)
        else:
            logging.warning(f"Client {client_id} not found in active connections")