"""Java处理器测试模块

该模块包含了对JavaProcessor类的单元测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import os
import tempfile
import shutil
from preprocessor.language_processors.java_processor import JavaProcessor

class TestJavaProcessor(unittest.TestCase):
    """JavaProcessor类的测试用例"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.processor = JavaProcessor()
        self.temp_dir = tempfile.mkdtemp()
        
        # 创建测试Java文件
        self.test_file = os.path.join(self.temp_dir, "TestClass.java")
        self._create_test_file()
        
    def tearDown(self):
        """测试后的清理工作"""
        shutil.rmtree(self.temp_dir)
        
    def _create_test_file(self):
        """创建测试Java文件"""
        test_code = '''
package com.example.test;

import java.util.List;
import java.util.ArrayList;

public class TestClass extends BaseClass implements TestInterface {
    private String name;
    private int age;
    
    public TestClass(String name, int age) {
        this.name = name;
        this.age = age;
    }
    
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    public int calculateComplexity(int n) {
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
    
    private List<String> processItems(List<String> items) {
        List<String> results = new ArrayList<>();
        for (String item : items) {
            if (item != null && !item.isEmpty()) {
                results.add(item.toUpperCase());
            }
        }
        return results;
    }
}
'''
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write(test_code)
            
    def test_extract_methods(self):
        """测试方法提取"""
        methods = self.processor.extract_methods(self.test_file)
        
        # 验证方法数量
        self.assertEqual(len(methods), 5)  # 构造函数 + 4个方法
        
        # 验证方法名称
        method_names = [m['name'] for m in methods]
        expected_names = [
            'TestClass',  # 构造函数
            'getName',
            'setName',
            'calculateComplexity',
            'processItems'
        ]
        self.assertEqual(sorted(method_names), sorted(expected_names))
        
        # 验证方法属性
        for method in methods:
            self.assertIn('name', method)
            self.assertIn('content', method)
            self.assertIn('start_line', method)
            self.assertIn('modifiers', method)
            self.assertIn('return_type', method)
            self.assertIn('parameters', method)
            
    def test_method_content(self):
        """测试方法内容提取"""
        methods = self.processor.extract_methods(self.test_file)
        
        # 找到calculateComplexity方法
        complex_method = next(
            m for m in methods if m['name'] == 'calculateComplexity'
        )
        
        # 验证方法内容
        self.assertIn('if (n > 0)', complex_method['content'])
        self.assertIn('for (int i = 0', complex_method['content'])
        self.assertIn('while (result > 100)', complex_method['content'])
        
    def test_return_type(self):
        """测试返回类型提取"""
        methods = self.processor.extract_methods(self.test_file)
        
        # 验证不同返回类型
        return_types = {m['name']: m['return_type'] for m in methods}
        self.assertEqual(return_types['getName'], 'String')
        self.assertEqual(return_types['setName'], 'void')
        self.assertEqual(return_types['calculateComplexity'], 'int')
        
    def test_parameters(self):
        """测试参数提取"""
        methods = self.processor.extract_methods(self.test_file)
        
        # 验证构造函数参数
        constructor = next(m for m in methods if m['name'] == 'TestClass')
        self.assertEqual(len(constructor['parameters']), 2)
        self.assertEqual(constructor['parameters'][0]['type'], 'String')
        self.assertEqual(constructor['parameters'][0]['name'], 'name')
        self.assertEqual(constructor['parameters'][1]['type'], 'int')
        self.assertEqual(constructor['parameters'][1]['name'], 'age')
        
    def test_complexity_analysis(self):
        """测试复杂度分析"""
        methods = self.processor.extract_methods(self.test_file)
        
        # 分析calculateComplexity方法的复杂度
        complex_method = next(
            m for m in methods if m['name'] == 'calculateComplexity'
        )
        metrics = self.processor.analyze_complexity(complex_method['content'])
        
        # 验证复杂度指标
        self.assertGreater(metrics['cyclomatic_complexity'], 1)
        self.assertGreater(metrics['cognitive_complexity'], 0)
        self.assertGreater(metrics['nesting_depth'], 1)
        
    def test_class_info(self):
        """测试类信息提取"""
        class_info = self.processor.extract_class_info(self.test_file)
        
        # 验证基本信息
        self.assertEqual(class_info['name'], 'TestClass')
        self.assertEqual(class_info['package'], 'com.example.test')
        
        # 验证继承和实现
        self.assertEqual(class_info['extends'], 'BaseClass')
        self.assertIn('TestInterface', class_info['implements'])
        
        # 验证导入
        self.assertIn('java.util.List', class_info['imports'])
        self.assertIn('java.util.ArrayList', class_info['imports'])
        
    def test_method_signature(self):
        """测试方法签名生成"""
        methods = self.processor.extract_methods(self.test_file)
        
        # 验证不同方法的签名
        for method in methods:
            signature = self.processor.get_method_signature(method)
            self.assertIsInstance(signature, str)
            self.assertGreater(len(signature), 0)
            
            if method['name'] == 'calculateComplexity':
                self.assertIn('public int calculateComplexity(int n)', signature)
                
    def test_code_normalization(self):
        """测试代码规范化"""
        test_code = '''
        public void testMethod() {
            // This is a comment
            String name = "test";  /* Another comment */
            if (name.equals("test")) {
                System.out.println("Hello");
            }
        }
        '''
        
        normalized = self.processor.normalize_code(test_code)
        
        # 验证规范化结果
        self.assertNotIn('//', normalized)  # 注释被移除
        self.assertNotIn('/*', normalized)  # 多行注释被移除
        self.assertNotIn('  ', normalized)  # 多余空格被移除
        self.assertEqual(normalized.count('"'), 2)  # 字符串被规范化
        
    def test_error_handling(self):
        """测试错误处理"""
        # 测试处理不存在的文件
        methods = self.processor.extract_methods("nonexistent.java")
        self.assertEqual(len(methods), 0)
        
        # 测试处理无效的Java代码
        invalid_file = os.path.join(self.temp_dir, "Invalid.java")
        with open(invalid_file, 'w') as f:
            f.write("invalid java code")
            
        methods = self.processor.extract_methods(invalid_file)
        self.assertEqual(len(methods), 0)
        
    def test_large_file(self):
        """测试处理大文件"""
        # 创建包含多个方法的大文件
        large_file = os.path.join(self.temp_dir, "LargeClass.java")
        with open(large_file, 'w') as f:
            f.write("public class LargeClass {\n")
            for i in range(100):
                f.write(f'''
                    public void method{i}() {{
                        System.out.println("Method {i}");
                    }}
                ''')
            f.write("}")
            
        # 验证能够处理大文件
        methods = self.processor.extract_methods(large_file)
        self.assertEqual(len(methods), 100)

if __name__ == '__main__':
    unittest.main() 