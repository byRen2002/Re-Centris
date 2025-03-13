"""内存优化器模块

该模块提供了内存使用优化功能，包括内存使用监控、分批处理数据、
自动垃圾回收和内存限制等功能。

作者: Re-Centris团队
版本: 1.0.0
许可证: MIT
"""

import os
import gc
import sys
import time
import logging
import threading
from typing import List, Any, Callable, Generator, TypeVar, Generic, Optional

# 获取模块日志记录器
logger = logging.getLogger("re-centris.memory_optimizer")

# 定义泛型类型
T = TypeVar('T')
R = TypeVar('R')


class MemoryOptimizer:
    """内存优化器，提供内存使用优化功能"""
    
    def __init__(
        self,
        target_memory_usage: float = 0.8,
        initial_batch_size: int = 1000,
        min_batch_size: int = 100,
        max_batch_size: int = 10000,
        check_interval: int = 10
    ):
        """初始化内存优化器
        
        Args:
            target_memory_usage: 目标内存使用率(0.0-1.0)
            initial_batch_size: 初始批处理大小
            min_batch_size: 最小批处理大小
            max_batch_size: 最大批处理大小
            check_interval: 内存检查间隔(秒)
        """
        self.target_memory_usage = target_memory_usage
        self.current_batch_size = initial_batch_size
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.check_interval = check_interval
        self._lock = threading.Lock()
        self._last_check_time = 0
        self._last_gc_time = 0
    
    def get_memory_usage(self) -> float:
        """获取当前内存使用率
        
        Returns:
            内存使用率(0.0-1.0)
        """
        try:
            import psutil
            process = psutil.Process()
            return process.memory_percent() / 100
        except ImportError:
            # 如果没有psutil，使用简单的内存使用估计
            if hasattr(sys, 'getsizeof'):
                # 获取Python解释器使用的内存
                memory_used = 0
                for obj in gc.get_objects():
                    try:
                        memory_used += sys.getsizeof(obj)
                    except:
                        pass
                # 估计总内存
                try:
                    with open('/proc/meminfo', 'r') as f:
                        for line in f:
                            if 'MemTotal' in line:
                                total_memory = int(line.split()[1]) * 1024
                                return memory_used / total_memory
                except:
                    pass
            return 0.5  # 默认返回中等内存使用率
    
    def should_gc(self) -> bool:
        """判断是否需要执行垃圾回收
        
        Returns:
            是否需要执行垃圾回收
        """
        current_time = time.time()
        
        # 至少间隔10秒检查一次
        if current_time - self._last_check_time < self.check_interval:
            return False
        
        self._last_check_time = current_time
        
        # 检查内存使用率
        memory_usage = self.get_memory_usage()
        
        # 如果内存使用率超过目标，执行垃圾回收
        if memory_usage > self.target_memory_usage:
            # 至少间隔30秒执行一次垃圾回收
            if current_time - self._last_gc_time >= 30:
                self._last_gc_time = current_time
                return True
        
        return False
    
    def optimize(self) -> None:
        """执行内存优化"""
        if self.should_gc():
            logger.debug("执行垃圾回收")
            gc.collect()
    
    def adjust_batch_size(self) -> int:
        """根据内存使用情况调整批处理大小
        
        Returns:
            调整后的批处理大小
        """
        with self._lock:
            memory_usage = self.get_memory_usage()
            
            if memory_usage > self.target_memory_usage:
                # 内存使用率过高，减小批处理大小
                self.current_batch_size = max(
                    self.min_batch_size,
                    int(self.current_batch_size * 0.8)
                )
            elif memory_usage < self.target_memory_usage * 0.7:
                # 内存使用率较低，增加批处理大小
                self.current_batch_size = min(
                    self.max_batch_size,
                    int(self.current_batch_size * 1.2)
                )
            
            return self.current_batch_size
    
    def batch_items(self, items: List[T]) -> Generator[List[T], None, None]:
        """分批处理数据
        
        Args:
            items: 数据项列表
        
        Yields:
            批次数据
        """
        for i in range(0, len(items), self.current_batch_size):
            batch = items[i:i + self.current_batch_size]
            yield batch
            
            # 优化内存
            self.optimize()
            
            # 调整批处理大小
            self.adjust_batch_size()
    
    def process_in_batches(
        self,
        items: List[T],
        processor: Callable[[List[T]], List[R]]
    ) -> List[R]:
        """分批处理数据并合并结果
        
        Args:
            items: 数据项列表
            processor: 处理函数，接受一个批次数据，返回处理结果
        
        Returns:
            所有批次的处理结果合并
        """
        results = []
        
        for batch in self.batch_items(items):
            batch_results = processor(batch)
            results.extend(batch_results)
        
        return results
    
    def monitor_memory(
        self,
        interval: int = 60,
        callback: Optional[Callable[[float], None]] = None
    ) -> threading.Thread:
        """启动内存监控线程
        
        Args:
            interval: 监控间隔(秒)
            callback: 回调函数，接受当前内存使用率
        
        Returns:
            监控线程
        """
        def _monitor():
            while True:
                try:
                    memory_usage = self.get_memory_usage()
                    
                    if callback:
                        callback(memory_usage)
                    else:
                        logger.info(f"当前内存使用率: {memory_usage:.2%}")
                    
                    # 如果内存使用率过高，执行垃圾回收
                    if memory_usage > self.target_memory_usage:
                        logger.warning(f"内存使用率过高: {memory_usage:.2%}")
                        gc.collect()
                    
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"内存监控异常: {e}")
                    time.sleep(interval)
        
        thread = threading.Thread(target=_monitor, daemon=True)
        thread.start()
        return thread


class BatchProcessor(Generic[T, R]):
    """批处理器，用于高效处理大量数据"""
    
    def __init__(
        self,
        processor: Callable[[T], R],
        batch_size: int = 1000,
        memory_optimizer: Optional[MemoryOptimizer] = None
    ):
        """初始化批处理器
        
        Args:
            processor: 处理函数，接受一个数据项，返回处理结果
            batch_size: 批处理大小
            memory_optimizer: 内存优化器，如果为None则创建新的
        """
        self.processor = processor
        self.batch_size = batch_size
        self.memory_optimizer = memory_optimizer or MemoryOptimizer()
    
    def process(self, items: List[T]) -> List[R]:
        """处理数据项列表
        
        Args:
            items: 数据项列表
        
        Returns:
            处理结果列表
        """
        results = []
        
        for batch in self.memory_optimizer.batch_items(items):
            batch_results = [self.processor(item) for item in batch]
            results.extend(batch_results)
            
            # 优化内存
            self.memory_optimizer.optimize()
        
        return results
    
    def process_generator(self, items_generator: Generator[T, None, None]) -> Generator[R, None, None]:
        """处理数据项生成器
        
        Args:
            items_generator: 数据项生成器
        
        Yields:
            处理结果
        """
        batch = []
        
        for item in items_generator:
            batch.append(item)
            
            if len(batch) >= self.batch_size:
                for result in self._process_batch(batch):
                    yield result
                batch = []
                
                # 优化内存
                self.memory_optimizer.optimize()
        
        # 处理剩余项
        if batch:
            for result in self._process_batch(batch):
                yield result
    
    def _process_batch(self, batch: List[T]) -> List[R]:
        """处理单个批次
        
        Args:
            batch: 批次数据
        
        Returns:
            处理结果
        """
        return [self.processor(item) for item in batch] 