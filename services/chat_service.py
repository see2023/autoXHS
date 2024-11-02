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
from services.task_manager import TaskManager
from services.task_executor import TaskExecutor
from services.browser_service import BrowserService
from services.task_manager import TaskState, TaskEvent

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
        self._analyzing = False
        
        # 初始化任务管理器
        self.task_manager = TaskManager(self.websocket_service)
        self.browser_service = None
        self.task_executor = None

    @classmethod
    async def create(cls) -> 'ChatService':
        """异步工厂方法创建 ChatService 实例"""
        service = cls()
        await service.setup()
        return service

    async def setup(self):
        """异步初始化方法"""
        self.browser_service = await BrowserService.get_instance()
        self.task_executor = TaskExecutor(
            task_manager=self.task_manager,
            browser_service=self.browser_service,
            ai_service=self.ai_service,
            ai_service_mm=self.ai_service_mm
        )

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
                logger.debug("start analyze search intent")
                response = await self.ai_service.generate_response(messages, model=config.llm.get('model'))
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
                                "content": sentence,
                                "message_type": "chat"
                            })
            
            # 发送剩余的不完整句子
            if one_sentence:
                logger.info(f"Sending remaining text: {one_sentence}")
                if client_id:
                    await self.websocket_service.send_message(client_id, {
                        "type": "chat_response",
                        "content": one_sentence,
                        "message_type": "chat"
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
                # 创建待定状态的任务
                task_id = self.task_manager.create_pending_task(keywords, client_id)
                
                await self.websocket_service.send_message(client_id, {
                    "type": "search_intent",
                    "content": f"看起来您想搜索关于「{keywords}」的信息。要开始智能搜索任务吗？",
                    "keywords": keywords,
                    "task_id": task_id
                })
                logger.info(f'create pending task with keywords {keywords} and task_id {task_id}')

        except Exception as e:
            logger.error(f"Error in _handle_stream_response: {e}")
            if client_id:
                await self.websocket_service.send_message(client_id, {
                    "type": "error",
                    "content": str(e)
                })

    async def start_auto_search(self, keywords: str, client_id: str, task_id: str) -> dict:
        """开始自动搜索任务"""
        try:
            task = await self.task_manager.create_task(keywords, client_id, task_id)
            
            # 创建异步任务执行搜索
            asyncio.create_task(self.task_executor.execute_search_task(task))
            
            return {
                "status": "success",
                "task_id": task.task_id,
                "message": "搜索任务已启动"
            }
        except ValueError as e:
            return {
                "status": "error",
                "message": str(e),
                "task_id": task_id
            }
        except Exception as e:
            logger.error(f"Error starting search task: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    async def cancel_auto_search(self, task_id: str, client_id: str) -> dict:
        """取消搜索任务"""
        return await self.task_manager.cancel_task(task_id, client_id)

    async def get_search_tasks(self, client_id: str) -> dict:
        """获取客户端的所有搜索任务"""
        tasks = await self.task_manager.get_client_tasks(client_id)
        return {
            "status": "success",
            "tasks": tasks
        }

    async def submit_user_input(self, task_id: str, client_id: str, user_input: Dict) -> dict:
        """处理用户输入并继续任务"""
        try:
            # 更新任务状态
            await self.task_manager.receive_user_input(task_id, user_input)
            
            # 获取任务实例
            task = self.task_manager.tasks.get(task_id)
            if not task:
                return {
                    "status": "error",
                    "message": "Task not found"
                }
                
            # 如果用户选择继续搜索，重新启动搜索任务
            if user_input.get("continue_search"):
                asyncio.create_task(self.task_executor.execute_search_task(task))
                return {
                    "status": "success",
                    "message": "继续搜索"
                }
            else:
                # 如果用户选择查看结果，将任务标记为完成
                await self.task_manager.update_task_state(
                    task_id,
                    TaskState.COMPLETED,
                    TaskEvent.COMPLETE,
                    "用户选择查看结果，搜索结束"
                )
                return {
                    "status": "success",
                    "message": "搜索结束，准备展示结果"
                }
                
        except Exception as e:
            logger.error(f"Error submitting user input: {e}")
            return {
                "status": "error",
                "message": str(e)
            }