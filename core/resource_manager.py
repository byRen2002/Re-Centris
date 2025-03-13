"""资源管理器模块

该模块提供了统一的资源管理功能，包括文件句柄、进程池、线程池等资源的管理，
确保资源在使用后被正确释放，避免资源泄漏。

作者: Re-Centris团队
版本: 1.0.0
许可证: MIT
"""

import os
import logging
import threading
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Dict, Any, Optional, Tuple, Union, Set

# 获取模块日志记录器
logger = logging.getLogger("re-centris.resource_manager")


class ResourceManager:
    """资源管理器，负责管理和释放各种资源"""
    
    def __init__(self):
        """初始化资源管理器"""
        self._file_handles: Dict[Tuple[str, str], Any] = {}
        self._process_pools: Dict[str, ProcessPoolExecutor] = {}
        self._thread_pools: Dict[str, ThreadPoolExecutor] = {}
        self._resources: Dict[str, Any] = {}
        self._lock = threading.Lock()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出时释放所有资源"""
        self.close_all()
    
    def get_file_handle(self, path: str, mode: str = 'r', encoding: Optional[str] = None) -> Any:
        """获取文件句柄
        
        Args:
            path: 文件路径
            mode: 打开模式
            encoding: 文件编码
        
        Returns:
            文件句柄
        """
        with self._lock:
            key = (path, mode)
            if key not in self._file_handles:
                try:
                    if encoding:
                        self._file_handles[key] = open(path, mode, encoding=encoding)
                    else:
                        self._file_handles[key] = open(path, mode)
                except Exception as e:
                    logger.error(f"打开文件失败 {path}: {e}")
                    raise
            return self._file_handles[key]
    
    def close_file(self, path: str, mode: str = 'r') -> None:
        """关闭文件句柄
        
        Args:
            path: 文件路径
            mode: 打开模式
        """
        with self._lock:
            key = (path, mode)
            if key in self._file_handles:
                try:
                    self._file_handles[key].close()
                except Exception as e:
                    logger.warning(f"关闭文件失败 {path}: {e}")
                finally:
                    del self._file_handles[key]
    
    def get_process_pool(self, name: str = "default", max_workers: Optional[int] = None) -> ProcessPoolExecutor:
        """获取进程池
        
        Args:
            name: 进程池名称
            max_workers: 最大工作进程数，如果为None则使用CPU核心数
        
        Returns:
            进程池
        """
        with self._lock:
            if name not in self._process_pools:
                if max_workers is None:
                    max_workers = multiprocessing.cpu_count()
                self._process_pools[name] = ProcessPoolExecutor(max_workers=max_workers)
            return self._process_pools[name]
    
    def get_thread_pool(self, name: str = "default", max_workers: Optional[int] = None) -> ThreadPoolExecutor:
        """获取线程池
        
        Args:
            name: 线程池名称
            max_workers: 最大工作线程数，如果为None则使用CPU核心数的5倍
        
        Returns:
            线程池
        """
        with self._lock:
            if name not in self._thread_pools:
                if max_workers is None:
                    max_workers = multiprocessing.cpu_count() * 5
                self._thread_pools[name] = ThreadPoolExecutor(max_workers=max_workers)
            return self._thread_pools[name]
    
    def register_resource(self, name: str, resource: Any, close_method: str = "close") -> None:
        """注册自定义资源
        
        Args:
            name: 资源名称
            resource: 资源对象
            close_method: 关闭资源的方法名
        """
        with self._lock:
            if name in self._resources:
                logger.warning(f"资源 {name} 已存在，将被覆盖")
            
            self._resources[name] = (resource, close_method)
    
    def get_resource(self, name: str) -> Optional[Any]:
        """获取自定义资源
        
        Args:
            name: 资源名称
        
        Returns:
            资源对象，如果不存在则返回None
        """
        with self._lock:
            if name in self._resources:
                return self._resources[name][0]
            return None
    
    def close_resource(self, name: str) -> bool:
        """关闭自定义资源
        
        Args:
            name: 资源名称
        
        Returns:
            是否成功关闭
        """
        with self._lock:
            if name in self._resources:
                resource, close_method = self._resources[name]
                try:
                    getattr(resource, close_method)()
                    del self._resources[name]
                    return True
                except Exception as e:
                    logger.warning(f"关闭资源 {name} 失败: {e}")
            return False
    
    def close_all(self) -> None:
        """关闭所有资源"""
        with self._lock:
            # 关闭文件句柄
            for key, handle in list(self._file_handles.items()):
                try:
                    handle.close()
                except Exception as e:
                    logger.warning(f"关闭文件失败 {key[0]}: {e}")
            self._file_handles.clear()
            
            # 关闭进程池
            for name, pool in list(self._process_pools.items()):
                try:
                    pool.shutdown()
                except Exception as e:
                    logger.warning(f"关闭进程池 {name} 失败: {e}")
            self._process_pools.clear()
            
            # 关闭线程池
            for name, pool in list(self._thread_pools.items()):
                try:
                    pool.shutdown()
                except Exception as e:
                    logger.warning(f"关闭线程池 {name} 失败: {e}")
            self._thread_pools.clear()
            
            # 关闭自定义资源
            for name, (resource, close_method) in list(self._resources.items()):
                try:
                    getattr(resource, close_method)()
                except Exception as e:
                    logger.warning(f"关闭资源 {name} 失败: {e}")
            self._resources.clear()
    
    def __del__(self):
        """析构时关闭所有资源"""
        self.close_all()


class SafeFileHandler:
    """安全的文件处理器，自动处理文件打开和关闭"""
    
    def __init__(self, path: str, mode: str = 'r', encoding: Optional[str] = None):
        """初始化安全文件处理器
        
        Args:
            path: 文件路径
            mode: 打开模式
            encoding: 文件编码
        """
        self.path = path
        self.mode = mode
        self.encoding = encoding
        self.file = None
    
    def __enter__(self):
        """上下文管理器入口"""
        try:
            if self.encoding:
                self.file = open(self.path, self.mode, encoding=self.encoding)
            else:
                self.file = open(self.path, self.mode)
            return self.file
        except Exception as e:
            logger.error(f"打开文件失败 {self.path}: {e}")
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出时关闭文件"""
        if self.file:
            try:
                self.file.close()
            except Exception as e:
                logger.warning(f"关闭文件失败 {self.path}: {e}")


def safe_open(path: str, mode: str = 'r', encoding: Optional[str] = None) -> SafeFileHandler:
    """安全打开文件
    
    Args:
        path: 文件路径
        mode: 打开模式
        encoding: 文件编码
    
    Returns:
        安全文件处理器
    """
    return SafeFileHandler(path, mode, encoding) 