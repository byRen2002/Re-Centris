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
import sys
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Set, Tuple, Any, Optional, Generator

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.parallel_manager import ParallelManager
from core.performance_monitor import PerformanceMonitor
from core.resource_manager import ResourceManager, safe_open
from core.cache import Cache
from core.memory_optimizer import MemoryOptimizer
from core.logger import setup_logger, get_module_logger
from core.config_manager import ConfigManager

# 获取模块日志记录器
logger = get_module_logger("preprocessor")


def process_file_chunk_for_redundancy(chunk: List[str]) -> Dict[str, Dict]:
    """处理文件块，进行冗余消除"""
    result = {}

    for file_path in chunk:
        try:
            # 解析文件路径获取仓库名和版本
            file_name = os.path.basename(file_path)
            if not file_name.startswith('fuzzy_') or not file_name.endswith('.hidx'):
                continue

            repo_name = os.path.basename(os.path.dirname(file_path))
            version_name = file_name.replace('fuzzy_', '').replace('.hidx', '')

            if not version_name or version_name.isspace():
                continue

            # 读取函数哈希数据
            signatures = {}
            with open(file_path, 'r', encoding='utf-8') as f:
                # 跳过第一行（通常是头部信息）
                next(f, None)

                for line in f:
                    line = line.strip()
                    if not line or line.isspace():
                        continue

                    parts = line.split('\t')
                    if len(parts) >= 1:
                        hash_val = parts[0]
                        if hash_val not in signatures:
                            signatures[hash_val] = []
                        signatures[hash_val].append(version_name)

            result[file_path] = {
                'repo_name': repo_name,
                'version_name': version_name,
                'signatures': signatures,
                'func_count': len(signatures)
            }

        except Exception as e:
            logger.error(f"处理文件失败 {file_path}: {str(e)}")

    return result


def process_single_repo_for_redundancy(repo_name: str, config) -> Dict:
    """处理单个仓库进行冗余消除"""
    try:
        logger.info(f"开始处理仓库: {repo_name}")

        # 提取版本日期信息
        ver_date_dict = extract_version_dates_for_repo(repo_name, config)

        func_date_dict = {}
        temp_date_dict = {}
        signature = {}
        ver_dict = {}
        idx = 0

        # 获取版本列表
        result_path = config.get_path("result_path")
        repo_path = os.path.join(result_path, repo_name)
        version_files = [f for f in os.listdir(repo_path) if f.startswith('fuzzy_') and f.endswith('.hidx')]

        # 提取版本名并排序
        ver_temp_list = []
        for version_file in version_files:
            version_name = version_file.replace('fuzzy_', '').replace('.hidx', '')
            if version_name and not version_name.isspace():
                ver_temp_list.append(version_name)

        ver_temp_list.sort()

        # 处理每个版本
        for version_name in ver_temp_list:
            ver_dict[version_name] = idx
            idx += 1

            version_file_path = os.path.join(repo_path, f"fuzzy_{version_name}.hidx")

            with open(version_file_path, 'r', encoding='utf-8') as fp:
                # 跳过第一行
                next(fp, None)

                for line in fp:
                    line = line.strip()
                    if not line or line.isspace():
                        continue

                    parts = line.split('\t')
                    if len(parts) >= 1:
                        hash_val = parts[0]

                        if hash_val not in signature:
                            signature[hash_val] = []
                            temp_date_dict[hash_val] = []

                        signature[hash_val].append(str(idx - 1))

                        # 添加日期信息
                        if version_name in ver_date_dict:
                            temp_date_dict[hash_val].append(ver_date_dict[version_name])
                        else:
                            temp_date_dict[hash_val].append("NODATE")

        # 处理函数日期
        for hash_val in temp_date_dict:
            temp_date_dict[hash_val].sort()
            func_date_dict[hash_val] = temp_date_dict[hash_val][0]

        # 保存函数日期文件
        func_date_path = config.get_path("func_date_path")
        os.makedirs(func_date_path, exist_ok=True)

        func_date_file = os.path.join(func_date_path, f"{repo_name}_funcdate")
        with open(func_date_file, 'w', encoding='utf-8') as f:
            json.dump(func_date_dict, f)

        # 生成初始签名数据
        initial_sigs = []
        for hash_val, versions in signature.items():
            initial_sigs.append({
                'hash': hash_val,
                'vers': versions
            })

        # 保存初始签名文件
        initial_db_path = config.get_path("initial_db_path")
        os.makedirs(initial_db_path, exist_ok=True)

        initial_sig_file = os.path.join(initial_db_path, f"{repo_name}_sig")
        with open(initial_sig_file, 'w', encoding='utf-8') as f:
            json.dump(initial_sigs, f)

        # 保存版本索引
        ver_idx_path = config.get_path("ver_idx_path")
        os.makedirs(ver_idx_path, exist_ok=True)

        ver_idx_file = os.path.join(ver_idx_path, f"{repo_name}_idx")
        save_json = []
        for ver_name in ver_temp_list:
            temp = {"ver": ver_name, "idx": str(ver_dict[ver_name])}
            save_json.append(temp)

        with open(ver_idx_file, 'w', encoding='utf-8') as f:
            json.dump(save_json, f)

        logger.info(f"仓库 {repo_name} 处理完成: {len(initial_sigs)} 个函数")

        return {
            'repo_name': repo_name,
            'func_count': len(initial_sigs),
            'version_count': len(ver_temp_list)
        }

    except Exception as e:
        logger.error(f"处理仓库 {repo_name} 失败: {str(e)}")
        return None


