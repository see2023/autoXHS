import json
import logging
import re

logger = logging.getLogger(__name__)

def extract_json_from_text(text: str) -> dict:
    """从文本中提取JSON对象
    
    Args:
        text: 可能包含JSON的文本字符串
        
    Returns:
        解析后的JSON对象,如果解析失败返回None
        
    Example:
        >>> text = "some text before { \"key\": \"value\" } some text after"
        >>> result = extract_json_from_text(text)
        >>> print(result)
        {'key': 'value'}
    """
    try:
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 查找第一个 { 和最后一个 }
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            json_str = text[start_idx:end_idx + 1]
            return json.loads(json_str)
            
        logger.warning(f"No valid JSON found in text: {text}")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting JSON from text: {e}, text: {text}")
        return None 

# 从字符串提取第一个数字  "综合可信度 50 左右， 返回 50"
def extract_first_number(text: str) -> int:
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 0