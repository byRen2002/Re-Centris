import unittest
import os
import tempfile
import shutil
import json
import subprocess
from unittest.mock import patch
from preprocessor.preprocessor import Preprocessor
from detector.Detector import Detector

class TestSecurity(unittest.TestCase):
    """安全测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        cls.work_dir = tempfile.mkdtemp()
        cls._create_test_environment()
        
    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        shutil.rmtree(cls.work_dir)
        
    @classmethod
    def _create_test_environment(cls):
        """创建测试环境"""
        # 创建目录结构
        dirs = [
            "input",
            "preprocessor/result",
            "preprocessor/initialSigs",
            "preprocessor/componentDB",
            "preprocessor/metaInfos",
            "detector/result"
        ]
        
        for dir_path in dirs:
            os.makedirs(os.path.join(cls.work_dir, dir_path))
            
    def setUp(self):
        """测试前准备"""
        self.preprocessor = Preprocessor()
        self.detector = Detector()
        
        self.preprocessor.config.set_base_path(self.work_dir)
        self.detector.base_path = self.work_dir
        
    def test_path_traversal(self):
        """测试路径遍历攻击防护"""
        # 测试相对路径遍历
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\Windows\\System32\\config\\SAM",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2f",  # URL编码的../../../
            "input/project/../../etc/passwd"
        ]
        
        for path in malicious_paths:
            full_path = os.path.join(self.work_dir, path)
            result = self.detector.process_file(full_path, self.work_dir)
            self.assertEqual(result, ({}, 0, 0, 0))
            
    def test_file_content_injection(self):
        """测试文件内容注入防护"""
        # 创建包含恶意内容的文件
        malicious_file = os.path.join(self.work_dir, "input/malicious.cpp")
        with open(malicious_file, 'w') as f:
            f.write("""
                #include <stdlib.h>
                
                int main() {
                    system("rm -rf /");  // 危险的系统调用
                    return 0;
                }
                
                __attribute__((constructor))
                void init() {
                    system("echo 'Malicious code executed'");
                }
            """)
            
        # 确保处理过程不执行代码
        with patch('subprocess.run') as mock_run:
            self.detector.process_file(malicious_file, self.work_dir)
            mock_run.assert_not_called()
            
    def test_memory_limits(self):
        """测试内存限制"""
        # 创建大文件
        large_file = os.path.join(self.work_dir, "input/large.cpp")
        with open(large_file, 'w') as f:
            f.write("a" * (100 * 1024 * 1024))  # 100MB
            
        try:
            self.detector.process_file(large_file, self.work_dir)
        except MemoryError:
            self.fail("内存限制处理失败")
            
    def test_cpu_limits(self):
        """测试CPU限制"""
        # 创建CPU密集型文件
        cpu_intensive_file = os.path.join(self.work_dir, "input/cpu_intensive.cpp")
        with open(cpu_intensive_file, 'w') as f:
            f.write("int main() { while(1); return 0; }")
            
        start_time = time.time()
        self.detector.process_file(cpu_intensive_file, self.work_dir)
        duration = time.time() - start_time
        
        self.assertLess(duration, 10)  # 应该在10秒内超时
        
    def test_file_type_validation(self):
        """测试文件类型验证"""
        # 创建伪装的可执行文件
        fake_cpp = os.path.join(self.work_dir, "input/fake.cpp")
        with open(fake_cpp, 'wb') as f:
            f.write(b"MZ\x90\x00\x03")  # PE文件头
            
        result = self.detector.process_file(fake_cpp, self.work_dir)
        self.assertEqual(result, ({}, 0, 0, 0))
        
    def test_input_sanitization(self):
        """测试输入净化"""
        # 测试SQL注入
        malicious_input = "'; DROP TABLE users; --"
        safe_path = os.path.join(self.work_dir, malicious_input)
        result = self.detector.process_file(safe_path, self.work_dir)
        self.assertEqual(result, ({}, 0, 0, 0))
        
        # 测试命令注入
        malicious_input = "; rm -rf /"
        safe_path = os.path.join(self.work_dir, malicious_input)
        result = self.detector.process_file(safe_path, self.work_dir)
        self.assertEqual(result, ({}, 0, 0, 0))
        
    def test_file_permissions(self):
        """测试文件权限"""
        # 创建只读文件
        readonly_file = os.path.join(self.work_dir, "input/readonly.cpp")
        with open(readonly_file, 'w') as f:
            f.write("int main() { return 0; }")
            
        # 设置只读权限
        os.chmod(readonly_file, 0o444)
        
        try:
            self.detector.process_file(readonly_file, self.work_dir)
        except PermissionError:
            self.fail("文件权限处理失败")
            
    def test_concurrent_access(self):
        """测试并发访问安全"""
        import threading
        
        # 创建测试文件
        test_file = os.path.join(self.work_dir, "input/concurrent.cpp")
        with open(test_file, 'w') as f:
            f.write("int main() { return 0; }")
            
        # 并发访问
        def process_file():
            self.detector.process_file(test_file, self.work_dir)
            
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=process_file)
            threads.append(thread)
            thread.start()
            
        for thread in threads:
            thread.join()
            
    def test_resource_cleanup(self):
        """测试资源清理"""
        import psutil
        
        # 记录初始文件描述符数量
        process = psutil.Process()
        initial_fds = process.num_fds()
        
        # 执行多次操作
        for _ in range(10):
            test_file = os.path.join(self.work_dir, "input/test.cpp")
            with open(test_file, 'w') as f:
                f.write("int main() { return 0; }")
                
            self.detector.process_file(test_file, self.work_dir)
            
        # 验证文件描述符没有泄漏
        final_fds = process.num_fds()
        self.assertLessEqual(final_fds - initial_fds, 5)
        
    def test_data_validation(self):
        """测试数据验证"""
        # 测试无效的TLSH哈希
        invalid_hashes = [
            "not_a_hash",
            "T1" + "0" * 69,  # 长度不足
            "T1" + "0" * 71,  # 长度过长
            "T1" + "XYZ" + "0" * 67  # 无效字符
        ]
        
        for hash_val in invalid_hashes:
            result = self.detector._compute_tlsh(hash_val)
            self.assertIsNone(result)
            
    def test_error_handling(self):
        """测试错误处理"""
        # 测试文件不存在
        result = self.detector.process_file(
            "nonexistent.cpp",
            self.work_dir
        )
        self.assertEqual(result, ({}, 0, 0, 0))
        
        # 测试无效组件
        result = self.detector.process_component(
            ("invalid_comp", {}, "test_repo", {})
        )
        self.assertIsNone(result)
        
        # 测试无效配置
        with self.assertRaises(Exception):
            detector = Detector("invalid_config.yaml")
            
if __name__ == '__main__':
    unittest.main() 