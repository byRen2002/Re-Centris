import unittest
import os
import tempfile
import shutil
import json
from preprocessor.preprocessor import Preprocessor
from detector.Detector import Detector

class TestCloneDetection(unittest.TestCase):
    """克隆检测集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        # 创建临时工作目录
        cls.work_dir = tempfile.mkdtemp()
        
        # 创建测试项目结构
        cls._create_test_project()
        
    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        shutil.rmtree(cls.work_dir)
        
    @classmethod
    def _create_test_project(cls):
        """创建测试项目"""
        # 创建目录结构
        dirs = [
            "input/project1/src",
            "input/project2/src",
            "preprocessor/result",
            "preprocessor/initialSigs",
            "preprocessor/componentDB",
            "preprocessor/metaInfos",
            "detector/result"
        ]
        
        for dir_path in dirs:
            os.makedirs(os.path.join(cls.work_dir, dir_path))
            
        # 创建测试源文件
        cls._create_test_files()
        
    @classmethod
    def _create_test_files(cls):
        """创建测试文件"""
        # 项目1的源文件
        project1_file = os.path.join(cls.work_dir, "input/project1/src/main.cpp")
        with open(project1_file, 'w') as f:
            f.write("""
                int add(int a, int b) {
                    return a + b;
                }
                
                int subtract(int a, int b) {
                    return a - b;
                }
                
                int main() {
                    int x = 10, y = 5;
                    printf("%d\\n", add(x, y));
                    printf("%d\\n", subtract(x, y));
                    return 0;
                }
            """)
            
        # 项目2的源文件（包含克隆的代码）
        project2_file = os.path.join(cls.work_dir, "input/project2/src/calculator.cpp")
        with open(project2_file, 'w') as f:
            f.write("""
                // 克隆的add函数
                int add(int a, int b) {
                    return a + b;
                }
                
                // 修改的subtract函数
                int subtract(int x, int y) {
                    int result = x - y;
                    return result;
                }
                
                // 新的multiply函数
                int multiply(int a, int b) {
                    return a * b;
                }
                
                int main() {
                    int a = 20, b = 10;
                    printf("%d\\n", add(a, b));
                    printf("%d\\n", subtract(a, b));
                    printf("%d\\n", multiply(a, b));
                    return 0;
                }
            """)
            
    def setUp(self):
        """测试前准备"""
        # 初始化预处理器和检测器
        self.preprocessor = Preprocessor()
        self.detector = Detector()
        
        # 设置工作目录
        self.preprocessor.config.set_base_path(self.work_dir)
        self.detector.base_path = self.work_dir
        
    def test_end_to_end_clone_detection(self):
        """端到端克隆检测测试"""
        try:
            # 1. 运行预处理
            self.preprocessor.run()
            
            # 验证预处理结果
            self._verify_preprocessing()
            
            # 2. 运行克隆检测
            self.detector.detect(
                os.path.join(self.work_dir, "input/project2"),
                "project2"
            )
            
            # 验证检测结果
            self._verify_detection()
            
        except Exception as e:
            self.fail(f"端到端测试失败: {str(e)}")
            
    def _verify_preprocessing(self):
        """验证预处理结果"""
        # 检查初始签名
        initial_sigs_file = os.path.join(
            self.work_dir,
            "preprocessor/initialSigs/initialSigs.json"
        )
        self.assertTrue(os.path.exists(initial_sigs_file))
        
        with open(initial_sigs_file, 'r') as f:
            sigs = json.load(f)
            self.assertGreater(len(sigs), 0)
            
        # 检查组件数据库
        comp_db_dir = os.path.join(self.work_dir, "preprocessor/componentDB")
        self.assertTrue(os.path.exists(comp_db_dir))
        self.assertGreater(len(os.listdir(comp_db_dir)), 0)
        
    def _verify_detection(self):
        """验证检测结果"""
        # 检查检测结果文件
        result_file = os.path.join(
            self.work_dir,
            "detector/result/result_project2"
        )
        self.assertTrue(os.path.exists(result_file))
        
        with open(result_file, 'r') as f:
            results = f.readlines()
            self.assertGreater(len(results), 0)
            
            # 解析结果
            for result in results:
                parts = result.strip().split('\t')
                self.assertEqual(len(parts), 7)  # 验证结果格式
                
                # 验证字段
                project, repo, version, used, unused, modified, str_change = parts
                self.assertEqual(project, "project2")
                self.assertGreater(int(used), 0)  # 应该检测到至少一个使用的函数
                
    def test_incremental_detection(self):
        """增量检测测试"""
        # 首次检测
        self.preprocessor.run()
        self.detector.detect(
            os.path.join(self.work_dir, "input/project2"),
            "project2"
        )
        
        # 修改源文件
        project2_file = os.path.join(self.work_dir, "input/project2/src/calculator.cpp")
        with open(project2_file, 'a') as f:
            f.write("""
                // 新增的divide函数
                float divide(int a, int b) {
                    return a / (float)b;
                }
            """)
            
        # 再次检测
        self.preprocessor.run()
        self.detector.detect(
            os.path.join(self.work_dir, "input/project2"),
            "project2"
        )
        
        # 验证结果变化
        result_file = os.path.join(
            self.work_dir,
            "detector/result/result_project2"
        )
        with open(result_file, 'r') as f:
            results = f.readlines()
            last_result = results[-1].strip().split('\t')
            self.assertGreater(int(last_result[3]), 0)  # used
            self.assertGreater(int(last_result[4]), 0)  # unused
            
    def test_error_conditions(self):
        """错误条件测试"""
        # 测试空项目
        empty_dir = os.path.join(self.work_dir, "input/empty_project")
        os.makedirs(empty_dir)
        
        try:
            self.detector.detect(empty_dir, "empty_project")
        except Exception as e:
            self.fail(f"空项目处理失败: {str(e)}")
            
        # 测试无效文件
        invalid_dir = os.path.join(self.work_dir, "input/invalid_project")
        os.makedirs(invalid_dir)
        with open(os.path.join(invalid_dir, "invalid.cpp"), 'w') as f:
            f.write("This is not valid C++ code")
            
        try:
            self.detector.detect(invalid_dir, "invalid_project")
        except Exception as e:
            self.fail(f"无效文件处理失败: {str(e)}")
            
    def test_performance(self):
        """性能测试"""
        import time
        
        # 创建大型测试项目
        large_project_dir = os.path.join(self.work_dir, "input/large_project/src")
        os.makedirs(large_project_dir)
        
        # 生成多个源文件
        for i in range(100):
            with open(os.path.join(large_project_dir, f"file{i}.cpp"), 'w') as f:
                f.write(f"""
                    int func{i}(int x) {{
                        return x * {i};
                    }}
                """)
                
        # 测量处理时间
        start_time = time.time()
        
        self.preprocessor.run()
        self.detector.detect(
            os.path.join(self.work_dir, "input/large_project"),
            "large_project"
        )
        
        duration = time.time() - start_time
        
        # 验证性能
        self.assertLess(duration, 60)  # 应该在60秒内完成
        
if __name__ == '__main__':
    unittest.main() 