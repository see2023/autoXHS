import logging
from typing import Optional, List, Dict
from services.task_state import SearchTask, TaskState, TaskEvent
from services.task_manager import TaskManager
from services.browser_service import BrowserService
from services.ai_service import AIService
from models.ai_models import Message, MessageRole
from config.config_manager import config
import json
import re
from tools.json_tools import extract_json_from_text, extract_first_number

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self, task_manager: TaskManager, browser_service: BrowserService, 
                 ai_service: AIService, ai_service_mm: AIService):
        self.task_manager = task_manager
        self.browser_service = browser_service
        self.ai_service = ai_service  # 文本模型服务
        self.ai_service_mm = ai_service_mm  # 多模态模型服务
        # 从配置中读取参数
        self.max_notes_per_batch = config.get('task.max_notes_per_batch', 3)
        self.max_keywords_per_batch = config.get('task.max_keywords_per_batch', 2)
        self.max_batches = config.get('task.max_batches', 3)

    async def execute_search_task(self, task: SearchTask):
        """执行搜索任务的具体逻辑"""
        try:
            logger.debug(f"Starting search task: {task.task_id}, keywords: {task.keywords}")
            
            # 如果是首次执行，生成关键词并保存到context中
            if "all_keywords" not in task.context:
                # 发送开始搜索的消息
                await self.task_manager.websocket_service.send_message(task.client_id, {
                    "type": "chat_response",
                    "content": f"开始搜索「{task.keywords}」相内容...",
                    "message_type": "task_progress"
                })
                
                # 1. 生成搜索关键词组合
                all_keywords = await self._generate_search_keywords(task)
                if not all_keywords:
                    raise ValueError("Failed to generate search keywords")
                
                # 保存所有关键词到context
                task.keywords = " ".join(all_keywords)
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
            batch_start = current_batch * self.max_keywords_per_batch
            remaining_keywords = len(all_keywords) - batch_start
            if remaining_keywords <= self.max_keywords_per_batch + 1:
                # 如果剩余关键词数量小于等于正常批次大小+1，则一次性处理完
                batch_keywords = all_keywords[batch_start:]
            else:
                batch_keywords = all_keywords[batch_start:batch_start + self.max_keywords_per_batch]
            
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
            
            # 发送更新的任务状态到前端
            await self.task_manager.websocket_service.send_message(task.client_id, {
                "type": "search_task_update",
                "action": "progress",
                "task": task.to_dict()
            })
            
            # 执行搜索
            search_result = await self.browser_service.search_xiaohongshu(combined_keywords)
            if search_result["status"] == "success":
                notes = search_result["results"][:self.max_notes_per_batch]
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
            remaining_keywords = task.progress.keywords_total - task.progress.keywords_completed
            if remaining_keywords > 0:
                logger.debug(f"Batch completed, requesting user input for next batch. Remaining keywords: {remaining_keywords}")
                await self.task_manager.request_user_input(task.task_id, {
                    "type": "continue_search",
                    "message": f"已完成第 {current_batch + 1} 批搜索，还有 {remaining_keywords} 个关键词未处理: {', '.join(all_keywords[task.progress.keywords_completed:])}。是否继续搜索？",
                    "current_results": len(task.results),
                    "remaining_keywords": remaining_keywords
                })
                logger.info(f"User input requested for task {task.task_id}, waiting for response")
                return  # 等待用户响应

            # 所有批次都完成，进行综合分析
            logger.info(f"Task {task.task_id} completed with {len(task.results)} results")
            await self._analyze_all_opinions(task)  # 先进行分析
            await self._complete_task(task)  # 然后完成任务

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
            response = await self.ai_service.generate_response(messages, model=config.llm.get('model'))
            if not response:
                return [task.keywords]
                
            # 处理响应，分割关键词并清理，使用 ,; 中文逗号和顿号分割
            split_chars = ',;，、'
            keywords = []
            all_kw = re.split(f'[{split_chars}]', task.keywords) + re.split(f'[{split_chars}]', response)
            for kw in all_kw:
                kw = kw.strip(" \n\r\t,.。，、;；")
                # 过滤无效关键词
                if (len(kw) > 0 and len(kw) <= 30 and 
                    '\n' not in kw and '\r' not in kw):
                    keywords.append(kw)
            
            keywords = list(dict.fromkeys(keywords))
            logger.info(f"generated keywords: {keywords}")
            return keywords[:self.max_keywords_per_batch * self.max_batches]
            
        except Exception as e:
            logger.warning(f"Error generating keywords: {e}, return original keywords")
            return [task.keywords]  # 出错时返回原始关键词

    async def _process_notes(self, task: SearchTask, notes: List[Dict], keyword: str):
        """处理笔记列表"""
        logger.debug(f"Processing {len(notes)} notes for keyword: {keyword}")
        await self.task_manager.websocket_service.send_message(task.client_id, {
            "type": "search_task_update",
            "action": "progress",
            "task": task.to_dict()
        })
        
        # 存储当前批次的观点分析结果
        batch_opinions = []
        
        for j, note in enumerate(notes, 1):
            if task.state == TaskState.CANCELLED:
                break
                
            try:
                note_id = note.get("id", "unknown")
                note_title = note.get("title", "无标题")
                logger.debug(f"Processing note {j}/{len(notes)}: {note_id} - {note_title}")
                
                note_detail = await self.browser_service.open_note(
                    note["id"], 
                    note.get("xsec_token")
                )
                
                if note_detail["status"] == "success":
                    # 更新进度统计
                    task.progress.notes_processed += 1
                    comments = note_detail.get("comments_data", [])
                    task.progress.comments_total += len(comments)
                    task.progress.comments_processed += len(comments)
                    
                    # 分析观点
                    opinions = await self._analyze_note_opinions(
                        note_detail["note_data"],
                        comments
                    )
                    
                    if opinions and isinstance(opinions, dict): 
                        # 添加当前关键词信息
                        opinions["search_keyword"] = keyword
                        
                        # 将观点添加到当前批次
                        batch_opinions.append({
                            "keyword": keyword,
                            "note_id": note_id,
                            "note_title": note_title,
                            "opinions": opinions
                        })
                        
                        # 将观点添加到所有观点列表
                        if "all_opinions" not in task.context:
                            task.context["all_opinions"] = []
                        task.context["all_opinions"].append(opinions)
                        
                        try:
                            main_opinion = opinions.get('main_opinion', {})
                            supporting_opinions = opinions.get('supporting_opinions', [])
                            opposing_opinions = opinions.get('opposing_opinions', [])
                            
                            # 生成并发送单篇笔记的摘要
                            note_summary = [f"### {note_title}\n"]
                            
                            # 添加主要观点
                            if isinstance(main_opinion, dict):
                                note_summary.extend([
                                    f"**主要观点**：{main_opinion.get('content', '无')}\n",
                                    f"**可信度**：{main_opinion.get('confidence', 0)}/100\n"
                                ])
                            
                            # 添加支持观点
                            note_summary.append("\n**支持观点**：")
                            if isinstance(supporting_opinions, list) and supporting_opinions:
                                for op in supporting_opinions[:3]:  # 最多显示3个支持观点
                                    if isinstance(op, dict):
                                        note_summary.append(
                                            f"- {op.get('content', '无')} "
                                            f"(点赞：{op.get('metrics', {}).get('likes', 0)})"
                                        )
                            else:
                                note_summary.append("- 无支持观点")
                            
                            # 添加反对观点
                            note_summary.append("\n**反对观点**：")
                            if isinstance(opposing_opinions, list) and opposing_opinions:
                                for op in opposing_opinions[:3]:  # 最多显示3个反对观点
                                    if isinstance(op, dict):
                                        note_summary.append(
                                            f"- {op.get('content', '无')} "
                                            f"(点赞：{op.get('metrics', {}).get('likes', 0)})"
                                        )
                            else:
                                note_summary.append("- 无反对观点")
                            
                            # 将列表转换为字符串
                            note_summary = "\n".join(note_summary)
                            
                            await self.task_manager.websocket_service.send_message(task.client_id, {
                                "type": "chat_response",
                                "content": {
                                    "summary": note_summary,
                                    "note_id": note_id,
                                    "xsec_token": note.get("xsec_token"),
                                    "title": note_title
                                },
                                "message_type": "task_note_summary"
                            })
                            logger.debug(f"Sent note summary message for {note_id} - {note_title}")
                            
                        except Exception as e:
                            logger.error(f"Error generating note summary: {e}")
                            continue
                    
                    # 保存原始数据
                    task.results.append({
                        "keyword": keyword,
                        "note": note,
                        "detail": note_detail["note_data"],
                        "comments": comments,
                        "opinions": opinions
                    })
                    
                    logger.info(f"Note {note_id} - {note_title} processed with {len(comments)} comments and opinions analyzed")
                    
            except Exception as e:
                logger.error(f"Error processing note {note.get('id', 'unknown')}: {e}")
                continue
            await self.task_manager.websocket_service.send_message(task.client_id, {
                "type": "search_task_update",
                "action": "progress",
                "task": task.to_dict()
            })
        
        # 如果有观点分析结果，生成批次总结
        if batch_opinions:
            batch_summary = await self._summarize_batch_opinions(batch_opinions)
            if batch_summary:
                await self.task_manager.websocket_service.send_message(task.client_id, {
                    "type": "chat_response",
                    "content": f"\n### 本批次观点总结\n{batch_summary}",
                    "message_type": "task_batch_summary"
                })

        logger.info(f"Completed processing notes for keyword {keyword}, processed {task.progress.notes_processed} notes")

    async def _complete_task(self, task: SearchTask):
        """完成任务并生成可视化总结"""
        if task.state == TaskState.RUNNING:
            try:
                # 获取分析结果
                analysis_result = task.context.get("final_analysis")
                if not analysis_result:
                    logger.error("No final analysis found in task context")
                    raise ValueError("Missing analysis result")

                # 生成用户友好的总结
                visualization_data = await self._generate_user_summary(analysis_result)
                
                # 发送结果到客户端
                await self.task_manager.websocket_service.send_message(task.client_id, {
                    "type": "search_result",
                    "content": visualization_data
                })
                
                # 更新任务状态
                await self.task_manager.update_task_state(
                    task.task_id,
                    TaskState.COMPLETED,
                    TaskEvent.COMPLETE,
                    "分析完成"
                )
                
            except Exception as e:
                logger.error(f"Error generating final summary: {e}")
                await self.task_manager.update_task_state(
                    task.task_id,
                    TaskState.FAILED,
                    TaskEvent.FAIL,
                    f"生成总结失败: {str(e)}"
                )
                await self.task_manager.websocket_service.send_message(task.client_id, {
                    "type": "chat_response",
                    "content": f"可视化总结失败: {str(e)}",
                    "message_type": "task_progress"
                })

    async def _notify_progress(self, task: SearchTask, message: str):
        """通知任务进度"""
        logger.debug(f"notify_progress: {message} for task {task.task_id}")
        await self.task_manager.update_task_state(
            task.task_id,
            task.state,
            TaskEvent.PROGRESS,
            message
        )

    async def _analyze_note_opinions(self, note: Dict, comments: List[Dict]) -> Dict:
        """分析笔记和评论中的观点"""
        try:
            # 计算笔记的影响力分数
            interact_info = note.get("interact_info", {})
            note_influence = {
                "liked_count": interact_info.get("liked_count", 0),
                "collected_count": interact_info.get("collected_count", 0),
                "comment_count": interact_info.get("comment_count", 0),
                "share_count": interact_info.get("share_count", 0)
            }
            
            # 构建分析提示
            note_content = {
                "title": note.get("title", ""),
                "desc": note.get("desc", ""),
                "influence": note_influence
            }
            
            # 处理评论，包含点赞数和时间信息
            processed_comments = [
                {
                    "content": comment.get("content", ""),
                    "like_count": comment.get("like_count", 0),
                    "time": comment.get("create_time", ""),  # 如果API提供的话
                    "sub_comments_count": len(comment.get("sub_comments", []))
                }
                for comment in comments
            ]

            prompt = f"""分析以下小红书笔记及其评论中的观点，考虑内容的影响力:

笔记内容:
标题: {note_content['title']}
正文: {note_content['desc']}
影响力指标:
- 获赞: {note_influence['liked_count']}
- 收藏: {note_influence['collected_count']}
- 评论: {note_influence['comment_count']}
- 分享: {note_influence['share_count']}

评论数据:
{json.dumps(processed_comments, ensure_ascii=False, indent=2)}

请提取并分析所有观点，返回单个JSON格式(请不要添加破坏json格式的注释):
{{
    "note_influence_score": "基于获赞、收藏、评论、分享等计算的影响力得分 0-100",
    "main_opinion": {{
        "content": "主贴核心观点",
        "confidence": "基于内容质量和影响力的可信度 0-100",
        "keywords": ["关键词1", "关键词2"],
        "support_metrics": {{
            "likes": "获赞数",
            "collects": "收藏数",
            "shares": "分享数",
            "supporting_comments": "支持性评论数",
            "opposing_comments": "反对性评论数"
        }}
    }},
    "supporting_opinions": [
        {{
            "content": "支持性观点",
            "source": "主贴/评论",
            "confidence": "基于点赞数和评论质量的可信度 0-100",
            "keywords": ["关键词"],
            "metrics": {{
                "likes": "获赞数",
                "sub_comments": "子评论数"
            }}
        }}
    ],
    "opposing_opinions": [
        {{
            "content": "反对性观点",
            "source": "主贴/评论",
            "confidence": "基于点赞数和评论质量的可信度 0-100",
            "keywords": ["关键词"],
            "metrics": {{
                "likes": "获赞数",
                "sub_comments": "子评论数"
            }}
        }}
    ]
}}"""

            messages = [
                Message(role=MessageRole.system, content="你是一个专业的观点分析专家，善于从文本中提取观点并分析观点的倾向性。"),
                Message(role=MessageRole.user, content=prompt)
            ]
            
            logger.debug(f"start analyze_note_opinions: {note_content['title']}")
            response = await self.ai_service.generate_response(messages, model=config.llm.get('model'), json_mode=config.llm.get('support_json_mode'))
            # 使用 extract_json_from_text 处理 AI 返回的文本
            analysis_result = extract_json_from_text(response)
            if not analysis_result:
                logger.warning(f"Failed to extract JSON from AI response: {response}")
                return None
            
            # 添加笔记的元信息
            analysis_result["note_metadata"] = {
                "id": note.get("id"),
                "title": note_content["title"],
                "influence": note_influence,
                "create_time": note.get("create_time")
            }
            
            logger.info(f"Opinion analysis completed for note {note_content['title']} with influence score {analysis_result.get('note_influence_score')}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing opinions: {e}")
            return None

    async def _summarize_batch_opinions(self, batch_opinions: List[Dict]) -> str:
        """汇总分析一批笔记的观点"""
        try:
            prompt = f"""分析以下笔记中的观点汇总:

{json.dumps(batch_opinions, ensure_ascii=False, indent=2)}

请总结以下内容:
1. 主流观点有哪些（按可信度排序）
2. 存在哪些争议点
3. 各种观点的支持度如何
4. 是否存在明显的误导性信息

返回格式化的文本总结。"""

            messages = [
                Message(role=MessageRole.system, content="你是一个专业的观点分析专家，善于归纳总结和分析观点倾向。"),
                Message(role=MessageRole.user, content=prompt)
            ]
            
            logger.debug(f"start summarize_batch_opinions")
            summary = await self.ai_service.generate_response(messages, model=config.llm.get('model'))
            return summary
            
        except Exception as e:
            logger.error(f"Error summarizing batch opinions: {e}")
            return "观点汇总分析失败"

    async def _analyze_all_opinions(self, task: SearchTask):
        """综合分析所有批次的观点"""
        try:
            all_opinions = task.context.get("all_opinions", [])
            if not all_opinions or len(all_opinions) == 0:
                logger.warning("No opinions found in task context")
                # 创建基础分析结果，包含统计数据
                basic_analysis = {
                    "stats": {
                        "total_notes": task.progress.notes_processed,
                        "total_comments": task.progress.comments_processed,
                        "total_keywords": task.progress.keywords_completed
                    },
                    "trending_opinions": [],
                    "controversial_points": [],
                    "time_based_analysis": {
                        "opinion_shifts": [],
                        "emerging_topics": [],
                        "fading_topics": []
                    }
                }
                task.context["final_analysis"] = basic_analysis
                return
                
            prompt = f"""分析以下所有笔记中的观点，考虑每个笔记的影响力和时间因素:

观点数据:
{json.dumps(all_opinions, ensure_ascii=False, indent=2)}

请综合分析并返回如下单个JSON格式(请不要添加破坏json格式的注释):
{{
    "trending_opinions": [
        {{
            "content": "主流观点",
            "confidence": "综合可信度 0-100",
            "support_level": "支持度 0-100",
            "influence_score": "影响力得分 0-100",
            "keywords": ["关键词"],
            "sources": ["笔记ID列表"],
            "trend": "上升/稳定/下降" 
        }}
    ],
    "controversial_points": [
        {{
            "topic": "争议点",
            "supporting_view": "支持方观点",
            "opposing_view": "反对方观点",
            "support_ratio": "支持比例 0-100",
            "discussion_heat": "讨论热度 0-100"
        }}
    ],
    "time_based_analysis": {{
        "opinion_shifts": ["观点变化趋势"],
        "emerging_topics": ["新兴话题"],
        "fading_topics": ["减弱话题"]
    }}
}}"""

            messages = [
                Message(role=MessageRole.system, 
                       content="你是一个专业的观点分析专家。请严格按照指定的JSON格式输出，不要添加任何其他文字。"),
                Message(role=MessageRole.user, content=prompt)
            ]
            
            logger.debug(f"start analyze_all_opinions")
            summary = await self.ai_service.generate_response(messages, model=config.llm.get('model'), json_mode=config.llm.get('support_json_mode'))
            # 使用 extract_json_from_text 处理 AI 返回的文本
            analysis_result = extract_json_from_text(summary)
            if not analysis_result:
                logger.warning(f"Failed to get valid JSON from response")
                return "观点综合分析失败"
            
            # 添加统计数据
            analysis_result["stats"] = {
                "total_notes": task.progress.notes_processed,
                "total_comments": task.progress.comments_processed,
                "total_keywords": task.progress.keywords_completed
            }
            
            # 保存综合分析结果
            task.context["final_analysis"] = analysis_result
            
        except Exception as e:
            logger.error(f"Error in comprehensive opinion analysis: {e}")
            return "观点综合分析失败"

    async def _generate_user_summary(self, analysis_result: Dict) -> Dict:
        """生成用户友好的分析总结，包含可视化数据"""
        try:
            # 生成 Markdown 格式的文字总结
            prompt = f"""基于以下分析结果，生成一个用户友好的总结，使用Markdown格式:
{json.dumps(analysis_result, ensure_ascii=False, indent=2)}

要求：
1. 使用清晰的标题层级
2. 突出主要观点和趋势
3. 说明争议点的不同立场
4. 指出时间维度的变化
5. 提供可操作的见解

格式示例：
# 总体分析
[总体趋势和主要发现]

## 主要观点
- 观点1
- 观点2

## 争议焦点
1. [争议点1]
   - 支持方：xxx
   - 反对方：xxx

## 时间趋势
[时间维度的变化分析]

## 建议
[基于分析的建议]
"""
            messages = [
                Message(role=MessageRole.system, 
                       content="你是一个善于将专业分析转化为用户友好内容的AI助手。"),
                Message(role=MessageRole.user, content=prompt)
            ]
            
            logger.debug(f"start generate_user_summary")
            text_summary = await self.ai_service.generate_response(
                messages, 
                model=config.llm.get('model')
            )
            logger.debug(f"text_summary: {text_summary}")
            
            # 使用实际的统计数据
            stats = analysis_result.get("stats", {})
            return {
                "basic_stats": {
                    "keywords_processed": stats.get("total_keywords", 0),
                    "total_notes": stats.get("total_notes", 0),
                    "total_comments": stats.get("total_comments", 0)
                },
                "text_summary": text_summary,
                "visualization_data": {
                    "word_cloud": {
                        "title": "关键词权重分布",
                        "data": [
                            {"text": keyword, "weight": confidence}
                            for opinion in analysis_result.get("trending_opinions", [])
                            for keyword, confidence in zip(
                                opinion.get("keywords", []), 
                                [extract_first_number(opinion.get("confidence", "0"))] * len(opinion.get("keywords", []))
                            )
                        ]
                    },
                    "opinion_distribution": {
                        "title": "主要观点分布",
                        "data": [
                            {
                                "content": opinion.get("content", ""),  # 完整观点内容
                                "support_level": extract_first_number(opinion.get("support_level", "0")),  # 支持度
                                "confidence": extract_first_number(opinion.get("confidence", "0")),  # 可信度
                                "influence_score": extract_first_number(opinion.get("influence_score", "0"))  # 影响力
                            }
                            for opinion in analysis_result.get("trending_opinions", [])
                        ]
                    },
                    "controversy_analysis": {
                        "title": "主要争议点",
                        "data": [
                            {
                                "topic": point.get("topic", ""),  # 争议主题
                                "support_ratio": extract_first_number(point.get("support_ratio", "0")),  # 支持比例
                                "discussion_heat": extract_first_number(point.get("discussion_heat", "0")),  # 讨论热度
                                "supporting_view": point.get("supporting_view", ""),  # 支持方观点
                                "opposing_view": point.get("opposing_view", "")  # 反对方观点
                            }
                            for point in analysis_result.get("controversial_points", [])
                        ]
                    }
                }
            }
                
        except Exception as e:
            logger.error(f"Error generating visualization data: {e}")
            # 出错时返回基础统计数据
            stats = analysis_result.get("stats", {})
            return {
                "basic_stats": {
                    "keywords_processed": stats.get("total_keywords", 0),
                    "total_notes": stats.get("total_notes", 0),
                    "total_comments": stats.get("total_comments", 0)
                },
                "text_summary": "无法生成分析总结",
                "error": str(e)
            }