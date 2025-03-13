"""语义分析器

该模块实现了代码语义分析功能。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import re
import logging
from typing import Dict, List, Set, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from gensim.models import Word2Vec
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

class SemanticAnalyzer:
    """语义分析器类"""
    
    def __init__(self):
        """初始化语义分析器"""
        self.vectorizer = TfidfVectorizer(
            tokenizer=self._tokenize,
            stop_words='english',
            ngram_range=(1, 3)
        )
        
        # 词形还原器
        self.lemmatizer = WordNetLemmatizer()
        
        # 停用词
        self.stop_words = set(stopwords.words('english'))
        
        # 标识符分词模式
        self.identifier_pattern = re.compile(r'[A-Z]?[a-z]+|[A-Z]{2,}(?=[A-Z][a-z]|\d|\W|$)|\d+')
        
        # Word2Vec模型
        self.word2vec = None
        
    def extract_features(self, content: str) -> Dict:
        """提取语义特征
        
        参数:
            content: 代码内容
            
        返回:
            特征字典
        """
        try:
            # 标识符提取和分词
            identifiers = self._extract_identifiers(content)
            tokens = self._tokenize_identifiers(identifiers)
            
            # 注释提取
            comments = self._extract_comments(content)
            
            # 字符串字面量提取
            strings = self._extract_strings(content)
            
            # 计算TF-IDF特征
            tfidf_features = self._compute_tfidf_features(
                tokens + self._tokenize(' '.join(comments))
            )
            
            # 计算Word2Vec特征
            w2v_features = self._compute_word2vec_features(tokens)
            
            return {
                'identifiers': identifiers,
                'tokens': tokens,
                'comments': comments,
                'strings': strings,
                'tfidf': tfidf_features,
                'word2vec': w2v_features
            }
            
        except Exception as e:
            logging.error(f"提取语义特征时出错: {e}")
            return {}
            
    def compare(self, features1: Dict, features2: Dict) -> float:
        """比较语义相似度
        
        参数:
            features1: 第一个特征字典
            features2: 第二个特征字典
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if not (features1 and features2):
                return 0.0
                
            # 计算标识符相似度
            identifier_sim = self._compare_identifiers(
                features1.get('identifiers', []),
                features2.get('identifiers', [])
            )
            
            # 计算注释相似度
            comment_sim = self._compare_comments(
                features1.get('comments', []),
                features2.get('comments', [])
            )
            
            # 计算TF-IDF相似度
            tfidf_sim = self._compare_tfidf(
                features1.get('tfidf', []),
                features2.get('tfidf', [])
            )
            
            # 计算Word2Vec相似度
            w2v_sim = self._compare_word2vec(
                features1.get('word2vec', []),
                features2.get('word2vec', [])
            )
            
            # 加权平均
            weights = {
                'identifier': 0.3,
                'comment': 0.2,
                'tfidf': 0.3,
                'word2vec': 0.2
            }
            
            return (
                identifier_sim * weights['identifier'] +
                comment_sim * weights['comment'] +
                tfidf_sim * weights['tfidf'] +
                w2v_sim * weights['word2vec']
            )
            
        except Exception as e:
            logging.error(f"比较语义相似度时出错: {e}")
            return 0.0
            
    def _extract_identifiers(self, content: str) -> List[str]:
        """提取标识符
        
        参数:
            content: 代码内容
            
        返回:
            标识符列表
        """
        identifiers = []
        try:
            # 移除字符串和注释
            content = self._remove_strings_and_comments(content)
            
            # 提取标识符
            words = re.findall(r'\b[A-Za-z_]\w*\b', content)
            
            # 过滤关键字
            keywords = {
                'if', 'else', 'while', 'for', 'do', 'break', 'continue',
                'return', 'try', 'catch', 'throw', 'throws', 'public',
                'private', 'protected', 'class', 'interface', 'extends',
                'implements', 'static', 'final', 'void', 'null', 'true',
                'false', 'new', 'this', 'super'
            }
            
            identifiers = [
                word for word in words
                if word not in keywords
            ]
            
        except Exception as e:
            logging.error(f"提取标识符时出错: {e}")
            
        return identifiers
        
    def _tokenize_identifiers(self, identifiers: List[str]) -> List[str]:
        """分词处理标识符
        
        参数:
            identifiers: 标识符列表
            
        返回:
            分词后的标记列表
        """
        tokens = []
        try:
            for identifier in identifiers:
                # 处理驼峰命名
                words = self.identifier_pattern.findall(identifier)
                
                # 词形还原
                words = [
                    self.lemmatizer.lemmatize(word.lower())
                    for word in words
                ]
                
                # 过滤停用词
                words = [
                    word for word in words
                    if word not in self.stop_words
                ]
                
                tokens.extend(words)
                
        except Exception as e:
            logging.error(f"分词处理标识符时出错: {e}")
            
        return tokens
        
    def _extract_comments(self, content: str) -> List[str]:
        """提取注释
        
        参数:
            content: 代码内容
            
        返回:
            注释列表
        """
        comments = []
        try:
            # 提取单行注释
            single_line = re.findall(r'//.*?$', content, re.MULTILINE)
            comments.extend(single_line)
            
            # 提取多行注释
            multi_line = re.findall(r'/\*.*?\*/', content, re.DOTALL)
            comments.extend(multi_line)
            
            # 清理注释标记
            comments = [
                re.sub(r'^[/*\s]+|[/*\s]+$', '', comment)
                for comment in comments
            ]
            
        except Exception as e:
            logging.error(f"提取注释时出错: {e}")
            
        return comments
        
    def _extract_strings(self, content: str) -> List[str]:
        """提取字符串字面量
        
        参数:
            content: 代码内容
            
        返回:
            字符串列表
        """
        strings = []
        try:
            # 提取双引号字符串
            double_quoted = re.findall(r'"([^"\\]|\\.)*"', content)
            strings.extend(double_quoted)
            
            # 提取单引号字符串
            single_quoted = re.findall(r"'([^'\\]|\\.)*'", content)
            strings.extend(single_quoted)
            
            # 清理引号
            strings = [
                s[1:-1] for s in strings
            ]
            
        except Exception as e:
            logging.error(f"提取字符串时出错: {e}")
            
        return strings
        
    def _compute_tfidf_features(self, tokens: List[str]) -> np.ndarray:
        """计算TF-IDF特征
        
        参数:
            tokens: 标记列表
            
        返回:
            TF-IDF特征向量
        """
        try:
            if not tokens:
                return np.array([])
                
            text = ' '.join(tokens)
            return self.vectorizer.fit_transform([text]).toarray()[0]
            
        except Exception as e:
            logging.error(f"计算TF-IDF特征时出错: {e}")
            return np.array([])
            
    def _compute_word2vec_features(self, tokens: List[str]) -> np.ndarray:
        """计算Word2Vec特征
        
        参数:
            tokens: 标记列表
            
        返回:
            Word2Vec特征向量
        """
        try:
            if not tokens:
                return np.array([])
                
            # 训练Word2Vec模型
            if not self.word2vec:
                self.word2vec = Word2Vec(
                    [tokens],
                    vector_size=100,
                    window=5,
                    min_count=1,
                    workers=4
                )
                
            # 计算平均词向量
            vectors = []
            for token in tokens:
                if token in self.word2vec.wv:
                    vectors.append(self.word2vec.wv[token])
                    
            if vectors:
                return np.mean(vectors, axis=0)
            return np.zeros(self.word2vec.vector_size)
            
        except Exception as e:
            logging.error(f"计算Word2Vec特征时出错: {e}")
            return np.array([])
            
    def _compare_identifiers(
        self,
        identifiers1: List[str],
        identifiers2: List[str]
    ) -> float:
        """比较标识符相似度
        
        参数:
            identifiers1: 第一个标识符列表
            identifiers2: 第二个标识符列表
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if not (identifiers1 and identifiers2):
                return 0.0
                
            # 计算Jaccard相似度
            set1 = set(identifiers1)
            set2 = set(identifiers2)
            
            return len(set1 & set2) / len(set1 | set2)
            
        except Exception as e:
            logging.error(f"比较标识符时出错: {e}")
            return 0.0
            
    def _compare_comments(
        self,
        comments1: List[str],
        comments2: List[str]
    ) -> float:
        """比较注释相似度
        
        参数:
            comments1: 第一个注释列表
            comments2: 第二个注释列表
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if not (comments1 and comments2):
                return 0.0
                
            # 使用TF-IDF和余弦相似度
            text1 = ' '.join(comments1)
            text2 = ' '.join(comments2)
            
            vectors = self.vectorizer.fit_transform([text1, text2])
            similarity = cosine_similarity(vectors)[0][1]
            
            return float(similarity)
            
        except Exception as e:
            logging.error(f"比较注释时出错: {e}")
            return 0.0
            
    def _compare_tfidf(
        self,
        tfidf1: np.ndarray,
        tfidf2: np.ndarray
    ) -> float:
        """比较TF-IDF相似度
        
        参数:
            tfidf1: 第一个TF-IDF向量
            tfidf2: 第二个TF-IDF向量
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if len(tfidf1) == 0 or len(tfidf2) == 0:
                return 0.0
                
            # 计算余弦相似度
            similarity = cosine_similarity(
                tfidf1.reshape(1, -1),
                tfidf2.reshape(1, -1)
            )[0][0]
            
            return float(similarity)
            
        except Exception as e:
            logging.error(f"比较TF-IDF时出错: {e}")
            return 0.0
            
    def _compare_word2vec(
        self,
        w2v1: np.ndarray,
        w2v2: np.ndarray
    ) -> float:
        """比较Word2Vec相似度
        
        参数:
            w2v1: 第一个Word2Vec向量
            w2v2: 第二个Word2Vec向量
            
        返回:
            相似度分数 [0,1]
        """
        try:
            if len(w2v1) == 0 or len(w2v2) == 0:
                return 0.0
                
            # 计算余弦相似度
            similarity = cosine_similarity(
                w2v1.reshape(1, -1),
                w2v2.reshape(1, -1)
            )[0][0]
            
            return float(similarity)
            
        except Exception as e:
            logging.error(f"比较Word2Vec时出错: {e}")
            return 0.0
            
    def _remove_strings_and_comments(self, content: str) -> str:
        """移除字符串和注释
        
        参数:
            content: 代码内容
            
        返回:
            处理后的代码
        """
        try:
            # 移除字符串字面量
            content = re.sub(r'"([^"\\]|\\.)*"', '', content)
            content = re.sub(r"'([^'\\]|\\.)*'", '', content)
            
            # 移除单行注释
            content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
            
            # 移除多行注释
            content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            
            return content
            
        except Exception as e:
            logging.error(f"移除字符串和注释时出错: {e}")
            return content
            
    def _tokenize(self, text: str) -> List[str]:
        """分词处理
        
        参数:
            text: 文本内容
            
        返回:
            分词后的标记列表
        """
        try:
            # 分词
            tokens = word_tokenize(text)
            
            # 词形还原
            tokens = [
                self.lemmatizer.lemmatize(token.lower())
                for token in tokens
            ]
            
            # 过滤停用词
            tokens = [
                token for token in tokens
                if token not in self.stop_words
            ]
            
            return tokens
            
        except Exception as e:
            logging.error(f"分词处理时出错: {e}")
            return [] 