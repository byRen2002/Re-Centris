"""克隆度量模块

该模块实现了代码克隆的度量和分析功能。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import logging
from typing import Dict, List, Set, Tuple
from collections import defaultdict
import numpy as np
from sklearn.cluster import DBSCAN

class CloneMetrics:
    """克隆度量类"""
    
    def __init__(self):
        """初始化克隆度量器"""
        pass
        
    def analyze_patterns(self, clones: List[Dict]) -> Dict:
        """分析克隆模式
        
        参数:
            clones: 克隆对列表
            
        返回:
            克隆模式分析结果
        """
        try:
            # 基本统计
            basic_stats = self._compute_basic_stats(clones)
            
            # 克隆类型分布
            type_dist = self._analyze_clone_types(clones)
            
            # 克隆大小分布
            size_dist = self._analyze_clone_sizes(clones)
            
            # 克隆聚类
            clusters = self._cluster_clones(clones)
            
            # 克隆链分析
            chains = self._analyze_clone_chains(clones)
            
            return {
                'basic_stats': basic_stats,
                'type_distribution': type_dist,
                'size_distribution': size_dist,
                'clusters': clusters,
                'chains': chains
            }
            
        except Exception as e:
            logging.error(f"分析克隆模式时出错: {e}")
            return {}
            
    def _compute_basic_stats(self, clones: List[Dict]) -> Dict:
        """计算基本统计信息
        
        参数:
            clones: 克隆对列表
            
        返回:
            基本统计信息
        """
        try:
            # 克隆对数量
            total_pairs = len(clones)
            
            # 涉及的文件数量
            files = set()
            for clone in clones:
                files.add(clone['file1'])
                files.add(clone['file2'])
            total_files = len(files)
            
            # 相似度统计
            similarities = [
                clone['similarity']['overall']
                for clone in clones
            ]
            
            return {
                'total_clone_pairs': total_pairs,
                'total_files': total_files,
                'avg_similarity': np.mean(similarities),
                'min_similarity': np.min(similarities),
                'max_similarity': np.max(similarities),
                'std_similarity': np.std(similarities)
            }
            
        except Exception as e:
            logging.error(f"计算基本统计信息时出错: {e}")
            return {}
            
    def _analyze_clone_types(self, clones: List[Dict]) -> Dict:
        """分析克隆类型分布
        
        参数:
            clones: 克隆对列表
            
        返回:
            克隆类型分布
        """
        try:
            type_counts = defaultdict(int)
            
            for clone in clones:
                sim = clone['similarity']
                
                # Type-1: 完全相同 (相似度 > 0.95)
                if sim['overall'] > 0.95:
                    type_counts['type1'] += 1
                    
                # Type-2: 仅变量名不同 (结构相似度高)
                elif sim['ast'] > 0.9:
                    type_counts['type2'] += 1
                    
                # Type-3: 有小的修改
                elif sim['overall'] > 0.7:
                    type_counts['type3'] += 1
                    
                # Type-4: 语义相似
                else:
                    type_counts['type4'] += 1
                    
            total = sum(type_counts.values())
            
            return {
                'counts': dict(type_counts),
                'percentages': {
                    t: count / total * 100
                    for t, count in type_counts.items()
                }
            }
            
        except Exception as e:
            logging.error(f"分析克隆类型时出错: {e}")
            return {}
            
    def _analyze_clone_sizes(self, clones: List[Dict]) -> Dict:
        """分析克隆大小分布
        
        参数:
            clones: 克隆对列表
            
        返回:
            克隆大小分布
        """
        try:
            # 按大小分组
            size_groups = defaultdict(int)
            
            for clone in clones:
                # 计算克隆大小（行数）
                size = (
                    clone.get('end_line1', 0) -
                    clone.get('start_line1', 0)
                )
                
                if size <= 10:
                    group = 'small'
                elif size <= 50:
                    group = 'medium'
                else:
                    group = 'large'
                    
                size_groups[group] += 1
                
            total = sum(size_groups.values())
            
            return {
                'counts': dict(size_groups),
                'percentages': {
                    g: count / total * 100
                    for g, count in size_groups.items()
                }
            }
            
        except Exception as e:
            logging.error(f"分析克隆大小时出错: {e}")
            return {}
            
    def _cluster_clones(self, clones: List[Dict]) -> List[List[Dict]]:
        """聚类分析克隆
        
        参数:
            clones: 克隆对列表
            
        返回:
            克隆簇列表
        """
        try:
            if not clones:
                return []
                
            # 构建相似度矩阵
            n = len(clones)
            similarity_matrix = np.zeros((n, n))
            
            for i in range(n):
                for j in range(n):
                    if i == j:
                        similarity_matrix[i][j] = 1.0
                    else:
                        similarity_matrix[i][j] = self._compute_clone_pair_similarity(
                            clones[i],
                            clones[j]
                        )
                        
            # 使用DBSCAN聚类
            clustering = DBSCAN(
                eps=0.3,  # 邻域半径
                min_samples=2,  # 最小样本数
                metric='precomputed'  # 使用预计算的距离矩阵
            ).fit(1 - similarity_matrix)  # 转换为距离矩阵
            
            # 整理聚类结果
            labels = clustering.labels_
            clusters = defaultdict(list)
            
            for i, label in enumerate(labels):
                if label != -1:  # 忽略噪声点
                    clusters[label].append(clones[i])
                    
            return list(clusters.values())
            
        except Exception as e:
            logging.error(f"聚类分析克隆时出错: {e}")
            return []
            
    def _analyze_clone_chains(self, clones: List[Dict]) -> List[List[Dict]]:
        """分析克隆链
        
        参数:
            clones: 克隆对列表
            
        返回:
            克隆链列表
        """
        try:
            # 构建克隆图
            graph = defaultdict(list)
            for clone in clones:
                graph[clone['file1']].append((clone['file2'], clone))
                graph[clone['file2']].append((clone['file1'], clone))
                
            # 查找克隆链
            chains = []
            visited = set()
            
            def dfs(node: str, chain: List[Dict]) -> None:
                """深度优先搜索查找克隆链"""
                if len(chain) > 1:
                    chains.append(chain[:])
                    
                visited.add(node)
                for next_node, clone_info in graph[node]:
                    if next_node not in visited:
                        chain.append(clone_info)
                        dfs(next_node, chain)
                        chain.pop()
                visited.remove(node)
                
            # 从每个节点开始搜索
            for node in graph:
                if node not in visited:
                    dfs(node, [])
                    
            return chains
            
        except Exception as e:
            logging.error(f"分析克隆链时出错: {e}")
            return []
            
    def _compute_clone_pair_similarity(
        self,
        clone1: Dict,
        clone2: Dict
    ) -> float:
        """计算克隆对之间的相似度
        
        参数:
            clone1: 第一个克隆对
            clone2: 第二个克隆对
            
        返回:
            相似度分数 [0,1]
        """
        try:
            # 文件重叠度
            files1 = {clone1['file1'], clone1['file2']}
            files2 = {clone2['file1'], clone2['file2']}
            file_overlap = len(files1 & files2) / len(files1 | files2)
            
            # 相似度差异
            sim_diff = abs(
                clone1['similarity']['overall'] -
                clone2['similarity']['overall']
            )
            
            # 综合评分
            return (file_overlap + (1 - sim_diff)) / 2
            
        except Exception as e:
            logging.error(f"计算克隆对相似度时出错: {e}")
            return 0.0 