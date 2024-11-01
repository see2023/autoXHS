import os
import logging
import time
from PIL import Image
from io import BytesIO
import base64
import asyncio
import json
from config.config_manager import config
from services.ai_service import AIService
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager

logger = logging.getLogger(__name__)

class BrowserService:
    def __init__(self):
        self.driver = None
        chrome_config = config.chrome
        self.debug_port = chrome_config['debug_port']
        self.user_data_dir = chrome_config['user_data_dir']

    async def start_browser(self):
        """启动浏览器"""
        try:
            logger.info("Starting browser...")
            
            os.makedirs(self.user_data_dir, exist_ok=True)
            
            # 设置 Chrome 选项
            chrome_options = Options()
            chrome_options.add_argument(f'--remote-debugging-port={self.debug_port}')
            # chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument(f'--user-data-dir={self.user_data_dir}')
            chrome_options.add_argument('--profile-directory=Default')

            # Add CDP (Chrome DevTools Protocol) logging
            chrome_options.set_capability(
                "goog:loggingPrefs", {"performance": "ALL"}
            )

            cache_manager = DriverCacheManager(valid_range=7)
            service = Service(
                ChromeDriverManager(
                    cache_manager=cache_manager
                ).install()
            )
            
            self.driver = webdriver.Chrome(
                service=service,
                options=chrome_options
            )
            
            logger.info("Browser started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
            raise

    async def open_xiaohongshu(self):
        """打开小红书"""
        try:
            if not self.driver:
                await self.start_browser()
            logger.debug("Opening Xiaohongshu...")
            self.driver.get('https://www.xiaohongshu.com')
            return True
        except Exception as e:
            logger.error(f"Error opening xiaohongshu: {e}")
            return False

    async def scroll_screenshot_and_ocr(self):
        """滚动、截图并进行OCR识别"""
        try:
            if not self.driver:
                await self.start_browser()
            
            logger.debug("Scrolling, taking screenshot, and performing OCR...")
            
            # 检查连接状态
            if not await self.is_browser_connected():
                return

            # 执行滚动
            actions = ActionChains(self.driver)
            actions.send_keys(Keys.PAGE_DOWN).perform()
            
            # 等待页面加载和动画完成
            await asyncio.sleep(1)

            # 获取截图
            screenshot = self.driver.get_screenshot_as_png()
            
            # 处理图片
            img = Image.open(BytesIO(screenshot))
            img.thumbnail((800, 800))  # 调整图片大小
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            if config.get('app.debug'):
                tmp_img_path = os.path.join(config.get('app.tmp_dir'), f'screenshot_{time.strftime("%Y%m%d_%H%M%S")}.png')
                img.save(tmp_img_path)
                logger.debug(f"Screenshot saved to {tmp_img_path}")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            # 调用 OCR 服务
            ai_service = AIService()
            ocr_text = await ai_service.ocr(image_content_base64=img_str, model=config.llm.get('openai_custom_mm_model'))
            logger.info(f"OCR Text: {ocr_text}")

            return {
                'status': 'success',
                'image': img_str,
                'ocr_text': ocr_text
            }
        except Exception as e:
            logger.error(f"Error in scroll_screenshot_and_ocr: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    async def is_browser_connected(self):
        """检查浏览器是否连接"""
        try:
            # 尝试获取当前窗口句柄
            self.driver.current_window_handle
            return True
        except:
            logger.warning("Browser disconnected, restarting...")
            await self.cleanup_chrome_instance()
            await self.start_browser()
            return False

    async def cleanup_chrome_instance(self):
        """清理Chrome实例"""
        if self.driver:
            logger.info("Cleaning up Chrome instance...")
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    async def search_xiaohongshu(self, keyword):
        """搜索小红书内容并捕获接口返回"""
        try:
            if not self.driver:
                await self.start_browser()
        
            logger.debug(f"Searching Xiaohongshu for: {keyword}")
            
            # 导航到搜索页面前先清除日志
            self.driver.get_log("performance")
            
            # 导航到搜索页面
            search_url = f'https://www.xiaohongshu.com/search_result?keyword={keyword}'
            self.driver.get(search_url)
            
            try:
                # 等待搜索结果加载完成 - 等待笔记卡片出现
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".note-item"))
                )
                logger.debug(f"Search {keyword} results loaded")
            except Exception as e:
                logger.warning(f"Timeout waiting for search results: {e}")
                pass
            await asyncio.sleep(1)
            
            # 获取网络请求日志
            logs = self.driver.get_log("performance")
            search_results = []
            logger.debug(f'Got {len(logs)} performance logs')
            
            for log in logs:
                try:
                    message = json.loads(log.get("message", "{}"))
                    method = message.get('message', {}).get('method')
                    if method != "Network.responseReceived":
                        continue
                    message_params = message.get("message", {}).get("params", {})
                    
                    if not message_params:
                        continue
                        
                    request_id = message_params.get("requestId")
                    response = message_params.get("response", {})
                    resp_url = response.get("url", "")
                    if not request_id or not resp_url or response.get("status") not in [200, 201]:
                        continue
                    
                    if "api/sns/web/v1/search/notes" in resp_url:
                        response_body = self.driver.execute_cdp_cmd(
                            "Network.getResponseBody", {"requestId": request_id}
                        )
                        
                        if response_body and "body" in response_body:
                            data = json.loads(response_body["body"])
                            if "data" in data and "items" in data["data"]:
                                for item in data["data"]["items"]:
                                    if "note_card" in item and "model_type" in item and item["model_type"] == "note":
                                        note = item["note_card"]
                                        search_results.append({
                                            "id": item.get("id"),
                                            "xsec_token": item.get("xsec_token"),
                                            "type": note.get("type"),
                                            "title": note.get("display_title"),
                                            "cover_url": note.get("cover", {}).get("url_default"),
                                            "nickname": note.get("user", {}).get("nickname"),
                                            "liked_count": note.get("interact_info", {}).get("liked_count")
                                        })
                                logger.info(f'Got {len(search_results)} search results')
                                return {
                                    "status": "success",
                                    "results": search_results
                                }
                
                except Exception as e:
                    logger.error(f"Error processing log entry: {e}")
                    continue
            
            logger.info(f'Got {len(search_results)} search results')
            return {
                "status": "success",
                "results": search_results
            }
            
        except Exception as e:
            logger.error(f"Error in search_xiaohongshu: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    async def open_note(self, note_id: str, xsec_token: str):
        """打开指定的笔记并获取详细信息"""
        try:
            if not self.driver:
                await self.start_browser()
            
            # 检查当前是否在笔记页面
            current_url = self.driver.current_url
            if 'explore' in current_url:
                # 如果当前在笔记页，先后退到搜索页
                logger.debug("Current page is note page, going back to search page")
                self.driver.back()
                # 等待搜索页面加载完成（等待笔记卡片出现）
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".note-item"))
                    )
                    logger.debug("Back to search page successfully")
                except Exception as e:
                    logger.warning(f"Timeout waiting for back to search page: {e}")
                await asyncio.sleep(1)

            # 清除性能日志
            self.driver.get_log("performance")

            # 尝试在当前页面找到目标笔记的链接
            try:
                # 使用更精确的选择器，查找带有图片的可见链接
                note_link_selector = f"a.cover[href*='{note_id}']"
                logger.debug(f"Trying to find note link with selector: {note_link_selector}")
                
                # 等待元素存在
                note_link = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, note_link_selector))
                )
                
                # 获取元素位置信息进行调试
                location = note_link.location
                size = note_link.size
                logger.debug(f"Found note link at position: {location}, size: {size}")
                
                # 确保元素在视图中
                self.driver.execute_script("arguments[0].scrollIntoView(true);", note_link)
                await asyncio.sleep(0.5)  # 等待滚动完成
                
                # 使用JavaScript点击元素
                logger.debug("Clicking note link using JavaScript")
                self.driver.execute_script("arguments[0].click();", note_link) 
                
            except Exception as e:
                # 找不到链接，使用直接访问的方式
                logger.debug(f"Note link not found, directly navigating to note page: {e}")
                note_url = f'https://www.xiaohongshu.com/explore/{note_id}'
                if xsec_token:
                    note_url += f'?xsec_token={xsec_token}'
                self.driver.get(note_url)
            
            # 等待笔记内容加载
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".note-content"))
            )
            await asyncio.sleep(1)
            
            # 获取网络请求日志
            logs = self.driver.get_log("performance")
            note_data = {}
            comments_data = []
            
            for log in logs:
                try:
                    message = json.loads(log.get("message", "{}"))
                    method = message.get('message', {}).get('method')
                    if method != "Network.responseReceived":
                        continue
                    
                    message_params = message.get("message", {}).get("params", {})
                    if not message_params:
                        continue
                    
                    request_id = message_params.get("requestId")
                    response = message_params.get("response", {})
                    resp_url = response.get("url", "")
                    
                    if not request_id or response.get("status") not in [200, 201]:
                        continue

                    # 获取笔记详情
                    if "api/sns/web/v1/feed" in resp_url:
                        if not request_id:
                            logger.debug("No request id found in feed response")
                            continue
                        response_body = self.driver.execute_cdp_cmd(
                            "Network.getResponseBody", {"requestId": request_id}
                        )
                        if response_body and "body" in response_body:
                            data = json.loads(response_body["body"])
                            if "data" in data and "items" in data["data"] and len(data["data"]["items"]) > 0:
                                note = data["data"]["items"][0]["note_card"]
                                note_data = {
                                    "topics": [tag["name"] for tag in note.get("tag_list", [])],
                                    "desc": note.get("desc", ""),
                                    "title": note.get("title", ""),
                                    "type": note.get("type", ""),
                                    "images": [],
                                    "interact_info": {
                                        "share_count": note.get("interact_info", {}).get("share_count", "0"),
                                        "collected_count": note.get("interact_info", {}).get("collected_count", "0"),
                                        "comment_count": note.get("interact_info", {}).get("comment_count", "0"),
                                        "liked_count": note.get("interact_info", {}).get("liked_count", "0")
                                    }
                                }
                                
                                # 获取图片列表
                                for img in note.get("image_list", []):
                                    for info in img.get("info_list", []):
                                        if info.get("image_scene") == "WB_DFT":
                                            note_data["images"].append(info.get("url"))
                                            break
                
                    # 获取评论
                    elif "api/sns/web/v2/comment/page" in resp_url:
                        if not request_id:
                            logger.debug("No request id found in comment response")
                            continue
                        response_body = self.driver.execute_cdp_cmd(
                            "Network.getResponseBody", {"requestId": request_id}
                        )
                        if response_body and "body" in response_body:
                            data = json.loads(response_body["body"])
                            if "data" in data and "comments" in data["data"]:
                                for comment in data["data"]["comments"]:
                                    comment_data = {
                                        "content": comment.get("content", ""),
                                        "like_count": comment.get("like_count", "0"),
                                        "sub_comments": []
                                    }
                                    
                                    # 获取子评论
                                    for sub_comment in comment.get("sub_comments", []):
                                        comment_data["sub_comments"].append({
                                            "content": sub_comment.get("content", ""),
                                            "like_count": sub_comment.get("like_count", "0")
                                        })
                                        
                                    comments_data.append(comment_data)
            
                except Exception as e:
                    logger.warning(f"Error processing log entry: {e}")
                    continue
            
            logger.info(f"Note {note_id} data captured successfully, got {len(comments_data)} comments")
            return {
                "status": "success",
                "note_data": note_data,
                "comments_data": comments_data
            }
            
        except Exception as e:
            logger.error(f"Error opening note: {e}")
            return {
                "status": "error",
                "message": str(e)
            }