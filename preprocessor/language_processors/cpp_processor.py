"""C++语言处理器

该模块实现了C++代码的解析和处理功能。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import os
import re
import logging
from typing import Dict, List, Optional, Set
import clang.cindex
from clang.cindex import CursorKind, TypeKind

class CppProcessor:
    """C++代码处理器类"""
    
    def __init__(self):
        """初始化C++处理器"""
        # 初始化libclang
        clang.cindex.Config.set_library_file('libclang.dll')  # Windows
        self.index = clang.cindex.Index.create()
        
        # 编译标志
        self.compile_flags = [
            '-x', 'c++',  # 强制C++模式
            '-std=c++17',  # 使用C++17标准
            '-I.'  # 包含当前目录
        ]
        
    def extract_functions(self, file_path: str) -> List[Dict[str, any]]:
        """提取C++文件中的函数
        
        参数:
            file_path: C++文件路径
            
        返回:
            函数列表，每个函数包含名称、内容、位置等信息
        """
        functions = []
        try:
            # 解析C++文件
            translation_unit = self.index.parse(
                file_path,
                args=self.compile_flags,
                options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            )
            
            # 遍历AST
            for cursor in translation_unit.cursor.walk_preorder():
                if cursor.kind in [
                    CursorKind.FUNCTION_DECL,
                    CursorKind.CXX_METHOD,
                    CursorKind.CONSTRUCTOR,
                    CursorKind.DESTRUCTOR
                ]:
                    function = {
                        'name': cursor.spelling,
                        'content': self._get_function_content(cursor),
                        'start_line': cursor.extent.start.line,
                        'end_line': cursor.extent.end.line,
                        'return_type': cursor.result_type.spelling,
                        'parameters': self._get_parameters(cursor),
                        'is_method': cursor.kind == CursorKind.CXX_METHOD,
                        'access_specifier': self._get_access_specifier(cursor),
                        'is_const': cursor.is_const_method(),
                        'is_virtual': cursor.is_virtual_method(),
                        'attributes': self._get_attributes(cursor)
                    }
                    functions.append(function)
                    
        except Exception as e:
            logging.error(f"处理C++文件 {file_path} 时出错: {e}")
            
        return functions
        
    def _get_function_content(self, cursor: clang.cindex.Cursor) -> str:
        """获取函数的完整内容"""
        try:
            start = cursor.extent.start
            end = cursor.extent.end
            
            with open(start.file.name, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            return ''.join(lines[start.line-1:end.line])
            
        except Exception as e:
            logging.error(f"提取函数内容时出错: {e}")
            return ""
            
    def _get_parameters(self, cursor: clang.cindex.Cursor) -> List[Dict[str, str]]:
        """获取函数参数列表"""
        params = []
        try:
            for param in cursor.get_arguments():
                params.append({
                    'name': param.spelling,
                    'type': param.type.spelling,
                    'is_const': param.type.is_const_qualified(),
                    'is_reference': param.type.kind == TypeKind.LVALUEREFERENCE,
                    'is_pointer': param.type.kind == TypeKind.POINTER
                })
        except:
            pass
        return params
        
    def _get_access_specifier(self, cursor: clang.cindex.Cursor) -> str:
        """获取访问说明符"""
        try:
            return str(cursor.access_specifier).split('.')[-1].lower()
        except:
            return 'public'  # 默认为public
            
    def _get_attributes(self, cursor: clang.cindex.Cursor) -> List[str]:
        """获取函数属性"""
        attributes = []
        try:
            for child in cursor.get_children():
                if child.kind == CursorKind.ANNOTATE_ATTR:
                    attributes.append(child.spelling)
        except:
            pass
        return attributes
        
    def extract_class_info(self, file_path: str) -> List[Dict[str, any]]:
        """提取类信息
        
        参数:
            file_path: C++文件路径
            
        返回:
            类信息列表，每个类包含名称、基类、成员等信息
        """
        classes = []
        try:
            translation_unit = self.index.parse(
                file_path,
                args=self.compile_flags
            )
            
            for cursor in translation_unit.cursor.walk_preorder():
                if cursor.kind == CursorKind.CLASS_DECL:
                    class_info = {
                        'name': cursor.spelling,
                        'bases': self._get_base_classes(cursor),
                        'methods': self._get_class_methods(cursor),
                        'fields': self._get_class_fields(cursor),
                        'is_abstract': self._is_abstract_class(cursor),
                        'template_parameters': self._get_template_parameters(cursor)
                    }
                    classes.append(class_info)
                    
        except Exception as e:
            logging.error(f"提取类信息时出错: {e}")
            
        return classes
        
    def _get_base_classes(self, cursor: clang.cindex.Cursor) -> List[Dict[str, str]]:
        """获取基类列表"""
        bases = []
        try:
            for child in cursor.get_children():
                if child.kind == CursorKind.CXX_BASE_SPECIFIER:
                    bases.append({
                        'name': child.type.spelling,
                        'access': str(child.access_specifier).split('.')[-1].lower(),
                        'is_virtual': child.is_virtual_base()
                    })
        except:
            pass
        return bases
        
    def _get_class_methods(self, cursor: clang.cindex.Cursor) -> List[Dict[str, any]]:
        """获取类方法列表"""
        methods = []
        try:
            for child in cursor.get_children():
                if child.kind in [
                    CursorKind.CXX_METHOD,
                    CursorKind.CONSTRUCTOR,
                    CursorKind.DESTRUCTOR
                ]:
                    method = {
                        'name': child.spelling,
                        'access': str(child.access_specifier).split('.')[-1].lower(),
                        'is_const': child.is_const_method(),
                        'is_virtual': child.is_virtual_method(),
                        'is_pure_virtual': child.is_pure_virtual_method()
                    }
                    methods.append(method)
        except:
            pass
        return methods
        
    def _get_class_fields(self, cursor: clang.cindex.Cursor) -> List[Dict[str, any]]:
        """获取类成员变量列表"""
        fields = []
        try:
            for child in cursor.get_children():
                if child.kind == CursorKind.FIELD_DECL:
                    field = {
                        'name': child.spelling,
                        'type': child.type.spelling,
                        'access': str(child.access_specifier).split('.')[-1].lower(),
                        'is_const': child.type.is_const_qualified(),
                        'is_static': child.storage_class == 2  # StorageClass.STATIC
                    }
                    fields.append(field)
        except:
            pass
        return fields
        
    def _is_abstract_class(self, cursor: clang.cindex.Cursor) -> bool:
        """判断是否为抽象类"""
        try:
            for method in cursor.get_children():
                if (method.kind == CursorKind.CXX_METHOD and
                    method.is_pure_virtual_method()):
                    return True
            return False
        except:
            return False
            
    def _get_template_parameters(self, cursor: clang.cindex.Cursor) -> List[str]:
        """获取模板参数列表"""
        params = []
        try:
            for child in cursor.get_children():
                if child.kind == CursorKind.TEMPLATE_TYPE_PARAMETER:
                    params.append(child.spelling)
        except:
            pass
        return params
        
    def analyze_complexity(self, function_content: str) -> Dict[str, int]:
        """分析函数的复杂度
        
        参数:
            function_content: 函数内容
            
        返回:
            包含圈复杂度、认知复杂度等指标的字典
        """
        metrics = {
            'cyclomatic_complexity': 1,  # 基础复杂度为1
            'cognitive_complexity': 0,
            'nesting_depth': 0,
            'essential_complexity': 1  # 基础本质复杂度为1
        }
        
        try:
            # 计算圈复杂度
            keywords = [
                'if', 'else', 'for', 'while', 'do', 'switch',
                'case', 'catch', '&&', '||', '?'
            ]
            
            for keyword in keywords:
                metrics['cyclomatic_complexity'] += function_content.count(keyword)
                
            # 计算嵌套深度
            current_depth = 0
            max_depth = 0
            
            for line in function_content.split('\n'):
                if '{' in line:
                    current_depth += 1
                    max_depth = max(max_depth, current_depth)
                if '}' in line:
                    current_depth -= 1
                    
            metrics['nesting_depth'] = max_depth
            
            # 计算认知复杂度
            metrics['cognitive_complexity'] = (
                metrics['cyclomatic_complexity'] +
                metrics['nesting_depth'] * 2  # 嵌套深度权重加倍
            )
            
            # 计算本质复杂度
            unstructured_patterns = [
                'goto', 'break', 'continue'
            ]
            
            for pattern in unstructured_patterns:
                metrics['essential_complexity'] += function_content.count(pattern)
                
        except Exception as e:
            logging.error(f"分析函数复杂度时出错: {e}")
            
        return metrics
        
    def normalize_code(self, code: str) -> str:
        """规范化代码
        
        参数:
            code: 源代码
            
        返回:
            规范化后的代码
        """
        try:
            # 移除注释
            code = re.sub(r'//.*?\n|/\*.*?\*/', '', code, flags=re.DOTALL)
            
            # 移除空行
            code = '\n'.join(
                line for line in code.splitlines()
                if line.strip()
            )
            
            # 规范化空白字符
            code = re.sub(r'\s+', ' ', code)
            
            # 规范化字符串字面量
            code = re.sub(r'"[^"]*"', '""', code)
            code = re.sub(r"'[^']*'", "''", code)
            
            # 规范化数字字面量
            code = re.sub(r'\b\d+\b', '0', code)
            
            # 规范化预处理指令
            code = re.sub(r'#\s*include\s*[<"].*?[>"]', '#include <...>', code)
            code = re.sub(r'#\s*define\s+\w+(\(.*?\))?\s+.*', '#define ...', code)
            
            return code.strip()
            
        except Exception as e:
            logging.error(f"规范化代码时出错: {e}")
            return code
            
    def get_function_signature(self, function: Dict[str, any]) -> str:
        """生成函数签名
        
        参数:
            function: 函数信息字典
            
        返回:
            标准化的函数签名
        """
        try:
            # 构建修饰符
            modifiers = []
            if function.get('is_virtual'):
                modifiers.append('virtual')
            if function.get('is_const'):
                modifiers.append('const')
                
            # 构建参数列表
            params = []
            for param in function.get('parameters', []):
                param_str = ''
                if param.get('is_const'):
                    param_str += 'const '
                param_str += param['type']
                if param.get('is_reference'):
                    param_str += '&'
                elif param.get('is_pointer'):
                    param_str += '*'
                param_str += ' ' + param['name']
                params.append(param_str)
                
            # 组合签名
            signature_parts = [
                ' '.join(modifiers) if modifiers else '',
                function.get('return_type', 'void'),
                function['name'],
                '(' + ', '.join(params) + ')'
            ]
            
            return ' '.join(part for part in signature_parts if part)
            
        except Exception as e:
            logging.error(f"生成函数签名时出错: {e}")
            return "" 