"""资源管理器测试模块

该模块包含了对ResourceManager类的单元测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from core.resource_manager import ResourceManager
from core.config_manager import ConfigManager

class TestResourceManager(unittest.TestCase):
    """ResourceManager类的测试用例"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.test_repo_path = os.path.join(self.temp_dir, "repos")
        self.test_cache_path = os.path.join(self.temp_dir, "cache")
        
        # 创建测试配置
        self.config = {
            "paths": {
                "repo": self.test_repo_path,
                "cache": self.test_cache_path
            },
            "limits": {
                "max_repo_size": 1024 * 1024 * 100,  # 100MB
                "max_cache_size": 1024 * 1024 * 500   # 500MB
            }
        }
        
        # 创建配置文件
        self.config_file = os.path.join(self.temp_dir, "config.yaml")
        with open(self.config_file, 'w') as f:
            yaml.dump(self.config, f)
            
        # 创建ConfigManager实例
        self.config_manager = ConfigManager(self.config_file)
        
        # 创建ResourceManager实例
        self.resource_manager = ResourceManager(self.config_manager)
        
    def tearDown(self):
        """测试后的清理工作"""
        # 删除临时目录及其内容
        shutil.rmtree(self.temp_dir)
        
    def test_init_directories(self):
        """测试目录初始化"""
        # 验证目录是否被创建
        self.assertTrue(os.path.exists(self.test_repo_path))
        self.assertTrue(os.path.exists(self.test_cache_path))
        
    def test_check_disk_space(self):
        """测试磁盘空间检查"""
        # 模拟磁盘空间不足的情况
        with patch('psutil.disk_usage') as mock_disk_usage:
            mock_disk_usage.return_value = MagicMock(
                free=1024 * 1024  # 1MB可用空间
            )
            
            with self.assertRaises(RuntimeError):
                self.resource_manager.check_disk_space(
                    self.test_repo_path,
                    required_space=1024 * 1024 * 10  # 需要10MB
                )
                
    def test_cleanup_old_files(self):
        """测试旧文件清理"""
        # 创建测试文件
        test_files = []
        for i in range(5):
            file_path = os.path.join(self.test_cache_path, f"test_{i}.txt")
            with open(file_path, 'w') as f:
                f.write("test data")
            test_files.append(file_path)
            
        # 修改文件访问时间
        for i, file_path in enumerate(test_files):
            access_time = time.time() - (i + 1) * 86400  # i+1天前
            os.utime(file_path, (access_time, access_time))
            
        # 清理3天前的文件
        self.resource_manager.cleanup_old_files(
            self.test_cache_path,
            days=3
        )
        
        # 验证结果
        remaining_files = os.listdir(self.test_cache_path)
        self.assertEqual(len(remaining_files), 3)  # 应该保留3个文件
        
    def test_monitor_resource_usage(self):
        """测试资源使用监控"""
        # 创建一些测试文件来占用空间
        for i in range(10):
            file_path = os.path.join(self.test_cache_path, f"large_{i}.txt")
            with open(file_path, 'wb') as f:
                f.write(b'0' * 1024 * 1024)  # 写入1MB数据
                
        # 获取资源使用情况
        usage = self.resource_manager.get_resource_usage()
        
        # 验证返回的数据结构
        self.assertIn('disk_usage', usage)
        self.assertIn('memory_usage', usage)
        self.assertIn('cpu_usage', usage)
        
    def test_resource_limits(self):
        """测试资源限制"""
        # 测试超出仓库大小限制
        large_data = b'0' * (self.config['limits']['max_repo_size'] + 1024)
        
        with self.assertRaises(ValueError):
            self.resource_manager.check_size_limit(
                len(large_data),
                'repo'
            )
            
    def test_file_operations(self):
        """测试文件操作"""
        # 测试文件写入
        test_data = b"test content"
        test_file = os.path.join(self.test_cache_path, "test.txt")
        
        self.resource_manager.write_file(test_file, test_data)
        self.assertTrue(os.path.exists(test_file))
        
        # 测试文件读取
        read_data = self.resource_manager.read_file(test_file)
        self.assertEqual(read_data, test_data)
        
        # 测试文件删除
        self.resource_manager.delete_file(test_file)
        self.assertFalse(os.path.exists(test_file))
        
    def test_path_validation(self):
        """测试路径验证"""
        # 测试无效路径
        invalid_paths = [
            "../outside.txt",
            "/absolute/path/file.txt",
            "../../etc/passwd"
        ]
        
        for path in invalid_paths:
            with self.assertRaises(ValueError):
                self.resource_manager.validate_path(path)
                
    def test_concurrent_access(self):
        """测试并发访问"""
        import threading
        
        def worker():
            # 执行一些文件操作
            for i in range(10):
                file_path = os.path.join(
                    self.test_cache_path,
                    f"thread_{threading.get_ident()}_{i}.txt"
                )
                self.resource_manager.write_file(file_path, b"test")
                self.resource_manager.read_file(file_path)
                self.resource_manager.delete_file(file_path)
                
        # 创建多个线程
        threads = [threading.Thread(target=worker) for _ in range(4)]
        
        # 启动所有线程
        for thread in threads:
            thread.start()
            
        # 等待所有线程完成
        for thread in threads:
            thread.join()
            
        # 验证没有遗留文件
        remaining_files = os.listdir(self.test_cache_path)
        self.assertEqual(len(remaining_files), 0)

if __name__ == '__main__':
    unittest.main() 