"""代码克隆检测器

该模块实现了改进的代码克隆检测算法。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import os
import logging
from typing import Dict, List, Tuple, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import tlsh
from concurrent.futures import ThreadPoolExecutor
from .ast_analyzer import ASTAnalyzer
from .semantic_analyzer import SemanticAnalyzer
from .metrics import CloneMetrics

class CloneDetector:
    """改进的代码克隆检测器类"""
    
    def __init__(self, config: Dict = None):
        """初始化克隆检测器
        
        参数:
            config: 配置参数字典
        """
        self.config = config or {}
        self.ast_analyzer = ASTAnalyzer()
        self.semantic_analyzer = SemanticAnalyzer()
        self.metrics = CloneMetrics()
        
        # 配置参数
        self.min_token_length = self.config.get('min_token_length', 50)
        self.tlsh_threshold = self.config.get('tlsh_threshold', 120)
        self.ast_threshold = self.config.get('ast_threshold', 0.8)
        self.semantic_threshold = self.config.get('semantic_threshold', 0.7)
        
        # TF-IDF向量化器
        self.vectorizer = TfidfVectorizer(
            tokenizer=self._tokenize,
            stop_words='english',
            ngram_range=(1, 3)
        )
        
        # 缓存
        self._cache = {}
        
    def detect_clones(self, source_files: List[str]) -> List[Dict]:
        """检测代码克隆
        
        参数:
            source_files: 源代码文件列表
            
        返回:
            克隆对列表，每个克隆对包含相似度信息
        """
        clones = []
        try:
            # 并行处理文件
            with ThreadPoolExecutor() as executor:
                # 计算所有文件的特征
                file_features = list(executor.map(
                    self._extract_features,
                    source_files
                ))
                
                # 两两比较文件
                for i, file1 in enumerate(source_files):
                    for j, file2 in enumerate(source_files[i+1:], i+1):
                        similarity = self._compare_files(
                            file1, file2,
                            file_features[i],
                            file_features[j]
                        )
                        
                        if similarity['overall'] >= self.config.get('min_similarity', 0.8):
                            clones.append({
                                'file1': file1,
                                'file2': file2,
                                'similarity': similarity
                            })
                            
        except Exception as e:
            logging.error(f"检测克隆时出错: {e}")
            
        return clones
        
    def _extract_features(self, file_path: str) -> Dict:
        """提取文件特征
        
        参数:
            file_path: 文件路径
            
        返回:
            特征字典
        """
        if file_path in self._cache:
            return self._cache[file_path]
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            features = {
                'content': content,
                'tlsh_hash': self._compute_tlsh(content),
                'ast': self.ast_analyzer.parse(content),
                'tokens': self._tokenize(content),
                'semantic_features': self.semantic_analyzer.extract_features(content)
            }
            
            self._cache[file_path] = features
            return features
            
        except Exception as e:
            logging.error(f"提取特征时出错 {file_path}: {e}")
            return {}
            
    def _compare_files(
        self,
        file1: str,
        file2: str,
        features1: Dict,
        features2: Dict
    ) -> Dict[str, float]:
        """比较两个文件的相似度
        
        参数:
            file1: 第一个文件路径
            file2: 第二个文件路径
            features1: 第一个文件的特征
            features2: 第二个文件的特征
            
        返回:
            相似度指标字典
        """
        try:
            # TLSH相似度
            tlsh_sim = self._compute_tlsh_similarity(
                features1['tlsh_hash'],
                features2['tlsh_hash']
            )
            
            # AST相似度
            ast_sim = self.ast_analyzer.compare(
                features1['ast'],
                features2['ast']
            )
            
            # 语义相似度
            semantic_sim = self.semantic_analyzer.compare(
                features1['semantic_features'],
                features2['semantic_features']
            )
            
            # 令牌相似度
            token_sim = self._compute_token_similarity(
                features1['tokens'],
                features2['tokens']
            )
            
            # 计算加权平均相似度
            weights = self.config.get('similarity_weights', {
                'tlsh': 0.3,
                'ast': 0.3,
                'semantic': 0.2,
                'token': 0.2
            })
            
            overall_sim = (
                tlsh_sim * weights['tlsh'] +
                ast_sim * weights['ast'] +
                semantic_sim * weights['semantic'] +
                token_sim * weights['token']
            )
            
            return {
                'tlsh': tlsh_sim,
                'ast': ast_sim,
                'semantic': semantic_sim,
                'token': token_sim,
                'overall': overall_sim
            }
            
        except Exception as e:
            logging.error(f"比较文件时出错 {file1} vs {file2}: {e}")
            return {
                'tlsh': 0.0,
                'ast': 0.0,
                'semantic': 0.0,
                'token': 0.0,
                'overall': 0.0
            }
            
    def _compute_tlsh(self, content: str) -> str:
        """计算TLSH哈希
        
        参数:
            content: 代码内容
            
        返回:
            TLSH哈希值
        """
        try:
            if len(content) < self.min_token_length:
                return ""
            return tlsh.hash(content.encode())
        except:
            return ""
            
    def _compute_tlsh_similarity(self, hash1: str, hash2: str) -> float:
        """计算TLSH相似度
        
        参数:
            hash1: 第一个哈希值
            hash2: 第二个哈希值
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if not (hash1 and hash2):
                return 0.0
            
            # TLSH距离转换为相似度分数
            distance = tlsh.diff(hash1, hash2)
            return max(0.0, 1.0 - (distance / self.tlsh_threshold))
            
        except:
            return 0.0
            
    def _tokenize(self, content: str) -> List[str]:
        """分词处理
        
        参数:
            content: 代码内容
            
        返回:
            标记列表
        """
        # 实现基本的代码分词
        # 可以根据具体编程语言扩展
        tokens = []
        try:
            # 移除注释和字符串字面量
            content = self._preprocess_code(content)
            
            # 分词
            current_token = []
            for char in content:
                if char.isalnum() or char == '_':
                    current_token.append(char)
                else:
                    if current_token:
                        tokens.append(''.join(current_token))
                        current_token = []
                    if not char.isspace():
                        tokens.append(char)
                        
            if current_token:
                tokens.append(''.join(current_token))
                
        except Exception as e:
            logging.error(f"分词时出错: {e}")
            
        return tokens
        
    def _compute_token_similarity(
        self,
        tokens1: List[str],
        tokens2: List[str]
    ) -> float:
        """计算标记相似度
        
        参数:
            tokens1: 第一个标记列表
            tokens2: 第二个标记列表
            
        返回:
            相似度分数 [0,1]
        """
        try:
            # 使用TF-IDF和余弦相似度
            vectors = self.vectorizer.fit_transform([
                ' '.join(tokens1),
                ' '.join(tokens2)
            ])
            similarity = cosine_similarity(vectors)[0][1]
            return float(similarity)
            
        except Exception as e:
            logging.error(f"计算标记相似度时出错: {e}")
            return 0.0
            
    def _preprocess_code(self, content: str) -> str:
        """预处理代码
        
        参数:
            content: 原始代码内容
            
        返回:
            预处理后的代码
        """
        try:
            # 移除注释
            # 这里需要根据具体编程语言扩展
            lines = []
            in_comment = False
            
            for line in content.split('\n'):
                # 移除单行注释
                if '//' in line:
                    line = line[:line.index('//')]
                    
                # 处理多行注释
                while '/*' in line and '*/' in line[line.index('/*'):]:
                    start = line.index('/*')
                    end = line.index('*/', start) + 2
                    line = line[:start] + line[end:]
                    
                if '/*' in line:
                    in_comment = True
                    line = line[:line.index('/*')]
                elif '*/' in line:
                    in_comment = False
                    line = line[line.index('*/') + 2:]
                elif in_comment:
                    continue
                    
                if line.strip():
                    lines.append(line)
                    
            return '\n'.join(lines)
            
        except Exception as e:
            logging.error(f"预处理代码时出错: {e}")
            return content
            
    def analyze_clone_patterns(self, clones: List[Dict]) -> Dict:
        """分析克隆模式
        
        参数:
            clones: 克隆对列表
            
        返回:
            克隆模式分析结果
        """
        try:
            return self.metrics.analyze_patterns(clones)
        except Exception as e:
            logging.error(f"分析克隆模式时出错: {e}")
            return {} 