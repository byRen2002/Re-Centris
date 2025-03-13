"""Java语言处理器

该模块实现了Java代码的解析和处理功能。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import os
import re
import ast
import javalang
from typing import Dict, List, Tuple, Optional
import logging

class JavaProcessor:
    """Java代码处理器类"""
    
    def __init__(self):
        """初始化Java处理器"""
        self.method_pattern = re.compile(
            r'(?:public|private|protected|static|\s) +[\w\<\>\[\]]+\s+(\w+) *\([^\)]*\) *\{?[^\{]*$'
        )
        
    def extract_methods(self, file_path: str) -> List[Dict[str, str]]:
        """提取Java文件中的方法
        
        参数:
            file_path: Java文件路径
            
        返回:
            方法列表，每个方法包含名称、内容、起始行等信息
        """
        methods = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 使用javalang解析Java代码
            tree = javalang.parse.parse(content)
            
            for _, node in tree.filter(javalang.tree.MethodDeclaration):
                method = {
                    'name': node.name,
                    'content': self._get_method_content(content, node),
                    'start_line': node.position.line if node.position else 0,
                    'modifiers': [str(mod) for mod in node.modifiers],
                    'return_type': self._get_return_type(node),
                    'parameters': self._get_parameters(node)
                }
                methods.append(method)
                
        except Exception as e:
            logging.error(f"处理Java文件 {file_path} 时出错: {e}")
            
        return methods
        
    def _get_method_content(self, content: str, node: javalang.tree.MethodDeclaration) -> str:
        """获取方法的完整内容"""
        try:
            lines = content.splitlines()
            start_line = node.position.line - 1
            
            # 找到方法体的结束位置
            end_line = start_line
            brace_count = 0
            found_first_brace = False
            
            for i, line in enumerate(lines[start_line:], start_line):
                if '{' in line:
                    brace_count += line.count('{')
                    found_first_brace = True
                if '}' in line:
                    brace_count -= line.count('}')
                    
                if found_first_brace and brace_count == 0:
                    end_line = i
                    break
                    
            return '\n'.join(lines[start_line:end_line + 1])
            
        except Exception as e:
            logging.error(f"提取方法内容时出错: {e}")
            return ""
            
    def _get_return_type(self, node: javalang.tree.MethodDeclaration) -> str:
        """获取方法返回类型"""
        try:
            return str(node.return_type.name) if node.return_type else "void"
        except:
            return "void"
            
    def _get_parameters(self, node: javalang.tree.MethodDeclaration) -> List[Dict[str, str]]:
        """获取方法参数列表"""
        params = []
        try:
            for param in node.parameters:
                params.append({
                    'name': param.name,
                    'type': str(param.type.name)
                })
        except:
            pass
        return params
        
    def analyze_complexity(self, method_content: str) -> Dict[str, int]:
        """分析方法的复杂度
        
        参数:
            method_content: 方法内容
            
        返回:
            包含圈复杂度、认知复杂度等指标的字典
        """
        metrics = {
            'cyclomatic_complexity': 1,  # 基础复杂度为1
            'cognitive_complexity': 0,
            'nesting_depth': 0
        }
        
        try:
            # 计算圈复杂度
            metrics['cyclomatic_complexity'] += (
                method_content.count('if ') +
                method_content.count('while ') +
                method_content.count('for ') +
                method_content.count('case ') +
                method_content.count('catch ') +
                method_content.count('&&') +
                method_content.count('||')
            )
            
            # 计算嵌套深度
            current_depth = 0
            max_depth = 0
            
            for line in method_content.split('\n'):
                if '{' in line:
                    current_depth += 1
                    max_depth = max(max_depth, current_depth)
                if '}' in line:
                    current_depth -= 1
                    
            metrics['nesting_depth'] = max_depth
            
            # 计算认知复杂度
            metrics['cognitive_complexity'] = (
                metrics['cyclomatic_complexity'] +
                metrics['nesting_depth']
            )
            
        except Exception as e:
            logging.error(f"分析方法复杂度时出错: {e}")
            
        return metrics
        
    def extract_class_info(self, file_path: str) -> Dict[str, any]:
        """提取类信息
        
        参数:
            file_path: Java文件路径
            
        返回:
            包含类名、包名、导入等信息的字典
        """
        class_info = {
            'name': '',
            'package': '',
            'imports': [],
            'extends': None,
            'implements': [],
            'modifiers': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            tree = javalang.parse.parse(content)
            
            # 获取包名
            if tree.package:
                class_info['package'] = str(tree.package.name)
                
            # 获取导入
            class_info['imports'] = [
                str(imp.path) for imp in tree.imports
            ]
            
            # 获取类信息
            for path, node in tree.filter(javalang.tree.ClassDeclaration):
                class_info['name'] = node.name
                class_info['modifiers'] = [str(mod) for mod in node.modifiers]
                
                if node.extends:
                    class_info['extends'] = str(node.extends.name)
                    
                if node.implements:
                    class_info['implements'] = [
                        str(impl.name) for impl in node.implements
                    ]
                break  # 只处理第一个类
                
        except Exception as e:
            logging.error(f"提取类信息时出错: {e}")
            
        return class_info
        
    def get_method_signature(self, method: Dict[str, str]) -> str:
        """生成方法签名
        
        参数:
            method: 方法信息字典
            
        返回:
            标准化的方法签名
        """
        try:
            modifiers = ' '.join(method.get('modifiers', []))
            return_type = method.get('return_type', 'void')
            name = method.get('name', '')
            
            params = []
            for param in method.get('parameters', []):
                params.append(f"{param['type']} {param['name']}")
                
            signature = f"{modifiers} {return_type} {name}({', '.join(params)})"
            return signature.strip()
            
        except Exception as e:
            logging.error(f"生成方法签名时出错: {e}")
            return ""
            
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
            
            return code.strip()
            
        except Exception as e:
            logging.error(f"规范化代码时出错: {e}")
            return code 