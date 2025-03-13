"""日志模块

该模块提供了统一的日志配置和管理功能，支持文件日志和控制台日志，
以及日志轮转、级别控制和格式化等功能。

作者: Re-Centris团队
版本: 1.0.0
许可证: MIT
"""

import os
import sys
import logging
import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, Union


def setup_logger(
    name: str = "re-centris",
    log_file: Optional[str] = None,
    log_level: Union[int, str] = logging.INFO,
    max_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console: bool = True,
    format_str: Optional[str] = None
) -> logging.Logger:
    """设置日志记录器
    
    Args:
        name: 日志记录器名称
        log_file: 日志文件路径，如果为None则不记录到文件
        log_level: 日志级别，可以是整数或字符串
        max_size: 日志文件最大大小(字节)
        backup_count: 日志文件备份数量
        console: 是否输出到控制台
        format_str: 日志格式字符串，如果为None则使用默认格式
    
    Returns:
        配置好的日志记录器
    """
    # 转换日志级别
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # 清除现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 设置日志格式
    if format_str is None:
        format_str = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    formatter = logging.Formatter(format_str)
    
    # 添加文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 添加控制台处理器
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def get_module_logger(module_name: str) -> logging.Logger:
    """获取模块日志记录器
    
    Args:
        module_name: 模块名称
    
    Returns:
        模块日志记录器
    """
    return logging.getLogger(f"re-centris.{module_name}")


class LoggerAdapter(logging.LoggerAdapter):
    """日志适配器，用于添加上下文信息"""
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        """初始化日志适配器
        
        Args:
            logger: 日志记录器
            extra: 额外上下文信息
        """
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """处理日志消息，添加上下文信息
        
        Args:
            msg: 日志消息
            kwargs: 关键字参数
        
        Returns:
            处理后的消息和关键字参数
        """
        context_str = " ".join(f"[{k}={v}]" for k, v in self.extra.items())
        if context_str:
            msg = f"{context_str} {msg}"
        return msg, kwargs


def create_context_logger(
    logger: logging.Logger,
    context: Dict[str, Any]
) -> LoggerAdapter:
    """创建带有上下文的日志记录器
    
    Args:
        logger: 基础日志记录器
        context: 上下文信息
    
    Returns:
        带有上下文的日志适配器
    """
    return LoggerAdapter(logger, context) 