from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.chat_service import ChatService
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
chat_service = ChatService()

class ChatMessage(BaseModel):
    message: str
    client_id: str

class SearchTask(BaseModel):
    keywords: Optional[str] = None
    client_id: str
    task_id: str

@router.post("/chat")
async def chat(message: ChatMessage):
    if not message.client_id:
        raise HTTPException(status_code=400, detail="client_id is required")
    
    result = await chat_service.process_chat(message.message, client_id=message.client_id)
    return result

@router.post("/start_auto_search")
async def start_auto_search(task: SearchTask):
    """开始自动搜索任务"""
    logger.debug(f"Starting auto search with task: {task}")
    if not task.keywords:
        raise HTTPException(status_code=400, detail="keywords is required for starting search")
        
    result = await chat_service.start_auto_search(task.keywords, task.client_id, task.task_id)
    logger.debug(f"Auto search started with result: {result}")
    return result

@router.post("/cancel_auto_search")
async def cancel_auto_search(task: SearchTask):
    """取消搜索任务"""
    logger.debug(f"Canceling search task: {task}")
    if not task.task_id:
        raise HTTPException(status_code=400, detail="task_id is required for canceling")
        
    result = await chat_service.cancel_auto_search(task.task_id, task.client_id)
    logger.debug(f"Auto search canceled with result: {result}")
    return result

@router.get("/search_tasks/{client_id}")
async def get_search_tasks(client_id: str):
    """获取指定客户端的所有搜索任务"""
    logger.debug(f"Getting search tasks for client: {client_id}")
    return await chat_service.get_search_tasks(client_id)
