import base64
from typing import Union
from PIL import Image
import logging
# 读取图片文件并转换为base64
def image_file_to_base64(image_path: Union[str, Image.Image]) -> str:
    try:
        if isinstance(image_path, str):
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        elif isinstance(image_path, Image.Image):
            return base64.b64encode(image_path.tobytes()).decode('utf-8')
        else:
            logging.error(f"image_path must be a string or a PIL.Image.Image, but got {type(image_path)}")
            return ''
    except Exception as e:
        logging.error(f"image_file_to_base64 error: {e}")
        return ''