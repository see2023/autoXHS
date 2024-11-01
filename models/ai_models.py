import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Union

MessageRole = Enum("MessageRole", ["system", "user", "assistant", "function"])

# 定义 TextContent 类
@dataclass
class TextContent:
    type: str = "text"
    text: str = ""

# 定义 ImageContent 类
@dataclass
class ImageContent:
    type: str = "image_url"
    image_url: dict = field(default_factory=lambda: {"url": ""})

# 定义 Message 类，支持纯文本或多模态（TextContent 和 ImageContent）的 content
@dataclass
class Message:
    role: MessageRole
    content: Union[str, List[Union[TextContent, ImageContent]]]  # 支持字符串或多模态的列表

    def to_dict(self) -> dict:
        # 如果 content 是字符串，直接返回字符串格式
        if isinstance(self.content, str):
            return {"role": self.role.name, "content": self.content}
        
        # 如果 content 是列表
        if isinstance(self.content, list):
            # 如果列表中的元素已经是字典，直接使用
            if all(isinstance(item, dict) for item in self.content):
                return {
                    "role": self.role.name,
                    "content": self.content
                }
            # 否则，构造多模态格式
            return {
                "role": self.role.name,
                "content": [
                    {"type": "text", "text": item.text} if isinstance(item, TextContent) 
                    else {"type": "image_url", "image_url": item.image_url}
                    for item in self.content
                ]
            }
        
        # 如果 content 既不是字符串也不是列表，抛出异常
        raise ValueError("Content must be either a string or a list of TextContent, ImageContent, or dict objects")
    
    def from_dict(self, dict: dict):
        self.role = MessageRole[dict['role']]
        self.content = dict['content']
    
    def combine_content(self, content: Union[str, List[Union[TextContent, ImageContent]]]):
        if isinstance(self.content, str) and isinstance(content, str):
            self.content += "\n" + content
        elif isinstance(self.content, list) and isinstance(content, list):
            self.content.extend(content)
        elif isinstance(self.content, str) and isinstance(content, list):
            # 把 content 作为多模态消息追加到 self.content 后
            self.content = [TextContent(text=self.content)] + content
        elif isinstance(self.content, list) and isinstance(content, str):
            # 把 content 作为单个文本消息追加到 self.content 后
            self.content.append(TextContent(text=content))
        else:
            logging.error("Invalid content type for combining: %s, %s", type(self.content), type(content))
    
    def get_content_length(self) -> int:
        # 如果 content 是字符串，直接返回其长度
        if isinstance(self.content, str):
            return len(self.content)
        
        # 如果 content 是列表，计算文本和图片 URL 的长度
        length = 0
        for item in self.content:
            if isinstance(item, TextContent):
                length += len(item.text)
            elif isinstance(item, ImageContent):
                length += len(item.image_url.get("url", ""))
        return length