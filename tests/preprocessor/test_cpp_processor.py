"""C++处理器测试模块

该模块包含了对CppProcessor类的单元测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import os
import tempfile
import shutil
from preprocessor.language_processors.cpp_processor import CppProcessor

class TestCppProcessor(unittest.TestCase):
    """CppProcessor类的测试用例"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.processor = CppProcessor()
        self.temp_dir = tempfile.mkdtemp()
        
        # 创建测试C++文件
        self.test_file = os.path.join(self.temp_dir, "test_class.cpp")
        self._create_test_file()
        
    def tearDown(self):
        """测试后的清理工作"""
        shutil.rmtree(self.temp_dir)
        
    def _create_test_file(self):
        """创建测试C++文件"""
        test_code = '''
#include <iostream>
#include <string>
#include <vector>

template<typename T>
class TestClass : public BaseClass {
private:
    std::string name;
    int age;
    static const int MAX_SIZE = 100;
    
public:
    TestClass(const std::string& name, int age)
        : name(name), age(age) {}
        
    virtual ~TestClass() {}
    
    std::string getName() const {
        return name;
    }
    
    void setName(const std::string& name) {
        this->name = name;
    }
    
    int calculateComplexity(int n) {
        int result = 0;
        if (n > 0) {
            for (int i = 0; i < n; i++) {
                if (i % 2 == 0) {
                    result += i;
                } else {
                    result -= i;
                }
                while (result > 100) {
                    result /= 2;
                }
            }
        }
        return result;
    }
    
    virtual std::vector<T> processItems(const std::vector<T>& items) {
        std::vector<T> results;
        for (const auto& item : items) {
            if (item) {
                results.push_back(item);
            }
        }
        return results;
    }
    
protected:
    virtual void abstractMethod() = 0;
};
'''
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write(test_code)
            
    def test_extract_functions(self):
        """测试函数提取"""
        functions = self.processor.extract_functions(self.test_file)
        
        # 验证函数数量
        self.assertEqual(len(functions), 6)  # 构造函数、析构函数和4个方法
        
        # 验证函数名称
        function_names = [f['name'] for f in functions]
        expected_names = [
            'TestClass',  # 构造函数
            '~TestClass',  # 析构函数
            'getName',
            'setName',
            'calculateComplexity',
            'processItems'
        ]
        self.assertEqual(sorted(function_names), sorted(expected_names))
        
        # 验证函数属性
        for function in functions:
            self.assertIn('name', function)
            self.assertIn('content', function)
            self.assertIn('start_line', function)
            self.assertIn('end_line', function)
            self.assertIn('return_type', function)
            self.assertIn('parameters', function)
            self.assertIn('is_method', function)
            self.assertIn('access_specifier', function)
            self.assertIn('is_const', function)
            self.assertIn('is_virtual', function)
            
    def test_function_content(self):
        """测试函数内容提取"""
        functions = self.processor.extract_functions(self.test_file)
        
        # 找到calculateComplexity方法
        complex_function = next(
            f for f in functions if f['name'] == 'calculateComplexity'
        )
        
        # 验证函数内容
        self.assertIn('if (n > 0)', complex_function['content'])
        self.assertIn('for (int i = 0', complex_function['content'])
        self.assertIn('while (result > 100)', complex_function['content'])
        
    def test_parameters(self):
        """测试参数提取"""
        functions = self.processor.extract_functions(self.test_file)
        
        # 验证setName方法的参数
        set_name = next(f for f in functions if f['name'] == 'setName')
        self.assertEqual(len(set_name['parameters']), 1)
        param = set_name['parameters'][0]
        self.assertEqual(param['name'], 'name')
        self.assertEqual(param['type'], 'std::string')
        self.assertTrue(param['is_const'])
        self.assertTrue(param['is_reference'])
        
    def test_class_info(self):
        """测试类信息提取"""
        classes = self.processor.extract_class_info(self.test_file)
        
        # 验证类数量
        self.assertEqual(len(classes), 1)
        
        # 验证类信息
        test_class = classes[0]
        self.assertEqual(test_class['name'], 'TestClass')
        
        # 验证基类
        self.assertEqual(len(test_class['bases']), 1)
        self.assertEqual(test_class['bases'][0]['name'], 'BaseClass')
        
        # 验证方法
        methods = test_class['methods']
        self.assertEqual(len(methods), 6)  # 包括纯虚函数
        
        # 验证字段
        fields = test_class['fields']
        self.assertEqual(len(fields), 3)  # name, age, MAX_SIZE
        
        # 验证是否为抽象类
        self.assertTrue(test_class['is_abstract'])
        
        # 验证模板参数
        self.assertEqual(test_class['template_parameters'], ['T'])
        
    def test_complexity_analysis(self):
        """测试复杂度分析"""
        functions = self.processor.extract_functions(self.test_file)
        
        # 分析calculateComplexity方法的复杂度
        complex_function = next(
            f for f in functions if f['name'] == 'calculateComplexity'
        )
        metrics = self.processor.analyze_complexity(complex_function['content'])
        
        # 验证复杂度指标
        self.assertGreater(metrics['cyclomatic_complexity'], 1)
        self.assertGreater(metrics['cognitive_complexity'], 0)
        self.assertGreater(metrics['nesting_depth'], 1)
        self.assertEqual(metrics['essential_complexity'], 1)  # 没有goto等语句
        
    def test_code_normalization(self):
        """测试代码规范化"""
        test_code = '''
        #include <iostream>
        #define MAX_SIZE 100
        
        int main() {
            // This is a comment
            std::string name = "test";  /* Another comment */
            int value = 42;
            if (value > 0) {
                std::cout << "Positive" << std::endl;
            }
            return 0;
        }
        '''
        
        normalized = self.processor.normalize_code(test_code)
        
        # 验证规范化结果
        self.assertNotIn('//', normalized)  # 注释被移除
        self.assertNotIn('/*', normalized)  # 多行注释被移除
        self.assertNotIn('  ', normalized)  # 多余空格被移除
        self.assertIn('#include <...>', normalized)  # include指令被规范化
        self.assertIn('#define ...', normalized)  # define指令被规范化
        self.assertNotIn('42', normalized)  # 数字被规范化
        self.assertEqual(normalized.count('"'), 2)  # 字符串被规范化
        
    def test_function_signature(self):
        """测试函数签名生成"""
        functions = self.processor.extract_functions(self.test_file)
        
        # 验证不同函数的签名
        for function in functions:
            signature = self.processor.get_function_signature(function)
            self.assertIsInstance(signature, str)
            self.assertGreater(len(signature), 0)
            
            if function['name'] == 'getName':
                self.assertIn('std::string getName() const', signature)
            elif function['name'] == 'processItems':
                self.assertIn('virtual', signature)
                self.assertIn('std::vector<T>', signature)
                
    def test_error_handling(self):
        """测试错误处理"""
        # 测试处理不存在的文件
        functions = self.processor.extract_functions("nonexistent.cpp")
        self.assertEqual(len(functions), 0)
        
        # 测试处理无效的C++代码
        invalid_file = os.path.join(self.temp_dir, "invalid.cpp")
        with open(invalid_file, 'w') as f:
            f.write("invalid c++ code")
            
        functions = self.processor.extract_functions(invalid_file)
        self.assertEqual(len(functions), 0)
        
    def test_large_file(self):
        """测试处理大文件"""
        # 创建包含多个函数的大文件
        large_file = os.path.join(self.temp_dir, "large_class.cpp")
        with open(large_file, 'w') as f:
            f.write("#include <iostream>\n\nclass LargeClass {\npublic:\n")
            for i in range(100):
                f.write(f'''
                    void method{i}() {{
                        std::cout << "Method {i}" << std::endl;
                    }}
                ''')
            f.write("};\n")
            
        # 验证能够处理大文件
        functions = self.processor.extract_functions(large_file)
        self.assertEqual(len(functions), 100)

if __name__ == '__main__':
    unittest.main() 