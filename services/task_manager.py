from typing import Dict, List, Optional, Any
from .task_state import SearchTask, TaskState, TaskEvent
from services.websocket_service import WebsocketService
import logging
import asyncio

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, websocket_service: WebsocketService):
        self.tasks: Dict[str, SearchTask] = {}
        self.client_tasks: Dict[str, List[str]] = {}  # client_id -> [task_id]
        self.websocket_service = websocket_service
        
    async def create_task(self, keywords: str, client_id: str, task_id: Optional[str] = None) -> SearchTask:
        """创建新任务，如果提供task_id则使用该ID"""
        # 标准化关键词
        normalized_keywords = keywords.strip()
        
        # 检查是否存在相同关键词的运行中任务
        for existing_task in self.tasks.values():
            if (existing_task.client_id == client_id and 
                existing_task.keywords.strip() == normalized_keywords and 
                existing_task.state == TaskState.RUNNING):
                logger.info(f"Found duplicate running task for keywords: {normalized_keywords}")
                return existing_task

        # 如果提供了task_id，检查是否存在且状态是否为pending
        if task_id:
            if task_id not in self.tasks:
                raise ValueError("Invalid task_id")
            task = self.tasks[task_id]
            if task.state != TaskState.PENDING:
                raise ValueError(f"Task state is not pending: {task.state}")
            # 更新任务状态
            await self.update_task_state(task_id, TaskState.RUNNING, TaskEvent.START)
            return task

        # 创建新任务
        task = SearchTask(normalized_keywords, client_id)
        self.tasks[task.task_id] = task
        
        # 关联到客户端
        if client_id not in self.client_tasks:
            self.client_tasks[client_id] = []
        self.client_tasks[client_id].append(task.task_id)
        
        await self._notify_task_update(task, TaskEvent.START)
        return task

    async def get_client_tasks(self, client_id: str) -> List[Dict[str, Any]]:
        """获取客户端的所有任务"""
        if client_id not in self.client_tasks:
            return []
            
        tasks = []
        for task_id in self.client_tasks[client_id]:
            if task_id in self.tasks:  # 确保任务仍然存在
                task = self.tasks[task_id]
                tasks.append(task.to_dict())
                
        return tasks

    def create_pending_task(self, keywords: str, client_id: str) -> str:
        """创建待定状态的任务，返回task_id"""
        task = SearchTask(keywords, client_id)
        task.state = TaskState.PENDING
        self.tasks[task.task_id] = task
        
        # 关联到客户端
        if client_id not in self.client_tasks:
            self.client_tasks[client_id] = []
        self.client_tasks[client_id].append(task.task_id)
        
        return task.task_id

    async def update_task_state(self, task_id: str, new_state: TaskState, 
                              event: TaskEvent, message: Optional[str] = None):
        """更新任务状态"""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
            
        task = self.tasks[task_id]
        task.update_state(new_state, event, message)
        await self._notify_task_update(task, event)
        
    async def request_user_input(self, task_id: str, input_request: Dict):
        """请求用户输入"""
        logger.debug(f"Requesting user input for task {task_id}: {input_request}")
        task = self.tasks[task_id]
        task.user_input_required = input_request
        await self.update_task_state(
            task_id, 
            TaskState.WAITING_USER_INPUT,
            TaskEvent.REQUIRE_INPUT,
            "等待用户输入"
        )
        logger.info(f"Task {task_id} state updated to waiting_user_input with request: {input_request}")
        
    async def receive_user_input(self, task_id: str, user_input: Dict):
        """接收用户输入"""
        task = self.tasks[task_id]
        task.context["user_input"] = user_input
        task.user_input_required = None
        await self.update_task_state(
            task_id,
            TaskState.RUNNING,
            TaskEvent.RECEIVE_INPUT,
            "Received user input"
        )
        
    async def _notify_task_update(self, task: SearchTask, event: TaskEvent):
        """通知客户端任务更新"""
        await self.websocket_service.send_message(task.client_id, {
            "type": "search_task_update",
            "action": event.value,
            "task": task.to_dict()
        }) 

    async def cancel_task(self, task_id: str, client_id: str) -> dict:
        """取消任务"""
        if task_id not in self.tasks:
            logger.info(f"Task not found: {task_id}")
            return {
                "status": "success",
                "message": "任务已经删除过了"
            }

        task = self.tasks[task_id]
        if task.client_id != client_id:
            logger.info(f"Task client_id mismatch: {task.client_id} != {client_id}")
            return {
                "status": "error",
                "message": "无权操作此任务"
            }

        await self.update_task_state(
            task_id,
            TaskState.CANCELLED,
            TaskEvent.CANCEL,
            "Task cancelled by user"
        )
        
        return {
            "status": "success",
            "message": "任务已取消"
        }