def extract_version_dates_for_repo(repo_name: str, config) -> Dict[str, str]:
    """提取版本日期信息"""
    ver_date_dict = {}
    tag_date_path = config.get_path("tag_date_path")
    repo_date_file = os.path.join(tag_date_path, repo_name)

    if os.path.isfile(repo_date_file):
        try:
            with open(repo_date_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and '\t' in line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            version = parts[0]
                            date = parts[1]
                            ver_date_dict[version] = date
        except Exception as e:
            logger.error(f"读取版本日期文件失败 {repo_date_file}: {str(e)}")

    return ver_date_dict


# 全局变量用于传递config
_global_config = None

def set_global_config(config):
    """设置全局配置"""
    global _global_config
    _global_config = config

def process_repo_wrapper_for_redundancy(repo_names) -> Dict:
    """包装函数，用于并行处理"""
    # 处理可能传入的列表或单个字符串
    if isinstance(repo_names, list):
        if len(repo_names) == 1:
            repo_name = repo_names[0]
        else:
            # 如果是多个仓库，只处理第一个
            repo_name = repo_names[0]
            logger.warning(f"收到多个仓库名，只处理第一个: {repo_name}")
    else:
        repo_name = repo_names

    return process_single_repo_for_redundancy(repo_name, _global_config)


def process_repo_meta_for_save(oss_files) -> Dict:
    """处理仓库元信息的包装函数"""
    # 处理可能传入的列表或单个字符串
    if isinstance(oss_files, list):
        if len(oss_files) == 1:
            oss_file = oss_files[0]
        else:
            oss_file = oss_files[0]
            logger.warning(f"收到多个OSS文件，只处理第一个: {oss_file}")
    else:
        oss_file = oss_files

    try:
        repo_name = oss_file.replace("_sig", "")
        result_path = _global_config.get_path("result_path")
        initial_db_path = _global_config.get_path("initial_db_path")
        meta_path = _global_config.get_path("meta_path")
        weight_path = os.path.join(meta_path, "weights")

        # 计算版本数量
        repo_path = os.path.join(result_path, repo_name)
        if not os.path.exists(repo_path):
            return None

        versions = os.listdir(repo_path)
        tot_vers = len(versions)

        if tot_vers == 0:
            return None

        # 读取函数数据
        oss_file_path = os.path.join(initial_db_path, oss_file)
        with open(oss_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        tot_funcs = len(json_data)
        weight_json = {}
        unique_funcs = {}

        # 计算权重和唯一函数
        import math
        for func_data in json_data:
            hash_val = func_data['hash']
            ver_list = func_data['vers']

            unique_funcs[hash_val] = repo_name
            # 计算权重: log(总版本数/包含该函数的版本数)
            weight_json[hash_val] = math.log(float(tot_vers) / float(len(ver_list)))

        # 保存权重文件
        os.makedirs(weight_path, exist_ok=True)
        weight_file = os.path.join(weight_path, f"{repo_name}_weights")
        with open(weight_file, 'w', encoding='utf-8') as f:
            json.dump(weight_json, f)

        return {
            'repo_name': repo_name,
            'ave_funcs': int(tot_funcs / tot_vers),
            'all_funcs': tot_funcs,
            'unique': unique_funcs,
            'weights': weight_json
        }

    except Exception as e:
        logger.error(f"处理仓库元信息失败 {oss_file}: {str(e)}")
        return None


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
        return self.parallel_manager.process_items(
            items=files,
            process_func=process_file_chunk_for_redundancy,
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

            logger.info(f"找到 {len(repos)} 个仓库需要处理")

            # 设置全局配置
            set_global_config(self.config)

            # 并行处理所有仓库
            results = self.parallel_manager.process_items(
                items=repos,
                process_func=process_repo_wrapper_for_redundancy,
                pool_name="redundancy_eliminator"
            )

            # 统计结果
            total_funcs = 0
            processed_repos = 0
            for result in results:
                if result:
                    total_funcs += result['func_count']
                    processed_repos += 1

            logger.info(f"冗余消除完成: 处理了 {processed_repos} 个仓库，共 {total_funcs} 个函数")

            # 生成最终组件数据库
            self.generate_component_db()

        except Exception as e:
            logger.error(f"冗余消除失败: {str(e)}")
            raise

    def extract_version_dates(self, repo_name: str) -> Dict[str, str]:
        """提取版本日期信息"""
        ver_date_dict = {}
        tag_date_path = self.config.get_path("tag_date_path")
        repo_date_file = os.path.join(tag_date_path, repo_name)

        if os.path.isfile(repo_date_file):
            try:
                with open(repo_date_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and '\t' in line:
                            parts = line.split('\t')
                            if len(parts) >= 2:
                                version = parts[0]
                                date = parts[1]
                                ver_date_dict[version] = date
            except Exception as e:
                logger.error(f"读取版本日期文件失败 {repo_date_file}: {str(e)}")

        return ver_date_dict

    def generate_component_db(self) -> None:
        """生成最终组件数据库"""
        logger.info("开始生成最终组件数据库...")

        try:
            import shutil

            initial_db_path = self.config.get_path("initial_db_path")
            final_db_path = self.config.get_path("final_db_path")

            # 确保目标目录存在
            os.makedirs(final_db_path, exist_ok=True)

            # 获取所有初始签名文件
            sig_files = [
                f for f in os.listdir(initial_db_path)
                if f.endswith('_sig') and os.path.isfile(os.path.join(initial_db_path, f))
            ]

            logger.info(f"找到 {len(sig_files)} 个签名文件需要处理")

            # 简单版本：直接复制所有签名文件到最终数据库
            # 在更复杂的实现中，这里会进行进一步的冗余消除和优化
            for sig_file in sig_files:
                src_file = os.path.join(initial_db_path, sig_file)
                dst_file = os.path.join(final_db_path, sig_file)
                shutil.copy2(src_file, dst_file)
                logger.debug(f"复制签名文件: {sig_file}")

            logger.info(f"最终组件数据库生成完成: {len(sig_files)} 个文件")

        except Exception as e:
            logger.error(f"生成最终组件数据库失败: {str(e)}")
            raise

    def save_meta_infos(self) -> None:
        """保存元信息"""
        logger.info("开始保存元信息...")

        try:
            # 获取初始数据库路径
            initial_db_path = self.config.get_path("initial_db_path")
            meta_path = self.config.get_path("meta_path")
            weight_path = os.path.join(meta_path, "weights")

            # 确保权重目录存在
            os.makedirs(weight_path, exist_ok=True)

            # 获取所有OSS文件
            oss_files = [
                f for f in os.listdir(initial_db_path)
                if f.endswith('_sig') and os.path.isfile(os.path.join(initial_db_path, f))
            ]

            logger.info(f"找到 {len(oss_files)} 个OSS文件需要处理")

            # 设置全局配置
            set_global_config(self.config)

            # 并行处理
            results = self.parallel_manager.process_items(
                items=oss_files,
                process_func=process_repo_meta_for_save,
                pool_name="meta_processor"
            )

            # 汇总结果
            ave_func_json = {}
            all_func_json = {}
            unique_funcs = {}

            for result in results:
                if result:
                    repo_name = result['repo_name']
                    ave_func_json[repo_name] = result['ave_funcs']
                    all_func_json[repo_name] = result['all_funcs']
                    unique_funcs.update(result['unique'])

            # 保存元信息文件
            with open(os.path.join(meta_path, "aveFuncs"), 'w', encoding='utf-8') as f:
                json.dump(ave_func_json, f)

            with open(os.path.join(meta_path, "allFuncs"), 'w', encoding='utf-8') as f:
                json.dump(all_func_json, f)

            # 保存唯一函数信息
            unique_json = []
            for hash_val, repo_name in unique_funcs.items():
                unique_json.append({"hash": hash_val, "OSS": [repo_name]})

            with open(os.path.join(meta_path, "uniqueFuncs"), 'w', encoding='utf-8') as f:
                json.dump(unique_json, f)

            logger.info(f"元信息保存完成: 处理了 {len(ave_func_json)} 个仓库")

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
            # 获取代码路径，如果没有配置则使用仓库路径
            code_path = self.config.get("paths", "code_path", None)
            if not code_path:
                code_path = self.config.get_path("repo_path")

            if not os.path.exists(code_path):
                logger.warning(f"代码路径不存在，跳过代码分割: {code_path}")
                return

            files = []
            for root, _, filenames in os.walk(code_path):
                for filename in filenames:
                    if filename.endswith(('.c', '.cpp', '.h', '.hpp')):
                        files.append(os.path.join(root, filename))

            if not files:
                logger.warning("没有找到C/C++源代码文件，跳过代码分割")
                return

            logger.info(f"找到 {len(files)} 个源代码文件")

            # 并行处理文件
            results = self.process_files_parallel(files)

            # 保存分割结果
            segment_path = self.config.get("paths", "segment_path", None)
            if not segment_path:
                # 如果没有配置segment_path，使用默认路径
                segment_path = os.path.join(os.path.dirname(self.config.get_path("result_path")), "segments")
            os.makedirs(segment_path, exist_ok=True)

            # 合并结果
            all_results = {}
            for result_dict in results:
                if result_dict:
                    all_results.update(result_dict)

            for file_path, file_data in all_results.items():
                rel_path = os.path.relpath(file_path, code_path)
                out_file = os.path.join(segment_path, rel_path + '.segments')
                os.makedirs(os.path.dirname(out_file), exist_ok=True)
                with open(out_file, 'w') as f:
                    json.dump(file_data, f, indent=2)
                    
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