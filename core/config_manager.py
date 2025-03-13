"""配置管理模块

该模块提供了统一的配置管理功能，支持从配置文件、环境变量和命令行参数加载配置。
配置项包括路径设置、性能参数、日志设置等。

作者: Re-Centris团队
版本: 1.0.0
许可证: MIT
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union


class ConfigManager:
    """配置管理类，负责加载、验证和提供配置信息"""
    
    def __init__(self, config_file: Optional[str] = None):
        """初始化配置管理器
        
        Args:
            config_file: 配置文件路径，如果为None，则尝试从默认位置加载
        """
        self.config: Dict[str, Any] = {}
        self.config_file = config_file
        self._load_default_config()
        
        if config_file:
            self.load_config(config_file)
        else:
            # 尝试从默认位置加载配置
            default_locations = [
                "./config.yaml",
                "./config.json",
                os.path.expanduser("~/.re-centris/config.yaml"),
                os.path.expanduser("~/.re-centris/config.json"),
                "/etc/re-centris/config.yaml",
                "/etc/re-centris/config.json"
            ]
            
            for location in default_locations:
                if os.path.exists(location):
                    self.load_config(location)
                    break
        
        # 从环境变量加载配置
        self._load_from_env()
    
    def _load_default_config(self) -> None:
        """加载默认配置"""
        # 获取当前工作目录
        current_dir = os.getcwd()
        
        self.config = {
            "paths": {
                "current_path": current_dir,
                "repo_path": os.path.join(current_dir, "repos"),
                "tag_date_path": os.path.join(current_dir, "osscollector", "repo_date"),
                "result_path": os.path.join(current_dir, "osscollector", "repo_functions"),
                "log_path": os.path.join(current_dir, "logs"),
                "ver_idx_path": os.path.join(current_dir, "preprocessor", "verIDX"),
                "initial_db_path": os.path.join(current_dir, "preprocessor", "initialSigs"),
                "final_db_path": os.path.join(current_dir, "preprocessor", "componentDB"),
                "meta_path": os.path.join(current_dir, "preprocessor", "metaInfos"),
                "weight_path": os.path.join(current_dir, "preprocessor", "metaInfos", "weights"),
                "func_date_path": os.path.join(current_dir, "preprocessor", "funcDate"),
                "cache_path": os.path.join(current_dir, "cache")
            },
            "performance": {
                "max_workers": os.cpu_count(),
                "cache_size": 1000,
                "cache_expire": 3600,  # 1小时
                "memory_limit": 0.9,  # 90%
                "timeout": 30,  # 30秒
                "batch_size": 1000
            },
            "logging": {
                "level": "INFO",
                "max_size": 10 * 1024 * 1024,  # 10MB
                "backup_count": 5
            },
            "analysis": {
                "theta": 0.1,  # 相似度阈值
                "tlsh_threshold": 30  # TLSH差异阈值
            },
            "external_tools": {
                "ctags_path": "ctags"  # 默认从PATH中查找
            }
        }
    
    def load_config(self, config_file: str) -> None:
        """从文件加载配置
        
        Args:
            config_file: 配置文件路径
        
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"配置文件不存在: {config_file}")
        
        try:
            ext = os.path.splitext(config_file)[1].lower()
            
            if ext == '.json':
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
            elif ext in ['.yaml', '.yml']:
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f)
            else:
                raise ValueError(f"不支持的配置文件格式: {ext}")
            
            # 递归更新配置
            self._update_config(self.config, file_config)
            
            logging.info(f"已从 {config_file} 加载配置")
            
        except Exception as e:
            logging.error(f"加载配置文件失败: {e}")
            raise
    
    def _update_config(self, target: Dict, source: Dict) -> None:
        """递归更新配置字典
        
        Args:
            target: 目标配置字典
            source: 源配置字典
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._update_config(target[key], value)
            else:
                target[key] = value
    
    def _load_from_env(self) -> None:
        """从环境变量加载配置
        
        环境变量格式: RECENTRIS_SECTION_KEY=value
        例如: RECENTRIS_PATHS_REPO_PATH=/path/to/repos
        """
        prefix = "RECENTRIS_"
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                parts = key[len(prefix):].lower().split('_')
                
                if len(parts) >= 2:
                    section = parts[0]
                    subkey = '_'.join(parts[1:])
                    
                    if section in self.config:
                        if subkey in self.config[section]:
                            # 尝试转换值类型
                            orig_value = self.config[section][subkey]
                            if isinstance(orig_value, bool):
                                self.config[section][subkey] = value.lower() in ['true', '1', 'yes']
                            elif isinstance(orig_value, int):
                                self.config[section][subkey] = int(value)
                            elif isinstance(orig_value, float):
                                self.config[section][subkey] = float(value)
                            else:
                                self.config[section][subkey] = value
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            section: 配置部分
            key: 配置键
            default: 默认值，如果配置不存在则返回该值
        
        Returns:
            配置值
        """
        if section in self.config and key in self.config[section]:
            return self.config[section][key]
        return default
    
    def set(self, section: str, key: str, value: Any) -> None:
        """设置配置值
        
        Args:
            section: 配置部分
            key: 配置键
            value: 配置值
        """
        if section not in self.config:
            self.config[section] = {}
        
        self.config[section][key] = value
    
    def get_path(self, key: str) -> str:
        """获取路径配置
        
        Args:
            key: 路径键名
        
        Returns:
            路径字符串
        """
        path = self.get("paths", key)
        if path:
            # 确保目录存在
            os.makedirs(path, exist_ok=True)
        return path
    
    def save_config(self, config_file: Optional[str] = None) -> None:
        """保存配置到文件
        
        Args:
            config_file: 配置文件路径，如果为None则使用初始化时的配置文件
        """
        if config_file is None:
            config_file = self.config_file
        
        if not config_file:
            raise ValueError("未指定配置文件路径")
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(config_file)), exist_ok=True)
            
            ext = os.path.splitext(config_file)[1].lower()
            
            if ext == '.json':
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
            elif ext in ['.yaml', '.yml']:
                with open(config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            else:
                raise ValueError(f"不支持的配置文件格式: {ext}")
            
            logging.info(f"配置已保存到 {config_file}")
            
        except Exception as e:
            logging.error(f"保存配置文件失败: {e}")
            raise
    
    def create_required_directories(self) -> None:
        """创建所有必需的目录"""
        for key, path in self.config["paths"].items():
            if isinstance(path, str) and not os.path.exists(path):
                try:
                    os.makedirs(path)
                    logging.info(f"创建目录: {path}")
                except Exception as e:
                    logging.error(f"创建目录 {path} 失败: {e}") 