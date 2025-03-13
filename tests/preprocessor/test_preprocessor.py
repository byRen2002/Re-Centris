"""预处理器测试模块

该模块包含了对Preprocessor类的单元测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import os
import tempfile
import shutil
import json
from unittest.mock import patch, MagicMock

from preprocessor.preprocessor import (
    PreprocessorConfig,
    SignatureProcessor,
    MetaInfoManager,
    CodeSegmenter
)

class TestPreprocessor(unittest.TestCase):
    """Preprocessor类的测试用例"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建临时测试目录
        self.temp_dir = tempfile.mkdtemp()
        self.test_data_dir = os.path.join(self.temp_dir, "test_data")
        os.makedirs(self.test_data_dir)
        
        # 创建测试仓库目录结构
        self.repo_dir = os.path.join(self.test_data_dir, "repos")
        self.repo_date_dir = os.path.join(self.test_data_dir, "repo_date")
        self.repo_func_dir = os.path.join(self.test_data_dir, "repo_functions")
        
        for dir_path in [self.repo_dir, self.repo_date_dir, self.repo_func_dir]:
            os.makedirs(dir_path)
            
        # 创建测试配置
        self.config = PreprocessorConfig()
        self.config.current_path = self.test_data_dir
        self.config.tag_date_path = self.repo_date_dir
        self.config.result_path = self.repo_func_dir
        
        # 创建测试数据
        self._create_test_data()
        
    def tearDown(self):
        """测试后的清理工作"""
        # 删除临时目录及其内容
        shutil.rmtree(self.temp_dir)
        
    def _create_test_data(self):
        """创建测试数据"""
        # 创建版本日期文件
        repo_date_file = os.path.join(self.repo_date_dir, "test_repo")
        with open(repo_date_file, 'w') as f:
            f.write("2024-01-01 tag: v1.0\n")
            f.write("2024-02-01 tag: v1.1\n")
            f.write("2024-03-01 tag: v2.0\n")
            
        # 创建函数签名文件
        repo_func_dir = os.path.join(self.repo_func_dir, "test_repo")
        os.makedirs(repo_func_dir)
        
        versions = ["v1.0", "v1.1", "v2.0"]
        for version in versions:
            func_file = os.path.join(repo_func_dir, f"fuzzy_{version}.hidx")
            with open(func_file, 'w') as f:
                f.write("hash\tfunction\tfile\n")
                f.write(f"hash1\tfunc1\tfile1.py\n")
                f.write(f"hash2\tfunc2\tfile2.py\n")
                
    def test_config_initialization(self):
        """测试配置初始化"""
        # 验证目录创建
        self.assertTrue(os.path.exists(self.config.ver_idx_path))
        self.assertTrue(os.path.exists(self.config.initial_db_path))
        self.assertTrue(os.path.exists(self.config.final_db_path))
        self.assertTrue(os.path.exists(self.config.meta_path))
        
    def test_signature_processing(self):
        """测试签名处理"""
        processor = SignatureProcessor(self.config)
        
        # 处理测试仓库
        processor.process_single_repo("test_repo")
        
        # 验证输出文件
        self.assertTrue(
            os.path.exists(
                os.path.join(self.config.func_date_path, "test_repo_funcdate")
            )
        )
        self.assertTrue(
            os.path.exists(
                os.path.join(self.config.ver_idx_path, "test_repo_idx")
            )
        )
        self.assertTrue(
            os.path.exists(
                os.path.join(self.config.initial_db_path, "test_repo_sig")
            )
        )
        
        # 验证版本索引内容
        with open(os.path.join(self.config.ver_idx_path, "test_repo_idx")) as f:
            ver_idx = json.load(f)
            self.assertEqual(len(ver_idx), 3)  # 应该有3个版本
            
    def test_meta_info_management(self):
        """测试元信息管理"""
        # 先处理签名
        processor = SignatureProcessor(self.config)
        processor.process_single_repo("test_repo")
        
        # 处理元信息
        meta_manager = MetaInfoManager(self.config)
        meta_manager.save_meta_infos()
        
        # 验证元信息文件
        self.assertTrue(
            os.path.exists(os.path.join(self.config.meta_path, "aveFuncs"))
        )
        self.assertTrue(
            os.path.exists(os.path.join(self.config.meta_path, "allFuncs"))
        )
        self.assertTrue(
            os.path.exists(os.path.join(self.config.meta_path, "uniqueFuncs"))
        )
        
        # 验证权重文件
        self.assertTrue(
            os.path.exists(
                os.path.join(self.config.weight_path, "test_repo_weights")
            )
        )
        
    def test_code_segmentation(self):
        """测试代码分割"""
        # 准备数据
        processor = SignatureProcessor(self.config)
        processor.process_single_repo("test_repo")
        
        meta_manager = MetaInfoManager(self.config)
        meta_manager.save_meta_infos()
        
        # 执行代码分割
        segmenter = CodeSegmenter(self.config)
        segmenter.segment_code()
        
        # 验证分割结果
        self.assertTrue(
            os.path.exists(
                os.path.join(self.config.final_db_path, "test_repo_sig")
            )
        )
        
    def test_version_date_extraction(self):
        """测试版本日期提取"""
        processor = SignatureProcessor(self.config)
        ver_dates = processor.extract_ver_date("test_repo")
        
        # 验证版本日期
        self.assertEqual(ver_dates["v1.0"], "2024-01-01")
        self.assertEqual(ver_dates["v1.1"], "2024-02-01")
        self.assertEqual(ver_dates["v2.0"], "2024-03-01")
        
    def test_error_handling(self):
        """测试错误处理"""
        processor = SignatureProcessor(self.config)
        
        # 测试处理不存在的仓库
        processor.process_single_repo("nonexistent_repo")
        
        # 验证不会创建相关文件
        self.assertFalse(
            os.path.exists(
                os.path.join(self.config.func_date_path, "nonexistent_repo_funcdate")
            )
        )
        
    def test_concurrent_processing(self):
        """测试并发处理"""
        import threading
        
        def worker():
            processor = SignatureProcessor(self.config)
            processor.process_single_repo("test_repo")
            
        # 创建多个线程
        threads = [threading.Thread(target=worker) for _ in range(4)]
        
        # 启动所有线程
        for thread in threads:
            thread.start()
            
        # 等待所有线程完成
        for thread in threads:
            thread.join()
            
        # 验证处理结果的一致性
        with open(os.path.join(self.config.ver_idx_path, "test_repo_idx")) as f:
            ver_idx = json.load(f)
            self.assertEqual(len(ver_idx), 3)
            
    def test_memory_efficiency(self):
        """测试内存效率"""
        import psutil
        process = psutil.Process()
        
        # 记录初始内存使用
        initial_memory = process.memory_info().rss
        
        # 处理大量数据
        processor = SignatureProcessor(self.config)
        for i in range(10):
            # 创建更多测试数据
            repo_name = f"test_repo_{i}"
            repo_dir = os.path.join(self.repo_func_dir, repo_name)
            os.makedirs(repo_dir)
            
            for j in range(100):
                with open(os.path.join(repo_dir, f"fuzzy_v{j}.hidx"), 'w') as f:
                    f.write("hash\tfunction\tfile\n")
                    for k in range(1000):
                        f.write(f"hash{k}\tfunc{k}\tfile{k}.py\n")
                        
            processor.process_single_repo(repo_name)
            
        # 记录最终内存使用
        final_memory = process.memory_info().rss
        
        # 验证内存增长在合理范围内
        memory_growth = (final_memory - initial_memory) / (1024 * 1024)  # MB
        self.assertLess(memory_growth, 1000)  # 内存增长应小于1GB

if __name__ == '__main__':
    unittest.main() 