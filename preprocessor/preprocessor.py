"""预处理器模块

该模块用于预处理开源代码库中收集的函数信息。主要功能包括:
1. 冗余消除 - 移除重复函数签名
2. 元信息保存 - 保存版本、函数数量等元数据
3. 代码分割 - 基于相似度的代码分割

作者: byRen2002
修改日期: 2025年3月
许可证: MIT
"""

import os
import sys
import re
import shutil
import json
import math
import tlsh
import datetime
import time
import logging
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Set, Tuple, Any, Optional, Generator
from core.parallel_manager import ParallelManager
from core.performance_monitor import PerformanceMonitor
from core.resource_manager import ResourceManager, safe_open
from core.cache import Cache
from core.logger import setup_logger, get_module_logger
from core.config_manager import ConfigManager

# 获取模块日志记录器
logger = get_module_logger("preprocessor")


class Preprocessor:
    """预处理器类，用于预处理开源代码库中收集的函数信息"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化预处理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config = ConfigManager(config_path)
        self.resource_manager = ResourceManager()
        self.cache = Cache()
        self.performance_monitor = PerformanceMonitor("preprocessor")
        self.parallel_manager = ParallelManager()
        
        # 设置日志
        setup_logger(self.config.get_path("log_path"))
        
        # 创建必要的目录
        self.config.create_required_directories()
        
        # 创建资源管理器
        self.resource_manager = ResourceManager()
        
        # 创建缓存
        cache_size = self.config.get("performance", "cache_size", 1000)
        cache_expire = self.config.get("performance", "cache_expire", 3600)
        cache_dir = self.config.get_path("cache_path")
        self.cache = Cache(cache_size, cache_expire, True, cache_dir)
        
        # 创建内存优化器
        memory_limit = self.config.get("performance", "memory_limit", 0.9)
        self.memory_optimizer = MemoryOptimizer(memory_limit)
        
        # 相似度阈值
        self.theta = self.config.get("analysis", "theta", 0.1)
        
        # 分隔符
        self.separator = "#@#"
        self.sep_len = len(self.separator)
    
    def extract_version_date(self, repo_name: str) -> Dict[str, str]:
        """提取版本日期
        
        Args:
            repo_name: 仓库名称
        
        Returns:
            版本日期字典，键为版本名，值为日期
        """
        ver_date_dict = {}
        
        tag_date_file = os.path.join(self.config.get_path("tag_date_path"), repo_name)
        if not os.path.exists(tag_date_file):
            logger.warning(f"标签日期文件不存在: {tag_date_file}")
            return ver_date_dict
        
        try:
            with safe_open(tag_date_file, 'r') as f:
                content = f.read()
                
                for line in content.split('\n'):
                    if not line or line.isspace():
                        continue
                    
                    # 解析日期和标签
                    match = re.search(r'(\d{4}-\d{2}-\d{2}).*\(.*tag: (.*?)[,\)]', line)
                    if match:
                        date_str = match.group(1)
                        tags = match.group(2).split(',')
                        
                        for tag in tags:
                            tag = tag.strip()
                            if tag:
                                ver_date_dict[tag] = date_str
        except Exception as e:
            logger.error(f"提取版本日期失败 {repo_name}: {e}")
        
        return ver_date_dict
    
    def process_single_repo(self, repo_name: str) -> Tuple[Dict[str, List[str]], Dict[str, str], Dict[str, int]]:
        """处理单个仓库
        
        Args:
            repo_name: 仓库名称
        
        Returns:
            签名字典, 函数日期字典, 版本索引字典
        """
        logger.info(f"开始处理仓库: {repo_name}")
        
        func_date_dict = {}
        temp_date_dict = {}
        ver_date_dict = self.extract_version_date(repo_name)
        
        ver_temp_list = []
        signature = {}
        ver_dict = {}
        idx = 0
        
        repo_path = os.path.join(self.config.get_path("result_path"), repo_name)
        if not os.path.exists(repo_path):
            logger.warning(f"仓库路径不存在: {repo_path}")
            return signature, func_date_dict, ver_dict
        
        # 获取版本列表
        for each_version in os.listdir(repo_path):
            if not each_version.startswith("fuzzy_") or not each_version.endswith(".hidx"):
                continue
                
            version_name = each_version.split("fuzzy_")[1].replace(".hidx", "")
            if not version_name or version_name.isspace():
                continue
                
            ver_temp_list.append(version_name)
        
        ver_temp_list.sort()
        
        # 处理每个版本
        for version_name in ver_temp_list:
            ver_dict[version_name] = idx
            idx += 1
            
            version_file = os.path.join(repo_path, f"fuzzy_{version_name}.hidx")
            
            try:
                with safe_open(version_file, 'r') as fp:
                    # 跳过标题行
                    next(fp)
                    
                    for line in fp:
                        if not line or line.isspace():
                            continue
                        
                        parts = line.strip().split('\t')
                        if not parts:
                            continue
                            
                        hash_val = parts[0]
                        
                        if hash_val not in signature:
                            signature[hash_val] = []
                            temp_date_dict[hash_val] = []
                        
                        signature[hash_val].append(str(idx - 1))
                        
                        if version_name in ver_date_dict:
                            temp_date_dict[hash_val].append(ver_date_dict[version_name])
                        else:
                            temp_date_dict[hash_val].append("NODATE")
            except Exception as e:
                logger.error(f"处理版本文件失败 {version_file}: {e}")
        
        # 存储函数日期
        for hash_val in temp_date_dict:
            if temp_date_dict[hash_val]:
                temp_date_dict[hash_val].sort()
                func_date_dict[hash_val] = temp_date_dict[hash_val][0]
        
        # 保存版本索引
        ver_idx_file = os.path.join(self.config.get_path("ver_idx_path"), f"{repo_name}.veridx")
        try:
            with safe_open(ver_idx_file, 'w') as f:
                json.dump(ver_dict, f, indent=2)
        except Exception as e:
            logger.error(f"保存版本索引失败 {ver_idx_file}: {e}")
        
        logger.info(f"处理仓库完成: {repo_name}")
        return signature, func_date_dict, ver_dict
    
    def process_files_parallel(self, files: List[str]) -> Dict[str, List[str]]:
        """并行处理文件
        
        Args:
            files: 文件路径列表
            
        Returns:
            处理结果字典
        """
        def process_file_chunk(chunk: List[str]) -> Dict[str, List[str]]:
            result = {}
            for file_path in chunk:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 处理文件内容...
                    # 这里添加具体的文件处理逻辑
                    result[file_path] = [content]  # 示例结果
                except Exception as e:
                    logger.error(f"处理文件失败 {file_path}: {str(e)}")
            return result
            
        return self.parallel_manager.process_items(
            items=files,
            process_func=process_file_chunk,
            pool_name="file_processor"
        )
        
    def process_repos_parallel(self, repos: List[str]) -> Tuple[Dict, Dict]:
        """并行处理仓库
        
        Args:
            repos: 仓库列表
            
        Returns:
            (签名字典, 函数日期字典)
        """
        def process_repo_chunk(chunk: List[str]) -> Tuple[Dict, Dict]:
            signatures = {}
            func_dates = {}
            for repo in chunk:
                try:
                    repo_sigs, repo_dates, _ = self.process_single_repo(repo)
                    signatures.update(repo_sigs)
                    func_dates.update(repo_dates)
                except Exception as e:
                    logger.error(f"处理仓库失败 {repo}: {str(e)}")
            return signatures, func_dates
            
        results = self.parallel_manager.process_items(
            items=repos,
            process_func=process_repo_chunk,
            pool_name="repo_processor"
        )
        
        # 合并结果
        all_signatures = {}
        all_func_dates = {}
        for signatures, func_dates in results:
            all_signatures.update(signatures)
            all_func_dates.update(func_dates)
            
        return all_signatures, all_func_dates
        
    def redundancy_elimination(self) -> None:
        """冗余消除"""
        logger.info("开始冗余消除...")
        
        try:
            # 获取所有仓库
            result_path = self.config.get_path("result_path")
            repos = [
                repo for repo in os.listdir(result_path)
                if os.path.isdir(os.path.join(result_path, repo))
            ]
            
            # 并行处理仓库
            all_signatures, all_func_dates = self.process_repos_parallel(repos)
            
            # 保存函数日期
            func_date_file = os.path.join(
                self.config.get_path("func_date_path"),
                "funcDate.json"
            )
            with open(func_date_file, 'w') as f:
                json.dump(all_func_dates, f, indent=2)
                
            # 保存初始签名
            initial_db_file = os.path.join(
                self.config.get_path("initial_db_path"),
                "initialSigs.json"
            )
            with open(initial_db_file, 'w') as f:
                json.dump(all_signatures, f, indent=2)
                
            logger.info("冗余消除完成")
            
        except Exception as e:
            logger.error(f"冗余消除失败: {str(e)}")
            raise
            
    def save_meta_infos(self) -> None:
        """保存元信息"""
        logger.info("开始保存元信息...")
        
        try:
            # 获取所有仓库
            result_path = self.config.get_path("result_path")
            repos = [
                repo for repo in os.listdir(result_path)
                if os.path.isdir(os.path.join(result_path, repo))
            ]
            
            # 并行处理仓库
            def process_repo_meta(repo: str) -> Dict:
                try:
                    # 处理仓库元信息...
                    # 这里添加具体的元信息处理逻辑
                    return {"repo": repo}  # 示例结果
                except Exception as e:
                    logger.error(f"处理仓库元信息失败 {repo}: {str(e)}")
                    return {}
                    
            results = self.parallel_manager.process_items(
                items=repos,
                process_func=process_repo_meta,
                pool_name="meta_processor"
            )
            
            # 保存元信息
            meta_file = os.path.join(
                self.config.get_path("meta_path"),
                "meta.json"
            )
            with open(meta_file, 'w') as f:
                json.dump(results, f, indent=2)
                
            logger.info("元信息保存完成")
            
        except Exception as e:
            logger.error(f"保存元信息失败: {str(e)}")
            raise
            
    def compute_tlsh_diff(self, hash1: str, hash2: str) -> int:
        """计算两个TLSH哈希值的差异
        
        Args:
            hash1: 第一个哈希值
            hash2: 第二个哈希值
        
        Returns:
            差异值
        """
        # 检查缓存
        cache_key = f"{hash1}:{hash2}"
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            # 确保哈希值格式正确
            if len(hash1) == 70 and hash1.startswith("T1"):
                hash1 = hash1[2:]
            if len(hash2) == 70 and hash2.startswith("T1"):
                hash2 = hash2[2:]
            
            diff = tlsh.diff(hash1, hash2)
            
            # 缓存结果
            self.cache.put(cache_key, diff)
            
            return diff
        except Exception as e:
            logger.error(f"计算TLSH差异失败: {e}")
            return 1000  # 返回一个大值表示差异很大
    
    def code_segmentation(self) -> None:
        """代码分割"""
        logger.info("开始代码分割...")
        
        try:
            # 获取所有文件
            code_path = self.config.get_path("code_path")
            files = []
            for root, _, filenames in os.walk(code_path):
                for filename in filenames:
                    if filename.endswith(('.c', '.cpp', '.h', '.hpp')):
                        files.append(os.path.join(root, filename))
                        
            # 并行处理文件
            results = self.process_files_parallel(files)
            
            # 保存分割结果
            segment_path = self.config.get_path("segment_path")
            os.makedirs(segment_path, exist_ok=True)
            
            for file_path, segments in results.items():
                rel_path = os.path.relpath(file_path, code_path)
                out_file = os.path.join(segment_path, rel_path + '.segments')
                os.makedirs(os.path.dirname(out_file), exist_ok=True)
                with open(out_file, 'w') as f:
                    json.dump(segments, f, indent=2)
                    
            logger.info("代码分割完成")
            
        except Exception as e:
            logger.error(f"代码分割失败: {str(e)}")
            raise
            
    def run(self) -> None:
        """运行预处理器"""
        try:
            # 开始性能监控
            self.performance_monitor.start_stage("redundancy_elimination")
            
            # 冗余消除
            self.redundancy_elimination()
            
            # 结束阶段
            self.performance_monitor.end_stage("redundancy_elimination")
            
            # 开始下一阶段
            self.performance_monitor.start_stage("save_meta_infos")
            
            # 保存元信息
            self.save_meta_infos()
            
            # 结束阶段
            self.performance_monitor.end_stage("save_meta_infos")
            
            # 开始下一阶段
            self.performance_monitor.start_stage("code_segmentation")
            
            # 代码分割
            self.code_segmentation()
            
            # 结束阶段
            self.performance_monitor.end_stage("code_segmentation")
            
        except Exception as e:
            logger.error(f"程序执行失败: {e}")
            logger.error(traceback.format_exc())
            sys.exit(1)
        finally:
            # 保存性能报告
            report_file = os.path.join(
                self.config.get_path("log_path"),
                f"preprocessor_performance_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            self.performance_monitor.save_report(report_file)
            
            # 清理资源
            self.resource_manager.close_all()
            self.parallel_manager.close_all()
            self.cache.clear()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Re-Centris 预处理器')
    parser.add_argument('-c', '--config', help='配置文件路径')
    args = parser.parse_args()
    
    preprocessor = Preprocessor(args.config)
    preprocessor.run()


if __name__ == "__main__":
    main() 