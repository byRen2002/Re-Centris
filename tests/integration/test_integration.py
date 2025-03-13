"""集成测试模块

该模块包含了Re-Centris系统的集成测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import os
import tempfile
import shutil
import json
import time
from unittest.mock import patch, MagicMock

from core.config_manager import ConfigManager
from preprocessor.preprocessor import (
    PreprocessorConfig,
    SignatureProcessor,
    MetaInfoManager,
    CodeSegmenter
)
from detector.detector import Detector

class TestIntegration(unittest.TestCase):
    """Re-Centris系统集成测试"""
    
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
                "logs": os.path.join(self.test_data_dir, "logs"),
                "cache": os.path.join(self.test_data_dir, "cache")
            },
            "detection": {
                "tlsh_threshold": 30,
                "similarity_threshold": 0.8,
                "min_component_size": 100,
                "max_workers": 4
            },
            "preprocessing": {
                "batch_size": 1000,
                "memory_limit": 1024 * 1024 * 1024  # 1GB
            },
            "logging": {
                "level": "INFO",
                "file": "re_centris.log"
            }
        }
        
        with open(self.config_file, 'w') as f:
            yaml.dump(self.test_config, f)
            
        # 创建必要的目录
        for path in self.test_config["paths"].values():
            os.makedirs(path, exist_ok=True)
            
        # 创建测试数据
        self._create_test_data()
        
        # 初始化组件
        self.config_manager = ConfigManager(self.config_file)
        self.preprocessor_config = PreprocessorConfig()
        self.preprocessor_config.current_path = self.test_data_dir
        self.detector = Detector(self.config_manager)
        
    def tearDown(self):
        """测试后的清理工作"""
        # 删除临时目录及其内容
        shutil.rmtree(self.temp_dir)
        
    def _create_test_data(self):
        """创建测试数据"""
        # 创建测试仓库
        repo_dir = os.path.join(self.test_config["paths"]["repo"], "test_repo")
        os.makedirs(repo_dir)
        
        # 创建测试代码文件
        test_files = [
            ("component1.py", [
                "def func1():\n    return 'test1'\n",
                "def func2():\n    return 'test2'\n"
            ]),
            ("component2.py", [
                "def func3():\n    return 'test3'\n",
                "def func4():\n    return 'test4'\n"
            ])
        ]
        
        for filename, functions in test_files:
            with open(os.path.join(repo_dir, filename), 'w') as f:
                for func in functions:
                    f.write(func + "\n")
                    
    def test_end_to_end_workflow(self):
        """测试端到端工作流"""
        # 1. 预处理阶段
        processor = SignatureProcessor(self.preprocessor_config)
        processor.process_single_repo("test_repo")
        
        # 验证预处理输出
        self.assertTrue(
            os.path.exists(
                os.path.join(self.preprocessor_config.func_date_path, "test_repo_funcdate")
            )
        )
        
        # 2. 元信息管理
        meta_manager = MetaInfoManager(self.preprocessor_config)
        meta_manager.save_meta_infos()
        
        # 验证元信息文件
        self.assertTrue(
            os.path.exists(os.path.join(self.preprocessor_config.meta_path, "aveFuncs"))
        )
        
        # 3. 代码分割
        segmenter = CodeSegmenter(self.preprocessor_config)
        segmenter.segment_code()
        
        # 验证分割结果
        self.assertTrue(
            os.path.exists(
                os.path.join(self.preprocessor_config.final_db_path, "test_repo_sig")
            )
        )
        
        # 4. 组件检测
        detection_results = self.detector.detect_batch(
            os.path.join(self.test_config["paths"]["repo"], "test_repo")
        )
        
        # 验证检测结果
        self.assertIsInstance(detection_results, dict)
        self.assertIn("matches", detection_results)
        
        # 5. 结果导出
        export_file = os.path.join(
            self.test_config["paths"]["results"],
            "final_results.json"
        )
        self.detector.export_results(detection_results, export_file)
        
        # 验证导出文件
        self.assertTrue(os.path.exists(export_file))
        
    def test_error_propagation(self):
        """测试错误传播"""
        # 创建无效的测试数据
        invalid_repo = os.path.join(self.test_config["paths"]["repo"], "invalid_repo")
        os.makedirs(invalid_repo)
        
        with open(os.path.join(invalid_repo, "invalid.py"), 'w') as f:
            f.write("invalid python code")
            
        # 验证错误处理
        with self.assertRaises(Exception):
            processor = SignatureProcessor(self.preprocessor_config)
            processor.process_single_repo("invalid_repo")
            
    def test_performance_integration(self):
        """测试性能集成"""
        # 创建大量测试数据
        large_repo = os.path.join(self.test_config["paths"]["repo"], "large_repo")
        os.makedirs(large_repo)
        
        for i in range(100):
            with open(os.path.join(large_repo, f"file_{i}.py"), 'w') as f:
                for j in range(100):
                    f.write(f"def func_{i}_{j}():\n    return 'test'\n")
                    
        # 记录开始时间
        start_time = time.time()
        
        # 执行完整工作流
        processor = SignatureProcessor(self.preprocessor_config)
        processor.process_single_repo("large_repo")
        
        meta_manager = MetaInfoManager(self.preprocessor_config)
        meta_manager.save_meta_infos()
        
        segmenter = CodeSegmenter(self.preprocessor_config)
        segmenter.segment_code()
        
        detection_results = self.detector.detect_batch(large_repo)
        
        # 计算总时间
        total_time = time.time() - start_time
        
        # 验证性能
        self.assertLess(total_time, 300)  # 应该在5分钟内完成
        
    def test_resource_management(self):
        """测试资源管理集成"""
        import psutil
        process = psutil.Process()
        
        # 记录初始资源使用
        initial_memory = process.memory_info().rss
        initial_files = len(process.open_files())
        
        # 执行完整工作流
        self.test_end_to_end_workflow()
        
        # 记录最终资源使用
        final_memory = process.memory_info().rss
        final_files = len(process.open_files())
        
        # 验证资源释放
        self.assertLessEqual(final_files, initial_files + 5)  # 允许少量文件句柄增长
        self.assertLess(
            (final_memory - initial_memory) / (1024 * 1024),
            500  # 内存增长应小于500MB
        )
        
    def test_concurrent_operations(self):
        """测试并发操作"""
        import threading
        
        def worker(repo_name):
            # 创建测试数据
            repo_dir = os.path.join(self.test_config["paths"]["repo"], repo_name)
            os.makedirs(repo_dir)
            
            with open(os.path.join(repo_dir, "test.py"), 'w') as f:
                f.write("def test():\n    return 'test'\n")
                
            # 执行处理流程
            processor = SignatureProcessor(self.preprocessor_config)
            processor.process_single_repo(repo_name)
            
            # 执行检测
            self.detector.detect(repo_dir)
            
        # 创建多个线程
        threads = []
        for i in range(4):
            thread = threading.Thread(
                target=worker,
                args=(f"concurrent_repo_{i}",)
            )
            threads.append(thread)
            thread.start()
            
        # 等待所有线程完成
        for thread in threads:
            thread.join()
            
        # 验证所有处理都成功完成
        for i in range(4):
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        self.preprocessor_config.func_date_path,
                        f"concurrent_repo_{i}_funcdate"
                    )
                )
            )
            
    def test_cache_consistency(self):
        """测试缓存一致性"""
        # 执行第一次处理
        self.test_end_to_end_workflow()
        
        # 修改测试文件
        test_file = os.path.join(
            self.test_config["paths"]["repo"],
            "test_repo",
            "component1.py"
        )
        
        with open(test_file, 'a') as f:
            f.write("def new_func():\n    return 'new'\n")
            
        # 执行第二次处理
        detection_results = self.detector.detect_batch(
            os.path.join(self.test_config["paths"]["repo"], "test_repo")
        )
        
        # 验证结果反映了更改
        self.assertIn("new_func", str(detection_results))

if __name__ == '__main__':
    unittest.main() 