"""缓存模块

该模块提供了统一的缓存管理功能，支持内存缓存和持久化缓存，
以及LRU淘汰策略、过期时间和大小限制等功能。

作者: Re-Centris团队
版本: 1.0.0
许可证: MIT
"""

import os
import time
import pickle
import threading
import logging
from typing import Dict, Any, Optional, Tuple, List, Callable
from functools import wraps

# 获取模块日志记录器
logger = logging.getLogger("re-centris.cache")


class Cache:
    """通用缓存类，支持LRU淘汰策略、过期时间和大小限制"""
    
    def __init__(
        self,
        max_size: int = 1000,
        expire_time: int = 3600,
        persistent: bool = False,
        cache_dir: Optional[str] = None
    ):
        """初始化缓存
        
        Args:
            max_size: 缓存最大条目数
            expire_time: 缓存过期时间(秒)
            persistent: 是否持久化缓存
            cache_dir: 缓存目录，仅在persistent=True时有效
        """
        self.max_size = max_size
        self.expire_time = expire_time
        self.persistent = persistent
        self.cache_dir = cache_dir
        
        if persistent and not cache_dir:
            raise ValueError("持久化缓存必须指定缓存目录")
        
        if persistent and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        
        self._cache: Dict[str, Any] = {}
        self._access_times: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值
        
        Args:
            key: 缓存键
        
        Returns:
            缓存值，如果不存在或已过期则返回None
        """
        with self._lock:
            # 检查内存缓存
            if key in self._cache:
                access_time = self._access_times[key]
                if time.time() - access_time <= self.expire_time:
                    # 更新访问时间
                    self._access_times[key] = time.time()
                    return self._cache[key]
                else:
                    # 缓存已过期，删除
                    del self._cache[key]
                    del self._access_times[key]
            
            # 如果启用了持久化缓存，尝试从文件加载
            if self.persistent:
                cache_file = self._get_cache_file(key)
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, 'rb') as f:
                            data = pickle.load(f)
                            timestamp, value = data
                            
                            if time.time() - timestamp <= self.expire_time:
                                # 加载到内存缓存
                                self._cache[key] = value
                                self._access_times[key] = time.time()
                                return value
                            else:
                                # 缓存已过期，删除文件
                                os.remove(cache_file)
                    except Exception as e:
                        logger.warning(f"从持久化缓存加载失败: {e}")
            
            return None
    
    def put(self, key: str, value: Any) -> None:
        """存入缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        with self._lock:
            # 如果键已存在，更新访问时间
            if key in self._cache:
                self._access_times[key] = time.time()
                self._cache[key] = value
            else:
                # 如果缓存已满，淘汰最久未使用的项
                if len(self._cache) >= self.max_size:
                    self._evict_lru()
                
                # 添加新项
                self._cache[key] = value
                self._access_times[key] = time.time()
            
            # 如果启用了持久化缓存，保存到文件
            if self.persistent:
                self._save_to_file(key, value)
    
    def _evict_lru(self) -> None:
        """淘汰最久未使用的缓存项"""
        if not self._access_times:
            return
        
        # 找出访问时间最早的键
        oldest_key = min(self._access_times.items(), key=lambda x: x[1])[0]
        
        # 从内存缓存中删除
        del self._cache[oldest_key]
        del self._access_times[oldest_key]
        
        # 如果启用了持久化缓存，删除文件
        if self.persistent:
            cache_file = self._get_cache_file(oldest_key)
            if os.path.exists(cache_file):
                try:
                    os.remove(cache_file)
                except Exception as e:
                    logger.warning(f"删除缓存文件失败: {e}")
    
    def _get_cache_file(self, key: str) -> str:
        """获取缓存文件路径
        
        Args:
            key: 缓存键
        
        Returns:
            缓存文件路径
        """
        # 使用MD5哈希作为文件名，避免文件名无效字符
        import hashlib
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{key_hash}.cache")
    
    def _save_to_file(self, key: str, value: Any) -> None:
        """保存缓存项到文件
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        if not self.persistent:
            return
        
        cache_file = self._get_cache_file(key)
        try:
            with open(cache_file, 'wb') as f:
                # 保存时间戳和值
                data = (time.time(), value)
                pickle.dump(data, f)
        except Exception as e:
            logger.warning(f"保存缓存到文件失败: {e}")
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            
            # 如果启用了持久化缓存，删除所有缓存文件
            if self.persistent and os.path.exists(self.cache_dir):
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith(".cache"):
                        try:
                            os.remove(os.path.join(self.cache_dir, filename))
                        except Exception as e:
                            logger.warning(f"删除缓存文件失败: {e}")
    
    def remove(self, key: str) -> bool:
        """删除缓存项
        
        Args:
            key: 缓存键
        
        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                del self._access_times[key]
                
                # 如果启用了持久化缓存，删除文件
                if self.persistent:
                    cache_file = self._get_cache_file(key)
                    if os.path.exists(cache_file):
                        try:
                            os.remove(cache_file)
                        except Exception as e:
                            logger.warning(f"删除缓存文件失败: {e}")
                
                return True
            return False
    
    def keys(self) -> List[str]:
        """获取所有缓存键
        
        Returns:
            缓存键列表
        """
        with self._lock:
            return list(self._cache.keys())
    
    def size(self) -> int:
        """获取缓存大小
        
        Returns:
            缓存条目数
        """
        with self._lock:
            return len(self._cache)
    
    def has_key(self, key: str) -> bool:
        """检查缓存键是否存在
        
        Args:
            key: 缓存键
        
        Returns:
            缓存键是否存在
        """
        with self._lock:
            return key in self._cache


def cached(cache: Cache, key_func: Optional[Callable] = None):
    """函数结果缓存装饰器
    
    Args:
        cache: 缓存对象
        key_func: 缓存键生成函数，如果为None则使用函数名和参数生成
    
    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # 默认使用函数名和参数生成键
                key = f"{func.__module__}.{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # 尝试从缓存获取
            result = cache.get(key)
            if result is not None:
                return result
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            cache.put(key, result)
            
            return result
        return wrapper
    return decorator 