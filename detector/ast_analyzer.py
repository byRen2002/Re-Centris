"""AST分析器

该模块实现了基于抽象语法树的代码分析功能。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import ast
import logging
from typing import Dict, List, Optional, Set, Tuple
import javalang
import clang.cindex
from clang.cindex import CursorKind

class ASTAnalyzer:
    """AST分析器类"""
    
    def __init__(self):
        """初始化AST分析器"""
        self.supported_languages = {
            '.py': self._parse_python,
            '.java': self._parse_java,
            '.cpp': self._parse_cpp,
            '.hpp': self._parse_cpp,
            '.c': self._parse_cpp,
            '.h': self._parse_cpp
        }
        
    def parse(self, content: str, file_ext: str = '.py') -> Dict:
        """解析代码生成AST
        
        参数:
            content: 代码内容
            file_ext: 文件扩展名
            
        返回:
            AST信息字典
        """
        try:
            parser = self.supported_languages.get(file_ext, self._parse_python)
            return parser(content)
        except Exception as e:
            logging.error(f"解析AST时出错: {e}")
            return {}
            
    def compare(self, ast1: Dict, ast2: Dict) -> float:
        """比较两个AST的相似度
        
        参数:
            ast1: 第一个AST
            ast2: 第二个AST
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if not (ast1 and ast2):
                return 0.0
                
            # 计算结构相似度
            struct_sim = self._compare_structure(
                ast1.get('structure', {}),
                ast2.get('structure', {})
            )
            
            # 计算类型相似度
            type_sim = self._compare_types(
                ast1.get('types', []),
                ast2.get('types', [])
            )
            
            # 计算控制流相似度
            flow_sim = self._compare_control_flow(
                ast1.get('control_flow', []),
                ast2.get('control_flow', [])
            )
            
            # 加权平均
            weights = {
                'structure': 0.4,
                'types': 0.3,
                'control_flow': 0.3
            }
            
            return (
                struct_sim * weights['structure'] +
                type_sim * weights['types'] +
                flow_sim * weights['control_flow']
            )
            
        except Exception as e:
            logging.error(f"比较AST时出错: {e}")
            return 0.0
            
    def _parse_python(self, content: str) -> Dict:
        """解析Python代码
        
        参数:
            content: Python代码内容
            
        返回:
            AST信息字典
        """
        try:
            tree = ast.parse(content)
            
            # 提取结构信息
            structure = self._extract_python_structure(tree)
            
            # 提取类型信息
            types = self._extract_python_types(tree)
            
            # 提取控制流信息
            control_flow = self._extract_python_control_flow(tree)
            
            return {
                'structure': structure,
                'types': types,
                'control_flow': control_flow
            }
            
        except Exception as e:
            logging.error(f"解析Python代码时出错: {e}")
            return {}
            
    def _parse_java(self, content: str) -> Dict:
        """解析Java代码
        
        参数:
            content: Java代码内容
            
        返回:
            AST信息字典
        """
        try:
            tree = javalang.parse.parse(content)
            
            # 提取结构信息
            structure = self._extract_java_structure(tree)
            
            # 提取类型信息
            types = self._extract_java_types(tree)
            
            # 提取控制流信息
            control_flow = self._extract_java_control_flow(tree)
            
            return {
                'structure': structure,
                'types': types,
                'control_flow': control_flow
            }
            
        except Exception as e:
            logging.error(f"解析Java代码时出错: {e}")
            return {}
            
    def _parse_cpp(self, content: str) -> Dict:
        """解析C++代码
        
        参数:
            content: C++代码内容
            
        返回:
            AST信息字典
        """
        try:
            index = clang.cindex.Index.create()
            tu = index.parse('tmp.cpp', 
                           unsaved_files=[('tmp.cpp', content)],
                           args=['-std=c++17'])
            
            # 提取结构信息
            structure = self._extract_cpp_structure(tu.cursor)
            
            # 提取类型信息
            types = self._extract_cpp_types(tu.cursor)
            
            # 提取控制流信息
            control_flow = self._extract_cpp_control_flow(tu.cursor)
            
            return {
                'structure': structure,
                'types': types,
                'control_flow': control_flow
            }
            
        except Exception as e:
            logging.error(f"解析C++代码时出错: {e}")
            return {}
            
    def _extract_python_structure(self, tree: ast.AST) -> Dict:
        """提取Python代码结构
        
        参数:
            tree: Python AST
            
        返回:
            结构信息字典
        """
        structure = {
            'classes': [],
            'functions': [],
            'imports': [],
            'assignments': []
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                structure['classes'].append({
                    'name': node.name,
                    'bases': [base.id for base in node.bases 
                            if isinstance(base, ast.Name)],
                    'methods': [m.name for m in node.body 
                              if isinstance(m, ast.FunctionDef)]
                })
            elif isinstance(node, ast.FunctionDef):
                structure['functions'].append({
                    'name': node.name,
                    'args': [arg.arg for arg in node.args.args],
                    'returns': self._get_return_type(node)
                })
            elif isinstance(node, ast.Import):
                structure['imports'].extend(
                    alias.name for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                structure['imports'].append(
                    f"{node.module}.{node.names[0].name}"
                )
            elif isinstance(node, ast.Assign):
                structure['assignments'].append(
                    self._get_assignment_info(node)
                )
                
        return structure
        
    def _extract_java_structure(self, tree) -> Dict:
        """提取Java代码结构
        
        参数:
            tree: Java AST
            
        返回:
            结构信息字典
        """
        structure = {
            'classes': [],
            'methods': [],
            'imports': [],
            'fields': []
        }
        
        for path, node in tree.filter(javalang.tree.ClassDeclaration):
            class_info = {
                'name': node.name,
                'extends': node.extends.name if node.extends else None,
                'implements': [i.name for i in node.implements],
                'modifiers': node.modifiers
            }
            structure['classes'].append(class_info)
            
        for path, node in tree.filter(javalang.tree.MethodDeclaration):
            method_info = {
                'name': node.name,
                'return_type': str(node.return_type),
                'parameters': [
                    (param.type.name, param.name)
                    for param in node.parameters
                ],
                'modifiers': node.modifiers
            }
            structure['methods'].append(method_info)
            
        for path, node in tree.filter(javalang.tree.Import):
            structure['imports'].append(node.path)
            
        for path, node in tree.filter(javalang.tree.FieldDeclaration):
            for declarator in node.declarators:
                field_info = {
                    'name': declarator.name,
                    'type': node.type.name,
                    'modifiers': node.modifiers
                }
                structure['fields'].append(field_info)
                
        return structure
        
    def _extract_cpp_structure(self, cursor: clang.cindex.Cursor) -> Dict:
        """提取C++代码结构
        
        参数:
            cursor: C++ AST游标
            
        返回:
            结构信息字典
        """
        structure = {
            'classes': [],
            'functions': [],
            'namespaces': [],
            'variables': []
        }
        
        def visit(cursor, parent):
            if cursor.kind == CursorKind.CLASS_DECL:
                class_info = {
                    'name': cursor.spelling,
                    'methods': [],
                    'fields': [],
                    'bases': []
                }
                
                for c in cursor.get_children():
                    if c.kind == CursorKind.CXX_METHOD:
                        class_info['methods'].append(c.spelling)
                    elif c.kind == CursorKind.FIELD_DECL:
                        class_info['fields'].append(c.spelling)
                    elif c.kind == CursorKind.CXX_BASE_SPECIFIER:
                        class_info['bases'].append(c.spelling)
                        
                structure['classes'].append(class_info)
                
            elif cursor.kind in [
                CursorKind.FUNCTION_DECL,
                CursorKind.CXX_METHOD
            ]:
                function_info = {
                    'name': cursor.spelling,
                    'return_type': cursor.result_type.spelling,
                    'parameters': [
                        (c.spelling, c.type.spelling)
                        for c in cursor.get_arguments()
                    ]
                }
                structure['functions'].append(function_info)
                
            elif cursor.kind == CursorKind.NAMESPACE:
                structure['namespaces'].append(cursor.spelling)
                
            elif cursor.kind == CursorKind.VAR_DECL:
                structure['variables'].append({
                    'name': cursor.spelling,
                    'type': cursor.type.spelling
                })
                
            for child in cursor.get_children():
                visit(child, cursor)
                
        visit(cursor, None)
        return structure
        
    def _extract_python_types(self, tree: ast.AST) -> List[str]:
        """提取Python代码类型信息
        
        参数:
            tree: Python AST
            
        返回:
            类型列表
        """
        types = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and node.annotation:
                if isinstance(node.annotation, ast.Name):
                    types.add(node.annotation.id)
                elif isinstance(node.annotation, ast.Subscript):
                    types.add(node.annotation.value.id)
                    
        return list(types)
        
    def _extract_java_types(self, tree) -> List[str]:
        """提取Java代码类型信息
        
        参数:
            tree: Java AST
            
        返回:
            类型列表
        """
        types = set()
        
        for path, node in tree.filter(javalang.tree.ReferenceType):
            types.add(node.name)
            
        for path, node in tree.filter(javalang.tree.BasicType):
            types.add(node.name)
            
        return list(types)
        
    def _extract_cpp_types(self, cursor: clang.cindex.Cursor) -> List[str]:
        """提取C++代码类型信息
        
        参数:
            cursor: C++ AST游标
            
        返回:
            类型列表
        """
        types = set()
        
        def visit(cursor):
            if cursor.kind in [
                CursorKind.TYPE_REF,
                CursorKind.INTEGER_LITERAL,
                CursorKind.FLOATING_LITERAL,
                CursorKind.CHARACTER_LITERAL,
                CursorKind.STRING_LITERAL
            ]:
                types.add(cursor.type.spelling)
                
            for child in cursor.get_children():
                visit(child)
                
        visit(cursor)
        return list(types)
        
    def _extract_python_control_flow(self, tree: ast.AST) -> List[str]:
        """提取Python代码控制流信息
        
        参数:
            tree: Python AST
            
        返回:
            控制流列表
        """
        control_flow = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While)):
                control_flow.append(node.__class__.__name__)
            elif isinstance(node, ast.Try):
                control_flow.append('Try')
                for handler in node.handlers:
                    control_flow.append('Except')
                if node.finalbody:
                    control_flow.append('Finally')
                    
        return control_flow
        
    def _extract_java_control_flow(self, tree) -> List[str]:
        """提取Java代码控制流信息
        
        参数:
            tree: Java AST
            
        返回:
            控制流列表
        """
        control_flow = []
        
        for path, node in tree.filter(javalang.tree.IfStatement):
            control_flow.append('If')
        for path, node in tree.filter(javalang.tree.ForStatement):
            control_flow.append('For')
        for path, node in tree.filter(javalang.tree.WhileStatement):
            control_flow.append('While')
        for path, node in tree.filter(javalang.tree.TryStatement):
            control_flow.append('Try')
            
        return control_flow
        
    def _extract_cpp_control_flow(self, cursor: clang.cindex.Cursor) -> List[str]:
        """提取C++代码控制流信息
        
        参数:
            cursor: C++ AST游标
            
        返回:
            控制流列表
        """
        control_flow = []
        
        def visit(cursor):
            if cursor.kind == CursorKind.IF_STMT:
                control_flow.append('If')
            elif cursor.kind == CursorKind.FOR_STMT:
                control_flow.append('For')
            elif cursor.kind == CursorKind.WHILE_STMT:
                control_flow.append('While')
            elif cursor.kind == CursorKind.DO_STMT:
                control_flow.append('Do')
            elif cursor.kind == CursorKind.SWITCH_STMT:
                control_flow.append('Switch')
                
            for child in cursor.get_children():
                visit(child)
                
        visit(cursor)
        return control_flow
        
    def _compare_structure(self, struct1: Dict, struct2: Dict) -> float:
        """比较代码结构相似度
        
        参数:
            struct1: 第一个结构字典
            struct2: 第二个结构字典
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if not (struct1 and struct2):
                return 0.0
                
            # 计算各个结构元素的Jaccard相似度
            similarities = []
            
            for key in struct1.keys():
                if key in struct2:
                    set1 = set(str(x) for x in struct1[key])
                    set2 = set(str(x) for x in struct2[key])
                    
                    if set1 or set2:
                        similarity = len(set1 & set2) / len(set1 | set2)
                        similarities.append(similarity)
                        
            return sum(similarities) / len(similarities) if similarities else 0.0
            
        except Exception as e:
            logging.error(f"比较代码结构时出错: {e}")
            return 0.0
            
    def _compare_types(self, types1: List[str], types2: List[str]) -> float:
        """比较类型相似度
        
        参数:
            types1: 第一个类型列表
            types2: 第二个类型列表
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if not (types1 and types2):
                return 0.0
                
            set1 = set(types1)
            set2 = set(types2)
            
            return len(set1 & set2) / len(set1 | set2)
            
        except Exception as e:
            logging.error(f"比较类型时出错: {e}")
            return 0.0
            
    def _compare_control_flow(
        self,
        flow1: List[str],
        flow2: List[str]
    ) -> float:
        """比较控制流相似度
        
        参数:
            flow1: 第一个控制流列表
            flow2: 第二个控制流列表
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if not (flow1 and flow2):
                return 0.0
                
            # 计算控制流序列的最长公共子序列
            m, n = len(flow1), len(flow2)
            dp = [[0] * (n + 1) for _ in range(m + 1)]
            
            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    if flow1[i-1] == flow2[j-1]:
                        dp[i][j] = dp[i-1][j-1] + 1
                    else:
                        dp[i][j] = max(dp[i-1][j], dp[i][j-1])
                        
            lcs_length = dp[m][n]
            return 2 * lcs_length / (m + n)
            
        except Exception as e:
            logging.error(f"比较控制流时出错: {e}")
            return 0.0
            
    def _get_return_type(self, node: ast.FunctionDef) -> Optional[str]:
        """获取Python函数返回类型
        
        参数:
            node: 函数定义节点
            
        返回:
            返回类型字符串
        """
        if node.returns:
            if isinstance(node.returns, ast.Name):
                return node.returns.id
            elif isinstance(node.returns, ast.Subscript):
                return node.returns.value.id
        return None
        
    def _get_assignment_info(self, node: ast.Assign) -> Dict:
        """获取赋值信息
        
        参数:
            node: 赋值节点
            
        返回:
            赋值信息字典
        """
        targets = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                targets.append(target.id)
            elif isinstance(target, ast.Attribute):
                targets.append(f"{target.value.id}.{target.attr}")
                
        return {
            'targets': targets,
            'value_type': node.value.__class__.__name__
        } 