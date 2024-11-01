import os
from typing import List, Optional, Tuple, Dict
from services.ai_service import AIService
from config.config_manager import config
from models.ai_models import Message, MessageRole, TextContent
import logging
from services.websocket_service import WebsocketService
import asyncio
import json
import re
import uuid
from datetime import datetime
from tools.json_tools import extract_json_from_text

logger = logging.getLogger(__name__)

class SearchTaskInfo:
    def __init__(self, keywords: str, client_id: str):
        self.task_id = str(uuid.uuid4())
        self.keywords = keywords
        self.client_id = client_id
        self.status = "running"  # running, completed, cancelled, error
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.progress = 0  # 0-100
        self.error: Optional[str] = None
        self.results: List[Dict] = []

class ChatService:
    def __init__(self):
        self.ai_service = AIService(base_url=config.llm.get('openai_custom_url'), 
                                  api_key=os.getenv(config.llm.get('openai_custom_key_envname')))
        self.ai_service_mm = AIService(base_url=config.llm.get('openai_custom_mm_url'), 
                                     api_key=os.getenv(config.llm.get('openai_custom_key_envname_mm')))
        
        self.system_message = Message(
            role=MessageRole.system,
            content="You are a helpful AI assistant. You aim to provide accurate, helpful, and friendly responses to users' questions. If you're unsure about something, please say so rather than making assumptions."
        )
        
        self.chat_history: List[Message] = []
        self.max_messages = 10
        self.max_message_length = 2000
        self.websocket_service = WebsocketService()
        self._analyzing = False  # 添加标志位,防止并发分析
        self.search_tasks: Dict[str, SearchTaskInfo] = {}  # task_id -> task_info
        self.client_tasks: Dict[str, List[str]] = {}  # client_id -> [task_id]

    @staticmethod
    def last_sentence_end(text: str, skip_comma: bool = True, min_length: int = 10) -> int:
        if not text or len(text) < min_length:
            return -1
        total_length = len(text)
        end_chars = ['。', '！', '？', '；', "\n", '…', '.', '!', '?', ';']
        
        for i in range(total_length-1, -1, -1):
            if i < min_length:
                break
            if text[i] in end_chars:
                if i < total_length-1 and text[i] == '.' and text[i-1].isdigit() and text[i+1].isdigit():
                    continue
                return i
                
        if not skip_comma:
            end_chars = ['，', ',']
            for i in range(total_length-1, -1, -1):
                if i < min_length:
                    return -1
                if text[i] in end_chars:
                    return i
        return -1

    async def process_chat(self, message_content: str, client_id: str = None) -> dict:
        """Process chat message and return initial response"""
        user_message = Message(
            role=MessageRole.user,
            content=message_content[:self.max_message_length]
        )
        logger.debug(f"process_chat start, user_message: {user_message}, client_id: {client_id}")
        
        messages = [self.system_message] + self.chat_history + [user_message]
        
        try:
            # 创建异步任务处理流式响应
            asyncio.create_task(self._handle_stream_response(messages, user_message, client_id))
            
            # 立即返回初始响应
            return {
                "status": "success",
                "initial_response": "Message is being sent through WebSocket"
            }
            
        except Exception as e:
            logger.error(f"Error in process_chat: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    async def analyze_search_intent(self, recent_messages: List[Message] = None) -> Tuple[bool, Optional[str]]:
        """分析最近的对话是否包含搜索意图"""
        if self._analyzing:
            logger.info("Already analyzing search intent, skipping...")
            return False, None
            
        try:
            self._analyzing = True
            
            # 默认分析最近5条消息
            if not recent_messages:
                recent_messages = self.chat_history[-5:] if len(self.chat_history) > 0 else []
            
            # 构建对话历史文本
            chat_history_text = "\n".join([
                f"{'用户' if msg.role == MessageRole.user else 'AI'}: {msg.content}"
                for msg in recent_messages
            ])
            
            analyze_prompt = f"""分析以下对话历史,判断用户是否在寻求信息搜索。如果是,提取最重要的1-3个核心关键词。

对话历史:
{chat_history_text}

直接返回JSON格式(不要添加任何其他标记):
{{
    "is_search": true/false,
    "keywords": "最多3个关键词,用逗号分隔,如果不是搜索意图则返回null",
    "reason": "分析原因,包括为什么选择这些关键词"
}}"""
        
            messages = [
                Message(role=MessageRole.system, content="你是一个专门分析用户意图的AI助手"),
                Message(role=MessageRole.user, content=analyze_prompt)
            ]
            
            try:
                response = await self.ai_service.generate_response(messages)
                result = extract_json_from_text(response)
                if result and result.get("is_search") and result.get("keywords"):
                    # 处理关键词：分割、去重、限制数量
                    keywords = [k.strip() for k in result["keywords"].split(",")]
                    keywords = list(dict.fromkeys(keywords))  # 去重
                    keywords = keywords[:3]  # 只取前3个
                    
                    logger.info(f"Search intent analysis result (processed): {keywords}")
                    return True, ",".join(keywords)
                else:
                    logger.info(f"Search intent analysis result (not search): {result}")
                    return False, None
                
            except Exception as e:
                logger.error(f"Error in analyze_search_intent: {e}")
                return False, None
                
        finally:
            self._analyzing = False

    async def _handle_stream_response(self, messages: List[Message], user_message: Message, client_id: str = None):
        try:
            # 先生成回复
            full_content = ""
            one_sentence = ""
            
            async for chunk in self.ai_service.generate_response_stream(messages, model=config.llm.get('model')):
                if chunk is not None:
                    full_content += chunk
                    one_sentence += chunk
                    last_sentence_end_pos = self.last_sentence_end(one_sentence)
                    if last_sentence_end_pos > 0:
                        sentence = one_sentence[:last_sentence_end_pos+1]
                        one_sentence = one_sentence[last_sentence_end_pos+1:]
                        logger.info(f"Got complete sentence: {sentence}")
                        
                        if client_id:
                            await self.websocket_service.send_message(client_id, {
                                "type": "chat_response",
                                "content": sentence
                            })
            
            # 发送剩余的不完整句子
            if one_sentence:
                logger.info(f"Sending remaining text: {one_sentence}")
                if client_id:
                    await self.websocket_service.send_message(client_id, {
                        "type": "chat_response",
                        "content": one_sentence
                    })
            
            # 更新聊天历史
            assistant_message = Message(
                role=MessageRole.assistant,
                content=full_content
            )
            self.chat_history.append(user_message)
            self.chat_history.append(assistant_message)
            
            while len(self.chat_history) > self.max_messages * 2:
                self.chat_history.pop(0)
                
            logger.info(f"Processed chat, input: {user_message.content}, full response: {full_content}")

            # 分析完整对话后的搜索意图
            is_search, keywords = await self.analyze_search_intent()
            if is_search and keywords and client_id:
                task_id = str(uuid.uuid4())
                await self.websocket_service.send_message(client_id, {
                    "type": "search_intent",
                    "content": f"看起来您想搜索关于「{keywords}」的信息。要开始智能搜索任务吗？",
                    "keywords": keywords,
                    "task_id": task_id
                })
                logger.info(f'create task with keyswords {keywords} and task_id {task_id}')
                
                # 预创建任务对象，但状态设为pending
                task = SearchTaskInfo(keywords, client_id)
                task.task_id = task_id
                task.status = "pending"
                self.search_tasks[task_id] = task

        except Exception as e:
            logger.error(f"Error in _handle_stream_response: {e}")
            if client_id:
                await self.websocket_service.send_message(client_id, {
                    "type": "error",
                    "content": str(e)
                })

    async def start_auto_search(self, keywords: str, client_id: str, task_id: str) -> dict:
        """开始自动搜索任务"""
        # 标准化关键词处理
        normalized_keywords = keywords.strip()

        # 用task_id检查， 如果不存在，或者状态不是 pending, 则返回
        if not task_id or task_id not in self.search_tasks:
            logger.info(f"task id not pending")
            return {
                "status": "error",
                "message": "任务ID错误",
                "task_id": task_id
            }
        if self.search_tasks[task_id].status != 'pending':
            logger.info(f"task id status not pending")
            return {
                "status": "error",
                "message": f"任务状态错误: {self.search_tasks[task_id].status}",
                "task_id": task_id
            }
        
        # 检查是否存在相同关键词的运行中任务
        for task in self.search_tasks.values():
            if (task.client_id == client_id and 
                task.keywords.strip() == normalized_keywords and 
                task.status == "running"):
                logger.info(f"Found duplicate running task for keywords: {normalized_keywords}")
                return {
                    "status": "error",
                    "message": "已经有相同关键词的搜索任务正在运行中",
                    "task_id": task.task_id  # 返回已存在的任务ID
                }

        # 创建新任务
        task = self.search_tasks[task_id]
        task.status = "running"
        
        # 关联到客户端
        if client_id not in self.client_tasks:
            self.client_tasks[client_id] = []
        self.client_tasks[client_id].append(task.task_id)

        # 发送任务开始通知
        await self.websocket_service.send_message(client_id, {
            "type": "search_task_update",
            "action": "start",
            "task": {
                "task_id": task.task_id,
                "keywords": keywords,
                "status": task.status,
                "progress": task.progress
            }
        })

        # 创建异步任务执行搜索
        asyncio.create_task(self._execute_search_task(task))

        logger.info(f"Search task started: {task.task_id}, client_id: {client_id}, keywords: {keywords}")
        return {
            "status": "success",
            "task_id": task.task_id,
            "message": "搜索任务已启动"
        }

    async def cancel_auto_search(self, task_id: str, client_id: str) -> dict:
        """取消搜索任务"""
        if task_id not in self.search_tasks:
            logger.info(f"Search task not found: {task_id}")
            return {
                "status": "success",
                "message": "任务已经删除过了"
            }

        task = self.search_tasks[task_id]
        if task.client_id != client_id:
            logger.info(f"Search task client_id mismatch: {task.client_id} != {client_id}")
            return {
                "status": "error",
                "message": "无权操作此任务"
            }

        task.status = "cancelled"
        task.end_time = datetime.now()

        # 发送任务取消通知
        await self.websocket_service.send_message(client_id, {
            "type": "search_task_update",
            "action": "cancel",
            "task_id": task_id
        })
        logger.info(f"Search task canceled: {task_id}, client_id: {client_id}")
        return {
            "status": "success",
            "message": "任务已取消"
        }

    async def get_search_tasks(self, client_id: str) -> dict:
        """获取客户端的所有搜索任务"""
        if client_id not in self.client_tasks:
            logger.info(f"No search tasks found for client: {client_id}")
            return {
                "status": "success",
                "tasks": []
            }

        tasks = []
        for task_id in self.client_tasks[client_id]:
            task = self.search_tasks[task_id]
            tasks.append({
                "task_id": task.task_id,
                "keywords": task.keywords,
                "status": task.status,
                "progress": task.progress,
                "start_time": task.start_time.isoformat(),
                "end_time": task.end_time.isoformat() if task.end_time else None,
                "error": task.error
            })

        logger.info(f"Search tasks retrieved for client: {client_id}, tasks: {tasks}")
        return {
            "status": "success",
            "tasks": tasks
        }

    async def _execute_search_task(self, task: SearchTaskInfo):
        """执行搜索任务的具体逻辑"""
        try:
            # TODO: 实现具体的搜索逻辑
            # 1. 生成关键词组合
            # 2. 执行搜索
            # 3. 分析结果
            # 4. 更新进度
            pass

        except Exception as e:
            logger.error(f"Error in search task: {e}")
            task.status = "error"
            task.error = str(e)
        finally:
            if task.status == "running":
                task.status = "completed"
            task.end_time = datetime.now()
            
            # 发送任务完成通知
            await self.websocket_service.send_message(task.client_id, {
                "type": "search_task_update",
                "action": "complete",
                "task_id": task.task_id,
                "status": task.status,
                "error": task.error
            })