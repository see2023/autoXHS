import os
import yaml
from typing import Any, Dict
from pathlib import Path

class ConfigManager:
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._load_config()

    def _load_config(self):
        """加载配置文件并处理环境变量覆盖"""
        config_path = Path(__file__).parent / 'config.yaml'
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

        self._process_env_overrides()
        
        self._process_special_configs()

    def _process_env_overrides(self):
        """处理环境变量覆盖"""
        if os.getenv('DEBUG'):
            self._config['debug'] = os.getenv('DEBUG').lower() == 'true'
            
    def _process_special_configs(self):
        """处理特殊配置项"""
        if 'chrome' in self._config:
            if 'user_data_dir' in self._config['chrome']:
                self._config['chrome']['user_data_dir'] = os.path.join(
                    os.getcwd(),
                    self._config['chrome']['user_data_dir']
                )

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    @property
    def chrome(self) -> Dict:
        """获取 Chrome 相关配置"""
        return self._config.get('chrome', {})

    @property
    def llm(self) -> Dict:
        """获取 LLM 相关配置"""
        return self._config.get('llm', {})

config = ConfigManager() 