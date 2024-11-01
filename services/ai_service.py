import base64
import logging
import os
import asyncio
from typing import List
from models.ai_models import Message, MessageRole
from config.config_manager import config
import openai
from tools.image_tools import image_file_to_base64
from PIL import Image

class AIService:
    def __init__(self, max_images: int = 2, base_url: str = None, api_key: str = None):
        if not base_url:
            base_url = config.llm.get('openai_custom_mm_url')
        self._base_url = base_url
        if not api_key:
            api_key = os.getenv(config.llm.get('openai_custom_key_envname_mm'))
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=self._base_url)
        self._max_images = max_images

    def _process_messages(self, messages: List[Message]) -> List[Message]:
        """Process messages to ensure image count is within limits"""
        image_count = 0
        for msg in messages:
            if isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and item.get('type') == "image_url":
                        image_count += 1
                        
        if image_count > self._max_images:
            while image_count > self._max_images:
                for msg in messages:
                    if isinstance(msg.content, list):
                        for item in msg.content:
                            if isinstance(item, dict) and item.get('type') == "image_url":
                                msg.content.remove(item)
                                image_count -= 1
                                logging.debug(f"Remove image, current image_count: {image_count}")
                                break
                    if image_count <= self._max_images:
                        break
        return messages

    async def generate_response(self, messages: List[Message], model: str = "Qwen/Qwen2-VL-2B-Instruct-AWQ") -> str:
        messages = self._process_messages(messages)
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[message.to_dict() for message in messages],
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f'send message to {self._base_url} error: {e}')
            return ''

    async def generate_response_stream(self, messages: List[Message], model: str = "Qwen/Qwen2-VL-2B-Instruct-AWQ"):
        """Stream version of generate_response"""
        messages = self._process_messages(messages)
        try:
            response_stream = await self._client.chat.completions.create(
                model=model,
                messages=[message.to_dict() for message in messages],
                stream=True
            )
            async for chunk in response_stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logging.error(f'Stream response error: {e}')
            yield f"Error: {str(e)}"

    async def ocr(self, image_path: str = None, image_content_base64: str = None, model: str = "Qwen/Qwen2-VL-2B-Instruct-AWQ") -> str:
        image_base64 = None
        if image_path:
            image_base64 = image_file_to_base64(image_path) 
        elif image_content_base64:
            image_base64 = image_content_base64
        else:
            raise ValueError("image_path or image_content is required")
        messages = [
            Message(role=MessageRole.system, content="""You are a professional OCR model. Your task is to accurately recognize and output ALL text from images, especially Chinese text.
Requirements:
1. Maintain the original text format and layout
2. Recognize ALL text completely, including Chinese characters, numbers, and punctuation
3. Do not skip any text or characters
4. For image-text combinations, focus on actual text content
5. Output raw text only, no explanations"""),
            
            Message(role=MessageRole.user, content=[
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": "Extract text from this social media content image. Focus on Chinese text recognition."}
            ]),
        ]
        
        try:
            response = await self.generate_response(messages, model=model)
            if not response.strip():  # 如果返回为空或者只有空白字符
                logging.warning("OCR returned empty result, retrying...")
                response = await self.generate_response(messages, model=model)  # 简单的重试一次
            return response
        except Exception as e:
            logging.error(f"OCR failed: {str(e)}")
            raise
        



async def main():
    # 配置日志
    logging.basicConfig(level=logging.INFO, 
        format='%(asctime)s - %(levelname)s [in %(pathname)s:%(lineno)d] - %(message)s')
    ai_service = AIService()
    if False:
        # 使用 os.path.expanduser() 展开 ~ 符号
        image_path3 = os.path.expanduser("~/Pictures/boy3.jpg")
        image_path2 = os.path.expanduser("~/Pictures/boy2.jpg")
        image_path1 = os.path.expanduser("~/Pictures/boy1.jpg")
        logging.info(f"Image path: {image_path3}")

        # 将图片转换为base64
        image_base64_3 = image_file_to_base64(image_path3)
        logging.debug(f"Image base64: {image_base64_3[:50]}...")  # 只打印前50个字符
        image_base64_2 = image_file_to_base64(image_path2)
        image_base64_1 = image_file_to_base64(image_path1)

        # 创建 Message 对象
        messages = [
            Message(
                role=MessageRole.system,
                content="你是一个儿童心理学家，请根据图片中的孩子回答问题。"
            ),
            Message(
                role=MessageRole.user,
                content=[
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64_3}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64_2}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64_1}"}},
                {"type": "text", "text": "图中的孩子们在干嘛？他们坐的端正吗？他们开心吗？"}
            ]
            )
        ]
        response = await ai_service.generate_response(messages, model=config.llm.get('openai_custom_mm_model'))
        logging.info(f"Response: {response}")

    if True:
        ocr_image_path = os.path.expanduser("~/Pictures/exam_en.jpg")
        ocr_image_path = './tmp/screenshot_20241030_151358.png'
        response = await ai_service.ocr(image_path=ocr_image_path, model=config.llm.get('openai_custom_mm_model'))
        logging.info(f"OCR Response: {response}")

if __name__ == "__main__":
    asyncio.run(main())
