"""性能监控模块

该模块提供了性能监控和统计功能，包括处理速度、资源使用和进度统计等，
支持实时监控和性能报告生成。

作者: Re-Centris团队
版本: 1.0.0
许可证: MIT
"""

import os
import time
import logging
import threading
import datetime
from typing import Dict, Any, Optional, Callable, List, Tuple
from functools import wraps

# 获取模块日志记录器
logger = logging.getLogger("re-centris.performance_monitor")


class PerformanceMonitor:
    """性能监控器，用于监控和记录程序运行性能"""
    
    def __init__(
        self,
        name: str = "default",
        log_interval: int = 60,
        detailed: bool = False
    ):
        """初始化性能监控器
        
        Args:
            name: 监控器名称
            log_interval: 日志记录间隔(秒)
            detailed: 是否记录详细信息
        """
        self.name = name
        self.log_interval = log_interval
        self.detailed = detailed
        
        self.start_time = time.time()
        self.last_log_time = self.start_time
        self.processed_items = 0
        self.processing_times: List[float] = []
        self.item_sizes: List[int] = []
        self._lock = threading.Lock()
        
        # 阶段性能统计
        self.stages: Dict[str, Dict[str, Any]] = {}
        
        # 是否正在运行
        self.running = True
        
        # 启动监控线程
        if detailed:
            self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
            self._monitor_thread.start()
    
    def update(self, items: int = 1, processing_time: Optional[float] = None, item_size: Optional[int] = None) -> None:
        """更新处理项数和性能指标
        
        Args:
            items: 处理项数
            processing_time: 处理时间(秒)
            item_size: 项大小(字节)
        """
        with self._lock:
            self.processed_items += items
            
            if processing_time is not None:
                self.processing_times.append(processing_time)
            
            if item_size is not None:
                self.item_sizes.append(item_size)
            
            current_time = time.time()
            
            # 每隔指定时间记录一次性能指标
            if current_time - self.last_log_time >= self.log_interval:
                self._log_performance()
                self.last_log_time = current_time
    
    def _log_performance(self) -> None:
        """记录性能指标"""
        elapsed = time.time() - self.start_time
        
        if elapsed <= 0:
            return
        
        rate = self.processed_items / elapsed
        
        logger.info(f"性能统计 [{self.name}]:")
        logger.info(f"- 总处理项数: {self.processed_items}")
        logger.info(f"- 运行时间: {self._format_time(elapsed)}")
        logger.info(f"- 处理速率: {rate:.2f}项/秒")
        
        if self.processing_times:
            avg_time = sum(self.processing_times) / len(self.processing_times)
            logger.info(f"- 平均处理时间: {avg_time:.6f}秒/项")
        
        if self.item_sizes:
            avg_size = sum(self.item_sizes) / len(self.item_sizes)
            logger.info(f"- 平均项大小: {self._format_size(avg_size)}")
    
    def start_stage(self, stage_name: str) -> None:
        """开始一个处理阶段
        
        Args:
            stage_name: 阶段名称
        """
        with self._lock:
            self.stages[stage_name] = {
                "start_time": time.time(),
                "end_time": None,
                "processed_items": 0,
                "processing_times": [],
                "item_sizes": []
            }
    
    def end_stage(self, stage_name: str) -> None:
        """结束一个处理阶段
        
        Args:
            stage_name: 阶段名称
        """
        with self._lock:
            if stage_name in self.stages:
                self.stages[stage_name]["end_time"] = time.time()
                
                # 记录阶段性能
                stage = self.stages[stage_name]
                elapsed = stage["end_time"] - stage["start_time"]
                
                if elapsed <= 0:
                    return
                
                rate = stage["processed_items"] / elapsed
                
                logger.info(f"阶段性能 [{self.name}] - {stage_name}:")
                logger.info(f"- 总处理项数: {stage['processed_items']}")
                logger.info(f"- 运行时间: {self._format_time(elapsed)}")
                logger.info(f"- 处理速率: {rate:.2f}项/秒")
                
                if stage["processing_times"]:
                    avg_time = sum(stage["processing_times"]) / len(stage["processing_times"])
                    logger.info(f"- 平均处理时间: {avg_time:.6f}秒/项")
                
                if stage["item_sizes"]:
                    avg_size = sum(stage["item_sizes"]) / len(stage["item_sizes"])
                    logger.info(f"- 平均项大小: {self._format_size(avg_size)}")
    
    def update_stage(
        self,
        stage_name: str,
        items: int = 1,
        processing_time: Optional[float] = None,
        item_size: Optional[int] = None
    ) -> None:
        """更新阶段处理项数和性能指标
        
        Args:
            stage_name: 阶段名称
            items: 处理项数
            processing_time: 处理时间(秒)
            item_size: 项大小(字节)
        """
        with self._lock:
            if stage_name in self.stages:
                self.stages[stage_name]["processed_items"] += items
                
                if processing_time is not None:
                    self.stages[stage_name]["processing_times"].append(processing_time)
                
                if item_size is not None:
                    self.stages[stage_name]["item_sizes"].append(item_size)
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告
        
        Returns:
            性能报告字典
        """
        with self._lock:
            elapsed = time.time() - self.start_time
            
            report = {
                "name": self.name,
                "start_time": datetime.datetime.fromtimestamp(self.start_time).isoformat(),
                "elapsed_time": elapsed,
                "processed_items": self.processed_items,
                "processing_rate": self.processed_items / elapsed if elapsed > 0 else 0,
                "stages": {}
            }
            
            if self.processing_times:
                report["avg_processing_time"] = sum(self.processing_times) / len(self.processing_times)
                report["min_processing_time"] = min(self.processing_times)
                report["max_processing_time"] = max(self.processing_times)
            
            if self.item_sizes:
                report["avg_item_size"] = sum(self.item_sizes) / len(self.item_sizes)
                report["min_item_size"] = min(self.item_sizes)
                report["max_item_size"] = max(self.item_sizes)
            
            # 添加阶段性能
            for stage_name, stage in self.stages.items():
                stage_elapsed = (stage["end_time"] or time.time()) - stage["start_time"]
                
                stage_report = {
                    "start_time": datetime.datetime.fromtimestamp(stage["start_time"]).isoformat(),
                    "elapsed_time": stage_elapsed,
                    "processed_items": stage["processed_items"],
                    "processing_rate": stage["processed_items"] / stage_elapsed if stage_elapsed > 0 else 0
                }
                
                if stage["processing_times"]:
                    stage_report["avg_processing_time"] = sum(stage["processing_times"]) / len(stage["processing_times"])
                    stage_report["min_processing_time"] = min(stage["processing_times"])
                    stage_report["max_processing_time"] = max(stage["processing_times"])
                
                if stage["item_sizes"]:
                    stage_report["avg_item_size"] = sum(stage["item_sizes"]) / len(stage["item_sizes"])
                    stage_report["min_item_size"] = min(stage["item_sizes"])
                    stage_report["max_item_size"] = max(stage["item_sizes"])
                
                report["stages"][stage_name] = stage_report
            
            return report
    
    def save_report(self, file_path: str) -> None:
        """保存性能报告到文件
        
        Args:
            file_path: 文件路径
        """
        import json
        
        report = self.get_performance_report()
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
            
            logger.info(f"性能报告已保存到 {file_path}")
        except Exception as e:
            logger.error(f"保存性能报告失败: {e}")
    
    def _monitor(self) -> None:
        """监控线程函数"""
        try:
            import psutil
            process = psutil.Process()
            
            while self.running:
                try:
                    # 获取CPU和内存使用情况
                    cpu_percent = process.cpu_percent(interval=1)
                    memory_percent = process.memory_percent()
                    
                    logger.debug(f"资源使用 [{self.name}]:")
                    logger.debug(f"- CPU使用率: {cpu_percent:.1f}%")
                    logger.debug(f"- 内存使用率: {memory_percent:.1f}%")
                    
                    time.sleep(self.log_interval)
                except Exception as e:
                    logger.error(f"监控异常: {e}")
                    time.sleep(self.log_interval)
        except ImportError:
            logger.warning("未安装psutil，无法监控资源使用情况")
    
    def stop(self) -> None:
        """停止监控"""
        self.running = False
        self._log_performance()
    
    def __del__(self) -> None:
        """析构时停止监控"""
        self.stop()
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """格式化时间
        
        Args:
            seconds: 秒数
        
        Returns:
            格式化后的时间字符串
        """
        if seconds < 60:
            return f"{seconds:.2f}秒"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.2f}分钟"
        else:
            hours = seconds / 3600
            return f"{hours:.2f}小时"
    
    @staticmethod
    def _format_size(size_bytes: float) -> str:
        """格式化大小
        
        Args:
            size_bytes: 字节数
        
        Returns:
            格式化后的大小字符串
        """
        if size_bytes < 1024:
            return f"{size_bytes:.2f}B"
        elif size_bytes < 1024 * 1024:
            kb = size_bytes / 1024
            return f"{kb:.2f}KB"
        elif size_bytes < 1024 * 1024 * 1024:
            mb = size_bytes / (1024 * 1024)
            return f"{mb:.2f}MB"
        else:
            gb = size_bytes / (1024 * 1024 * 1024)
            return f"{gb:.2f}GB"


class ProgressBar:
    """进度条，用于显示处理进度"""
    
    def __init__(
        self,
        total: int,
        prefix: str = '',
        suffix: str = '',
        decimals: int = 1,
        length: int = 50,
        fill: str = '█',
        print_end: str = '\r'
    ):
        """初始化进度条
        
        Args:
            total: 总项数
            prefix: 前缀字符串
            suffix: 后缀字符串
            decimals: 百分比小数位数
            length: 进度条长度
            fill: 进度条填充字符
            print_end: 打印结束字符
        """
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.decimals = decimals
        self.length = length
        self.fill = fill
        self.print_end = print_end
        self.current = 0
        self._lock = threading.Lock()
        self.start_time = time.time()
    
    def update(self, n: int = 1) -> None:
        """更新进度
        
        Args:
            n: 增加的项数
        """
        with self._lock:
            self.current += n
            self._print_progress()
    
    def _print_progress(self) -> None:
        """打印进度"""
        percent = 100 * (self.current / float(self.total))
        filled_length = int(self.length * self.current // self.total)
        bar = self.fill * filled_length + '-' * (self.length - filled_length)
        
        # 计算剩余时间
        elapsed = time.time() - self.start_time
        if self.current > 0:
            items_per_second = self.current / elapsed
            remaining_items = self.total - self.current
            eta = remaining_items / items_per_second if items_per_second > 0 else 0
            eta_str = f"ETA: {self._format_time(eta)}"
        else:
            eta_str = "ETA: 未知"
        
        # 打印进度条
        print(f'\r{self.prefix} |{bar}| {percent:.{self.decimals}f}% {self.suffix} {eta_str}', end=self.print_end)
        
        # 如果完成，打印换行
        if self.current == self.total:
            print()
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """格式化时间
        
        Args:
            seconds: 秒数
        
        Returns:
            格式化后的时间字符串
        """
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            seconds = int(seconds % 60)
            return f"{minutes}分{seconds}秒"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}时{minutes}分"


def timed(logger_name: Optional[str] = None):
    """函数执行时间装饰器
    
    Args:
        logger_name: 日志记录器名称，如果为None则使用默认记录器
    
    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取日志记录器
            log = logging.getLogger(logger_name or "re-centris.performance_monitor")
            
            # 记录开始时间
            start_time = time.time()
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 计算执行时间
            elapsed_time = time.time() - start_time
            
            # 记录执行时间
            log.info(f"函数 {func.__name__} 执行时间: {elapsed_time:.6f}秒")
            
            return result
        return wrapper
    return decorator 