"""缓存系统测试模块

该模块包含了对Cache类的单元测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import time
from unittest.mock import patch, MagicMock
import tempfile
import os

from core.cache import Cache

class TestCache(unittest.TestCase):
    """Cache类的测试用例"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.cache_size = 5
        self.expire_time = 1  # 1秒过期
        self.cache = Cache(self.cache_size, self.expire_time)
        
    def test_basic_operations(self):
        """测试基本的缓存操作"""
        # 测试设置和获取
        self.cache.set("key1", "value1")
        self.assertEqual(self.cache.get("key1"), "value1")
        
        # 测试不存在的键
        self.assertIsNone(self.cache.get("nonexistent"))
        
    def test_cache_size_limit(self):
        """测试缓存大小限制"""
        # 添加超过限制的项
        for i in range(self.cache_size + 2):
            self.cache.set(f"key{i}", f"value{i}")
            
        # 验证缓存大小不超过限制
        self.assertLessEqual(len(self.cache.cache), self.cache_size)
        
        # 验证最早的项被移除
        self.assertIsNone(self.cache.get("key0"))
        self.assertIsNotNone(self.cache.get(f"key{self.cache_size+1}"))
        
    def test_expiration(self):
        """测试缓存过期"""
        self.cache.set("expire_key", "expire_value")
        
        # 等待过期
        time.sleep(self.expire_time + 0.1)
        
        # 验证项已过期
        self.assertIsNone(self.cache.get("expire_key"))
        
    def test_clear(self):
        """测试清空缓存"""
        # 添加一些项
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")
        
        # 清空缓存
        self.cache.clear()
        
        # 验证缓存为空
        self.assertEqual(len(self.cache.cache), 0)
        self.assertEqual(len(self.cache.access_times), 0)
        
    def test_update_access_time(self):
        """测试访问时间更新"""
        self.cache.set("key", "value")
        first_access = self.cache.access_times["key"]
        
        # 等待一小段时间
        time.sleep(0.1)
        
        # 再次访问
        self.cache.get("key")
        second_access = self.cache.access_times["key"]
        
        # 验证访问时间已更新
        self.assertGreater(second_access, first_access)
        
    def test_persistence(self):
        """测试缓存持久化"""
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        cache_file = os.path.join(temp_dir, "cache.db")
        
        try:
            # 创建持久化缓存
            persistent_cache = Cache(
                self.cache_size,
                self.expire_time,
                persistent=True,
                cache_file=cache_file
            )
            
            # 添加数据
            persistent_cache.set("persist_key", "persist_value")
            
            # 关闭缓存
            persistent_cache.close()
            
            # 重新创建缓存并验证数据
            new_cache = Cache(
                self.cache_size,
                self.expire_time,
                persistent=True,
                cache_file=cache_file
            )
            
            self.assertEqual(new_cache.get("persist_key"), "persist_value")
            
        finally:
            # 清理
            if os.path.exists(cache_file):
                os.remove(cache_file)
            os.rmdir(temp_dir)
            
    def test_thread_safety(self):
        """测试线程安全性"""
        import threading
        
        def worker():
            for i in range(100):
                self.cache.set(f"thread_key_{i}", f"thread_value_{i}")
                self.cache.get(f"thread_key_{i}")
                
        # 创建多个线程同时操作缓存
        threads = [threading.Thread(target=worker) for _ in range(4)]
        
        # 启动所有线程
        for thread in threads:
            thread.start()
            
        # 等待所有线程完成
        for thread in threads:
            thread.join()
            
        # 验证缓存状态正常
        self.assertLessEqual(len(self.cache.cache), self.cache_size)
        
    def test_invalid_inputs(self):
        """测试无效输入处理"""
        # 测试无效的缓存大小
        with self.assertRaises(ValueError):
            Cache(-1, self.expire_time)
            
        # 测试无效的过期时间
        with self.assertRaises(ValueError):
            Cache(self.cache_size, -1)
            
    def test_memory_management(self):
        """测试内存管理"""
        large_data = "x" * 1024 * 1024  # 1MB数据
        
        # 添加大量数据
        for i in range(10):
            self.cache.set(f"large_key_{i}", large_data)
            
        # 验证缓存大小限制有效
        self.assertLessEqual(len(self.cache.cache), self.cache_size)

if __name__ == '__main__':
    unittest.main() 