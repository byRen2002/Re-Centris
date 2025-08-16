"""检测器测试模块

该模块包含了对Detector类的单元测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import os
import tempfile
import json
import tlsh
from unittest.mock import patch, MagicMock

from detector.run_detector import Detector
from core.config_manager import ConfigManager

class TestDetector(unittest.TestCase):
    """Detector类的测试用例"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建临时测试目录
        self.temp_dir = tempfile.mkdtemp()
        self.test_data_dir = os.path.join(self.temp_dir, "test_data")
        os.makedirs(self.test_data_dir)
        
        # 创建测试配置
        self.config_file = os.path.join(self.temp_dir, "config.yaml")
        self.test_config = {
            "paths": {
                "repo": os.path.join(self.test_data_dir, "repos"),
                "results": os.path.join(self.test_data_dir, "results"),
                "components": os.path.join(self.test_data_dir, "components"),
                "logs": os.path.join(self.test_data_dir, "logs")
            },
            "detection": {
                "tlsh_threshold": 30,
                "similarity_threshold": 0.8,
                "min_component_size": 100,
                "max_workers": 4
            },
            "logging": {
                "level": "INFO",
                "file": "detector.log"
            }
        }
        
        with open(self.config_file, 'w') as f:
            yaml.dump(self.test_config, f)
            
        # 创建必要的目录
        for path in self.test_config["paths"].values():
            os.makedirs(path, exist_ok=True)
            
        # 创建测试数据
        self._create_test_data()
        
        # 创建Detector实例
        self.config_manager = ConfigManager(self.config_file)
        self.detector = Detector(self.config_manager)
        
    def tearDown(self):
        """测试后的清理工作"""
        # 删除临时目录及其内容
        shutil.rmtree(self.temp_dir)
        
    def _create_test_data(self):
        """创建测试数据"""
        # 创建组件数据库
        component_db = os.path.join(
            self.test_config["paths"]["components"],
            "test_component.json"
        )
        
        test_functions = {
            tlsh.hash(b"function1"): {
                "name": "test_func1",
                "file": "test1.py",
                "component": "component1"
            },
            tlsh.hash(b"function2"): {
                "name": "test_func2",
                "file": "test2.py",
                "component": "component2"
            }
        }
        
        with open(component_db, 'w') as f:
            json.dump(test_functions, f)
            
        # 创建测试代码文件
        test_code = os.path.join(
            self.test_config["paths"]["repo"],
            "test_code.py"
        )
        
        with open(test_code, 'w') as f:
            f.write("def test_func1():\n    return 'test1'\n\n")
            f.write("def test_func2():\n    return 'test2'\n")
            
    def test_initialization(self):
        """测试初始化"""
        # 验证配置加载
        self.assertIsNotNone(self.detector.config)
        
        # 验证日志设置
        self.assertTrue(os.path.exists(
            os.path.join(self.test_config["paths"]["logs"], "detector.log")
        ))
        
    def test_tlsh_computation(self):
        """测试TLSH计算"""
        # 计算测试函数的TLSH
        code = "def test_function():\n    return 'test'\n"
        hash_value = self.detector.compute_tlsh(code)
        
        # 验证哈希值格式
        self.assertIsInstance(hash_value, str)
        self.assertGreater(len(hash_value), 0)
        
    def test_component_detection(self):
        """测试组件检测"""
        # 执行检测
        results = self.detector.detect(
            os.path.join(self.test_config["paths"]["repo"], "test_code.py")
        )
        
        # 验证检测结果
        self.assertIsInstance(results, dict)
        self.assertIn("matches", results)
        self.assertIn("statistics", results)
        
    def test_similarity_calculation(self):
        """测试相似度计算"""
        # 计算两个相似函数的TLSH差异
        code1 = "def test_function():\n    return 'test1'\n"
        code2 = "def test_function():\n    return 'test2'\n"
        
        hash1 = self.detector.compute_tlsh(code1)
        hash2 = self.detector.compute_tlsh(code2)
        
        diff = self.detector.compute_tlsh_diff(hash1, hash2)
        
        # 验证差异值在合理范围内
        self.assertIsInstance(diff, int)
        self.assertGreaterEqual(diff, 0)
        self.assertLessEqual(diff, 1000)
        
    def test_parallel_processing(self):
        """测试并行处理"""
        # 创建多个测试文件
        for i in range(10):
            test_file = os.path.join(
                self.test_config["paths"]["repo"],
                f"test_code_{i}.py"
            )
            with open(test_file, 'w') as f:
                f.write(f"def test_func_{i}():\n    return 'test{i}'\n")
                
        # 执行并行检测
        results = self.detector.detect_batch(
            self.test_config["paths"]["repo"]
        )
        
        # 验证结果
        self.assertEqual(len(results), 10)
        
    def test_cache_mechanism(self):
        """测试缓存机制"""
        # 第一次检测
        file_path = os.path.join(
            self.test_config["paths"]["repo"],
            "test_code.py"
        )
        
        start_time = time.time()
        first_result = self.detector.detect(file_path)
        first_time = time.time() - start_time
        
        # 第二次检测（应该使用缓存）
        start_time = time.time()
        second_result = self.detector.detect(file_path)
        second_time = time.time() - start_time
        
        # 验证结果一致性和性能提升
        self.assertEqual(first_result, second_result)
        self.assertLess(second_time, first_time)
        
    def test_error_handling(self):
        """测试错误处理"""
        # 测试不存在的文件
        with self.assertRaises(FileNotFoundError):
            self.detector.detect("nonexistent_file.py")
            
        # 测试无效的组件数据库
        with open(os.path.join(
            self.test_config["paths"]["components"],
            "invalid.json"
        ), 'w') as f:
            f.write("invalid json")
            
        with self.assertRaises(json.JSONDecodeError):
            self.detector.load_component_db("invalid.json")
            
    def test_memory_management(self):
        """测试内存管理"""
        import psutil
        process = psutil.Process()
        
        # 记录初始内存使用
        initial_memory = process.memory_info().rss
        
        # 处理大量数据
        for i in range(100):
            test_file = os.path.join(
                self.test_config["paths"]["repo"],
                f"large_test_{i}.py"
            )
            with open(test_file, 'w') as f:
                for j in range(1000):
                    f.write(f"def test_func_{i}_{j}():\n    return 'test'\n")
                    
        self.detector.detect_batch(self.test_config["paths"]["repo"])
        
        # 记录最终内存使用
        final_memory = process.memory_info().rss
        
        # 验证内存增长在合理范围内
        memory_growth = (final_memory - initial_memory) / (1024 * 1024)  # MB
        self.assertLess(memory_growth, 1000)  # 内存增长应小于1GB
        
    def test_performance_monitoring(self):
        """测试性能监控"""
        # 启用性能监控
        self.detector.enable_performance_monitoring()
        
        # 执行一些操作
        self.detector.detect(
            os.path.join(self.test_config["paths"]["repo"], "test_code.py")
        )
        
        # 获取性能统计
        stats = self.detector.get_performance_stats()
        
        # 验证统计信息
        self.assertIn("processing_time", stats)
        self.assertIn("memory_usage", stats)
        self.assertIn("cpu_usage", stats)
        
    def test_result_export(self):
        """测试结果导出"""
        # 执行检测
        results = self.detector.detect(
            os.path.join(self.test_config["paths"]["repo"], "test_code.py")
        )
        
        # 导出结果
        export_file = os.path.join(
            self.test_config["paths"]["results"],
            "test_results.json"
        )
        self.detector.export_results(results, export_file)
        
        # 验证导出文件
        self.assertTrue(os.path.exists(export_file))
        
        # 验证导出内容
        with open(export_file) as f:
            exported_data = json.load(f)
            self.assertEqual(exported_data, results)

if __name__ == '__main__':
    unittest.main() 