"""内存优化器测试模块

该模块包含了对MemoryOptimizer类的单元测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import os
import tempfile
import psutil
from unittest.mock import patch, MagicMock

from core.memory_optimizer import MemoryOptimizer
from core.config_manager import ConfigManager

class TestMemoryOptimizer(unittest.TestCase):
    """MemoryOptimizer类的测试用例"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建临时配置文件
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.yaml")
        
        # 测试配置数据
        self.test_config = {
            "memory": {
                "limit": 1024 * 1024 * 1024,  # 1GB
                "threshold": 0.8,  # 80%
                "cleanup_threshold": 0.9,  # 90%
                "min_free": 512 * 1024 * 1024  # 512MB
            }
        }
        
        # 写入测试配置
        with open(self.config_file, 'w') as f:
            yaml.dump(self.test_config, f)
            
        # 创建ConfigManager实例
        self.config_manager = ConfigManager(self.config_file)
        
        # 创建MemoryOptimizer实例
        self.memory_optimizer = MemoryOptimizer(self.config_manager)
        
    def tearDown(self):
        """测试后的清理工作"""
        # 删除临时文件和目录
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
        os.rmdir(self.temp_dir)
        
    def test_memory_check(self):
        """测试内存检查"""
        # 模拟内存使用情况
        with patch('psutil.virtual_memory') as mock_memory:
            # 模拟内存充足的情况
            mock_memory.return_value = MagicMock(
                total=8 * 1024 * 1024 * 1024,  # 8GB总内存
                available=4 * 1024 * 1024 * 1024  # 4GB可用内存
            )
            
            # 验证内存检查通过
            self.assertTrue(
                self.memory_optimizer.check_memory_available(
                    1024 * 1024 * 1024  # 需要1GB内存
                )
            )
            
            # 模拟内存不足的情况
            mock_memory.return_value = MagicMock(
                total=8 * 1024 * 1024 * 1024,  # 8GB总内存
                available=256 * 1024 * 1024  # 256MB可用内存
            )
            
            # 验证内存检查失败
            self.assertFalse(
                self.memory_optimizer.check_memory_available(
                    1024 * 1024 * 1024  # 需要1GB内存
                )
            )
            
    def test_memory_cleanup(self):
        """测试内存清理"""
        # 创建一些大对象来占用内存
        large_objects = []
        for _ in range(5):
            large_objects.append(bytearray(100 * 1024 * 1024))  # 每个100MB
            
        # 记录清理前的内存使用
        before_cleanup = psutil.Process().memory_info().rss
        
        # 执行内存清理
        self.memory_optimizer.cleanup()
        
        # 记录清理后的内存使用
        after_cleanup = psutil.Process().memory_info().rss
        
        # 验证内存使用减少
        self.assertLess(after_cleanup, before_cleanup)
        
    def test_memory_monitoring(self):
        """测试内存监控"""
        # 启动监控
        self.memory_optimizer.start_monitoring()
        
        # 验证监控线程已启动
        self.assertTrue(self.memory_optimizer.is_monitoring())
        
        # 停止监控
        self.memory_optimizer.stop_monitoring()
        
        # 验证监控线程已停止
        self.assertFalse(self.memory_optimizer.is_monitoring())
        
    def test_memory_limit_enforcement(self):
        """测试内存限制执行"""
        # 测试超出内存限制
        with self.assertRaises(MemoryError):
            # 尝试分配超过限制的内存
            self.memory_optimizer.allocate_memory(
                self.test_config['memory']['limit'] * 2
            )
            
    def test_memory_stats(self):
        """测试内存统计"""
        # 获取内存统计信息
        stats = self.memory_optimizer.get_memory_stats()
        
        # 验证统计信息的完整性
        self.assertIn('total', stats)
        self.assertIn('available', stats)
        self.assertIn('used', stats)
        self.assertIn('free', stats)
        self.assertIn('percent', stats)
        
    def test_optimization_strategies(self):
        """测试优化策略"""
        # 测试不同的优化级别
        strategies = [
            'minimal',  # 最小优化
            'moderate',  # 中等优化
            'aggressive'  # 激进优化
        ]
        
        for strategy in strategies:
            # 设置优化策略
            self.memory_optimizer.set_optimization_strategy(strategy)
            
            # 验证策略设置成功
            self.assertEqual(
                self.memory_optimizer.get_current_strategy(),
                strategy
            )
            
    def test_memory_pressure_handling(self):
        """测试内存压力处理"""
        # 模拟高内存压力情况
        with patch('psutil.virtual_memory') as mock_memory:
            mock_memory.return_value = MagicMock(
                percent=95.0  # 95%内存使用率
            )
            
            # 触发内存压力处理
            self.memory_optimizer.handle_memory_pressure()
            
            # 验证是否触发了清理操作
            self.assertTrue(self.memory_optimizer.cleanup_triggered)
            
    def test_concurrent_memory_operations(self):
        """测试并发内存操作"""
        import threading
        
        def memory_worker():
            # 执行一些内存操作
            for _ in range(10):
                # 分配和释放内存
                data = bytearray(10 * 1024 * 1024)  # 10MB
                self.memory_optimizer.track_allocation(len(data))
                del data
                self.memory_optimizer.track_deallocation(10 * 1024 * 1024)
                
        # 创建多个线程
        threads = [threading.Thread(target=memory_worker) for _ in range(4)]
        
        # 启动所有线程
        for thread in threads:
            thread.start()
            
        # 等待所有线程完成
        for thread in threads:
            thread.join()
            
        # 验证内存跟踪的准确性
        self.assertEqual(
            self.memory_optimizer.get_tracked_allocations(),
            0
        )

if __name__ == '__main__':
    unittest.main() 