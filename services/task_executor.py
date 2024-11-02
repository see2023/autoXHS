import logging
from typing import Optional, List, Dict
from services.task_state import SearchTask, TaskState, TaskEvent
from services.task_manager import TaskManager
from services.browser_service import BrowserService
from services.ai_service import AIService
from models.ai_models import Message, MessageRole
from config.config_manager import config

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self, task_manager: TaskManager, browser_service: BrowserService, 
                 ai_service: AIService, ai_service_mm: AIService):
        self.task_manager = task_manager
        self.browser_service = browser_service
        self.ai_service = ai_service  # 文本模型服务
        self.ai_service_mm = ai_service_mm  # 多模态模型服务

    async def execute_search_task(self, task: SearchTask):
        """执行搜索任务的具体逻辑"""
        try:
            logger.debug(f"Starting search task: {task.task_id}, keywords: {task.keywords}")
            
            # 从配置中读取参数
            MAX_NOTES_PER_BATCH = config.get('task.max_notes_per_batch', 5)
            MAX_KEYWORDS_PER_BATCH = config.get('task.max_keywords_per_batch', 2)  # 改为2个关键词一组
            
            # 如果是首次执行，生成关键词并保存到context中
            if "all_keywords" not in task.context:
                # 发送开始搜索的消息
                await self.task_manager.websocket_service.send_message(task.client_id, {
                    "type": "chat_response",
                    "content": f"开始搜索「{task.keywords}」相关内容...",
                    "message_type": "task_progress"
                })
                
                # 1. 生成搜索关键词组合
                all_keywords = await self._generate_search_keywords(task)
                if not all_keywords:
                    raise ValueError("Failed to generate search keywords")
                
                # 保存所有关键词到context
                task.context["all_keywords"] = all_keywords
                task.context["current_batch"] = 0
                
                # 发送关键词生成完成的消息
                await self.task_manager.websocket_service.send_message(task.client_id, {
                    "type": "chat_response",
                    "content": f"已生成搜索关键词：{', '.join(all_keywords)}",
                    "message_type": "task_progress"
                })
            
            # 获取当前批次和所有关键词
            all_keywords = task.context["all_keywords"]
            current_batch = task.context["current_batch"]
            
            # 处理当前批次的关键词，如果剩下最后一个关键词，合并到当前批次
            batch_start = current_batch * MAX_KEYWORDS_PER_BATCH
            remaining_keywords = len(all_keywords) - batch_start
            if remaining_keywords <= MAX_KEYWORDS_PER_BATCH + 1:
                # 如果剩余关键词数量小于等于正常批次大小+1，则一次性处理完
                batch_keywords = all_keywords[batch_start:]
            else:
                batch_keywords = all_keywords[batch_start:batch_start + MAX_KEYWORDS_PER_BATCH]
            
            logger.debug(f"Processing batch {current_batch + 1}, keywords: {batch_keywords}")
            
            # 组合关键词进行搜索
            combined_keywords = " ".join(batch_keywords)
            await self._notify_progress(task, f"正在搜索关键词组合：{combined_keywords}")
            
            # 更新进度信息，累加之前的结果
            task.progress.keywords_total = len(all_keywords)
            task.progress.keywords_completed = batch_start + len(batch_keywords)
            task.progress.notes_total = task.progress.notes_total or 0  # 保留之前的总数
            task.progress.notes_processed = task.progress.notes_processed or 0  # 保留之前的处理数
            task.progress.comments_total = task.progress.comments_total or 0  # 保留之前的评论总数
            task.progress.comments_processed = task.progress.comments_processed or 0  # 保留之前的处理数
            
            # 执行搜索
            search_result = await self.browser_service.search_xiaohongshu(combined_keywords)
            if search_result["status"] == "success":
                notes = search_result["results"][:MAX_NOTES_PER_BATCH]
                task.progress.notes_total += len(notes)
                await self._process_notes(task, notes, combined_keywords)
            
            # 发送批次完成的消息
            batch_summary = (
                f"完成第 {current_batch + 1} 批搜索（关键词：{combined_keywords}），"
                f"累计处理 {task.progress.notes_processed} 篇笔记，"
                f"获取 {task.progress.comments_processed} 条评论。"
            )
            await self.task_manager.websocket_service.send_message(task.client_id, {
                "type": "chat_response",
                "content": batch_summary,
                "message_type": "task_progress"
            })

            # 更新当前批次
            task.context["current_batch"] = current_batch + 1
            
            # 检查是否还有下一批
            remaining_keywords = len(all_keywords) - (batch_start + len(batch_keywords))
            if remaining_keywords > 0:
                logger.debug(f"Batch completed, requesting user input for next batch. Remaining keywords: {remaining_keywords}")
                await self.task_manager.request_user_input(task.task_id, {
                    "type": "continue_search",
                    "message": f"已完成第 {current_batch + 1} 批搜索，还有 {remaining_keywords} 个关键词未处理。是否继续搜索？",
                    "current_results": len(task.results),
                    "remaining_keywords": remaining_keywords
                })
                logger.info(f"User input requested for task {task.task_id}, waiting for response")
                return  # 等待用户响应

            # 所有批次都完成
            logger.info(f"Task {task.task_id} completed with {len(task.results)} results")
            await self._complete_task(task)

        except Exception as e:
            logger.error(f"Error in search task: {e}")
            await self.task_manager.websocket_service.send_message(task.client_id, {
                "type": "chat_response",
                "content": f"搜索任务执行出错：{str(e)}",
                "message_type": "task_progress"
            })
            await self.task_manager.update_task_state(
                task.task_id,
                TaskState.FAILED,
                TaskEvent.FAIL,
                str(e)
            )

    async def _generate_search_keywords(self, task: SearchTask) -> List[str]:
        """Generate search keywords using AI"""
        try:
            prompt = f"""Based on the topic "{task.keywords}", generate 3-5 related search keyword combinations.
Requirements:
1. Keywords must be specific and targeted
2. Consider different search angles
3. Each keyword should be 2-6 characters
4. Return keywords directly, separated by English commas
5. Do not include any explanations or other text

Input example: 遛狗 (walking dogs)
Output example: 遛狗技巧,狗狗训练,遛狗装备,遛狗注意事项"""

            messages = [
                Message(role=MessageRole.system, content="You are a search keyword optimization expert. Return only keywords without explanations."),
                Message(role=MessageRole.user, content=prompt)
            ]
            
            logger.debug(f"starting generate_search_keywords: {task.keywords}")
            response = await self.ai_service.generate_response(messages)
            if not response:
                return [task.keywords]
                
            # 处理响应，分割关键词并清理
            keywords = []
            for kw in response.split(','):
                kw = kw.strip()
                # 过滤无效关键词
                if (len(kw) > 0 and len(kw) <= 30 and 
                    '\n' not in kw and '\r' not in kw and 
                    '.' not in kw and len(keywords) < 5):
                    keywords.append(kw)
            
            # 确保原始关键词也包含在内
            if task.keywords not in keywords:
                keywords.insert(0, task.keywords)
            
            logger.info(f"generated keywords: {keywords}")
            return keywords[:5]  # 最多返回5个关键词
            
        except Exception as e:
            logger.error(f"Error generating keywords: {e}")
            return [task.keywords]  # 出错时返回原始关键词

    async def _process_notes(self, task: SearchTask, notes: List[Dict], keyword: str):
        """处理笔记列表"""
        logger.debug(f"Processing {len(notes)} notes for keyword: {keyword}")
        for j, note in enumerate(notes, 1):
            if task.state == TaskState.CANCELLED:
                break
                
            try:
                await self._notify_progress(
                    task, 
                    f"正在处理笔记 ({j}/{len(notes)}): {note.get('title', '无标题')}"
                )
                note_id = note.get("id", "unknown")
                note_title = note.get("title", "无标题")
                logger.debug(f"Processing note {j}/{len(notes)}: {note_id} - {note_title}")

                
                note_detail = await self.browser_service.open_note(
                    note["id"], 
                    note.get("xsec_token")
                )
                
                if note_detail["status"] == "success":
                    comments_count = len(note_detail.get("comments_data", []))
                    logger.info(f"Note {note_id} - {note_title} processed successfully with {comments_count} comments")
                    task.progress.notes_processed += 1
                    comments = note_detail.get("comments_data", [])
                    task.progress.comments_total += len(comments)
                    task.progress.comments_processed += len(comments)
                    
                    task.results.append({
                        "keyword": keyword,
                        "note": note,
                        "detail": note_detail["note_data"],
                        "comments": comments
                    })
                    
            except Exception as e:
                logger.error(f"Error processing note {note.get('id', 'unknown')}: {e}")
                continue

        logger.info(f"Completed processing notes for keyword {keyword}, processed {task.progress.notes_processed} notes")

    async def _complete_task(self, task: SearchTask):
        """完成任务"""
        if task.state == TaskState.RUNNING:
            summary = (
                f"搜索完成。共处理 {task.progress.keywords_completed}/{task.progress.keywords_total} 个关键词, "
                f"获取 {task.progress.notes_processed} 篇笔记, "
                f"{task.progress.comments_processed} 条评论"
            )
            logger.info(f"Task {task.task_id} summary: {summary}")
            
            # 发送任务完成消息到对话框
            await self.task_manager.websocket_service.send_message(task.client_id, {
                "type": "chat_response",
                "content": summary
            })
            
            # 更新任务状态
            await self.task_manager.update_task_state(
                task.task_id,
                TaskState.COMPLETED,
                TaskEvent.COMPLETE,
                summary
            )

    async def _notify_progress(self, task: SearchTask, message: str):
        """通知任务进度"""
        logger.debug(f"notify_progress: {message} for task {task.task_id}")
        await self.task_manager.update_task_state(
            task.task_id,
            task.state,
            TaskEvent.PROGRESS,
            message
        )