import os
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import List, Callable, Any, Dict, Optional, Union
from functools import partial

logger = logging.getLogger(__name__)

class ParallelManager:
    """并行处理管理器类"""
    
    def __init__(self, max_workers: Optional[int] = None):
        """初始化并行处理管理器
        
        Args:
            max_workers: 最大工作进程数，默认为CPU核心数
        """
        self.max_workers = max_workers or multiprocessing.cpu_count()
        self._process_pools: Dict[str, ProcessPoolExecutor] = {}
        self._thread_pools: Dict[str, ThreadPoolExecutor] = {}
        
    def process_items(self,
                     items: List[Any],
                     process_func: Callable,
                     pool_name: str = "default",
                     chunk_size: Optional[int] = None,
                     use_threads: bool = False,
                     **kwargs) -> List[Any]:
        """并行处理项目列表
        
        Args:
            items: 待处理项目列表
            process_func: 处理函数
            pool_name: 进程池名称
            chunk_size: 分块大小
            use_threads: 是否使用线程池
            **kwargs: 传递给处理函数的额外参数
            
        Returns:
            处理结果列表
        """
        if not items:
            return []
            
        # 确定分块大小
        if chunk_size is None:
            chunk_size = max(1, len(items) // (self.max_workers * 4))
            
        # 准备任务
        chunked_items = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
        partial_func = partial(process_func, **kwargs)
        
        # 选择执行器
        executor_cls = ThreadPoolExecutor if use_threads else ProcessPoolExecutor
        executor_dict = self._thread_pools if use_threads else self._process_pools
        
        # 获取或创建执行器
        if pool_name not in executor_dict:
            executor_dict[pool_name] = executor_cls(max_workers=self.max_workers)
        executor = executor_dict[pool_name]
        
        results = []
        try:
            # 提交任务
            futures = [
                executor.submit(partial_func, chunk)
                for chunk in chunked_items
            ]
            
            # 收集结果
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if isinstance(result, list):
                        results.extend(result)
                    else:
                        results.append(result)
                except Exception as e:
                    logger.error(f"处理任务失败: {str(e)}")
                    
        except Exception as e:
            logger.error(f"并行处理失败: {str(e)}")
            
        return results
        
    def process_items_with_progress(self,
                                  items: List[Any],
                                  process_func: Callable,
                                  progress_callback: Callable[[int, int], None],
                                  pool_name: str = "default",
                                  chunk_size: Optional[int] = None,
                                  use_threads: bool = False,
                                  **kwargs) -> List[Any]:
        """带进度回调的并行处理
        
        Args:
            items: 待处理项目列表
            process_func: 处理函数
            progress_callback: 进度回调函数
            pool_name: 进程池名称
            chunk_size: 分块大小
            use_threads: 是否使用线程池
            **kwargs: 传递给处理函数的额外参数
            
        Returns:
            处理结果列表
        """
        total_items = len(items)
        processed_items = 0
        
        def update_progress(result):
            nonlocal processed_items
            processed_items += len(result) if isinstance(result, list) else 1
            progress_callback(processed_items, total_items)
            return result
            
        results = self.process_items(
            items=items,
            process_func=process_func,
            pool_name=pool_name,
            chunk_size=chunk_size,
            use_threads=use_threads,
            **kwargs
        )
        
        for result in results:
            update_progress(result)
            
        return results
        
    def close_pool(self, pool_name: str, use_threads: bool = False):
        """关闭指定的进程池或线程池
        
        Args:
            pool_name: 池名称
            use_threads: 是否为线程池
        """
        pool_dict = self._thread_pools if use_threads else self._process_pools
        if pool_name in pool_dict:
            pool_dict[pool_name].shutdown()
            del pool_dict[pool_name]
            
    def close_all(self):
        """关闭所有进程池和线程池"""
        for pool in list(self._process_pools.values()):
            pool.shutdown()
        self._process_pools.clear()
        
        for pool in list(self._thread_pools.values()):
            pool.shutdown()
        self._thread_pools.clear() 