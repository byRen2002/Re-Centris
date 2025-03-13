"""Re-Centris 检测器模块 - 基于TLSH的代码克隆和依赖关系检测器。

主要功能:
1. 代码克隆检测 - 使用TLSH算法检测代码克隆
2. 依赖关系分析 - 分析组件间的依赖关系
3. 版本预测 - 预测使用的组件版本

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import os
import sys
import re
import json
import tlsh
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from typing import Dict, List, Tuple, Optional, Any

from core.config_manager import ConfigManager
from core.cache import Cache
from core.resource_manager import ResourceManager
from core.memory_optimizer import MemoryOptimizer
from core.performance_monitor import PerformanceMonitor
from core.logger import logger, setup_logger
from core.parallel_manager import ParallelManager

class Detector:
    """代码克隆和依赖关系检测器类"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化检测器
        
        Args:
            config_path: 配置文件路径
        """
        self.config = ConfigManager(config_path)
        self.resource_manager = ResourceManager()
        self.cache = Cache()
        self.performance_monitor = PerformanceMonitor("detector")
        self.parallel_manager = ParallelManager()
        
        # 设置日志
        setup_logger(self.config.get_path("log_path"))
        
        # 从配置加载参数
        self.theta = self.config.get("analysis.similarity_threshold", 0.1)
        self.tlsh_threshold = self.config.get("analysis.tlsh_threshold", 30)
        
        # 设置路径
        self.base_path = self.config.get("paths.base_path")
        self.result_path = os.path.join(self.base_path, "detector")
        self.repo_func_path = os.path.join(self.base_path, "osscollector/repo_functions")
        self.ver_idx_path = os.path.join(self.base_path, "preprocessor/verIDX")
        self.initial_db_path = os.path.join(self.base_path, "preprocessor/initialSigs")
        self.final_db_path = os.path.join(self.base_path, "preprocessor/componentDB")
        self.meta_path = os.path.join(self.base_path, "preprocessor/metaInfos")
        self.weight_path = os.path.join(self.meta_path, "weights")
        
        # 创建必要的目录
        self._create_directories()
        
        # 加载组件数据库
        self.component_db = self._read_component_db()
        self.ave_funcs = self._get_ave_funcs()
        
    def _create_directories(self):
        """创建必要的目录"""
        dirs = [
            self.result_path,
            self.repo_func_path,
            self.ver_idx_path,
            self.initial_db_path,
            self.final_db_path,
            self.meta_path,
            self.weight_path
        ]
        
        for directory in dirs:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logger.info(f"创建目录: {directory}")
                
    def _read_component_db(self) -> Dict[str, List[str]]:
        """读取组件数据库"""
        component_db = {}
        
        for oss in os.listdir(self.final_db_path):
            component_db[oss] = []
            with open(os.path.join(self.final_db_path, oss), 'r') as fp:
                json_data = json.load(fp)
                for hash_entry in json_data:
                    component_db[oss].append(hash_entry["hash"])
                    
        return component_db
        
    def _get_ave_funcs(self) -> Dict[str, int]:
        """获取平均函数数量"""
        ave_funcs = {}
        ave_funcs_path = os.path.join(self.meta_path, "aveFuncs")
        
        with open(ave_funcs_path, 'r') as fp:
            ave_funcs = json.load(fp)
            
        return ave_funcs
        
    def process_file(self, file_path: str, repo_path: str) -> Tuple[Dict, int, int, int]:
        """处理单个文件
        
        Args:
            file_path: 文件路径
            repo_path: 仓库路径
            
        Returns:
            Tuple[Dict, int, int, int]: (函数哈希字典, 文件数, 函数数, 代码行数)
        """
        # 检查缓存
        cache_key = f"file_{file_path}"
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return cached_result
            
        file_result = {}
        func_count = 0
        line_count = 0
        
        try:
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
                line_count = len(lines)
                
            # 提取函数
            for func_text in self._extract_functions(content):
                # 处理函数文本
                func_text = self._remove_comments(func_text)
                func_text = self._normalize_code(func_text)
                
                # 计算TLSH哈希
                func_hash = self._compute_tlsh(func_text)
                if not func_hash:
                    continue
                    
                # 存储结果
                stored_path = file_path.replace(repo_path, "")
                if func_hash not in file_result:
                    file_result[func_hash] = []
                file_result[func_hash].append(stored_path)
                func_count += 1
                
            result = (file_result, 1, func_count, line_count)
            self.cache.set(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"处理文件失败 {file_path}: {str(e)}")
            return {}, 0, 0, 0
            
    def _extract_functions(self, content: str) -> List[str]:
        """从代码中提取函数"""
        functions = []
        # 使用正则表达式提取函数
        func_pattern = re.compile(r'\w+\s+\w+\s*\([^)]*\)\s*{[^}]*}')
        matches = func_pattern.finditer(content)
        for match in matches:
            functions.append(match.group())
        return functions
        
    def _remove_comments(self, code: str) -> str:
        """移除代码中的注释"""
        # 移除单行注释
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        # 移除多行注释
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        return code
        
    def _normalize_code(self, code: str) -> str:
        """标准化代码"""
        code = code.replace('\n', '')
        code = code.replace('\r', '')
        code = code.replace('\t', '')
        code = code.replace('{', '')
        code = code.replace('}', '')
        code = ''.join(code.split())
        return code.lower()
        
    def _compute_tlsh(self, text: str) -> Optional[str]:
        """计算TLSH哈希值"""
        try:
            hash_val = tlsh.hash(text.encode())
            if len(hash_val) == 72 and hash_val.startswith("T1"):
                return hash_val[2:]
            return None
        except:
            return None
            
    def process_component(self, component_info: Tuple) -> Optional[str]:
        """处理单个组件
        
        Args:
            component_info: (组件名, 输入函数字典, 输入仓库名, 平均函数数)
            
        Returns:
            Optional[str]: 检测结果
        """
        oss, input_dict, input_repo, ave_funcs = component_info
        
        try:
            repo_name = oss.split('_sig')[0]
            tot_oss_funcs = float(ave_funcs[repo_name])
            
            if tot_oss_funcs == 0.0:
                return None
                
            # 计算共同函数
            common_funcs = []
            com_oss_funcs = 0.0
            
            for hash_val in self.component_db[oss]:
                if hash_val in input_dict:
                    common_funcs.append(hash_val)
                    com_oss_funcs += 1.0
                    
            # 检查相似度
            if (com_oss_funcs/tot_oss_funcs) >= self.theta:
                # 预测版本
                ver_predict = self._predict_version(repo_name, common_funcs)
                
                # 分析函数使用情况
                used, unused, modified, str_change = self._analyze_usage(
                    repo_name, ver_predict, input_dict
                )
                
                # 返回结果
                return '\t'.join([
                    input_repo, repo_name, ver_predict,
                    str(used), str(unused), str(modified),
                    str(str_change)
                ])
                
            return None
            
        except Exception as e:
            logger.error(f"处理组件失败 {oss}: {str(e)}")
            return None
            
    def _predict_version(self, repo_name: str, common_funcs: List[str]) -> str:
        """预测版本"""
        # 读取版本信息
        all_vers, idx2ver = self._read_versions(repo_name)
        
        # 初始化版本预测权重
        ver_predict = {ver: 0.0 for ver in all_vers}
        
        # 读取权重信息
        weights = self._read_weights(repo_name)
        
        # 计算版本得分
        with open(os.path.join(self.initial_db_path, f"{repo_name}_sig"), 'r') as f:
            json_data = json.load(f)
            for hash_entry in json_data:
                hash_val = hash_entry["hash"]
                ver_list = hash_entry["vers"]
                
                if hash_val in common_funcs:
                    for ver_idx in ver_list:
                        ver = idx2ver[ver_idx]
                        ver_predict[ver] += weights.get(hash_val, 1.0)
                        
        # 返回得分最高的版本
        return max(ver_predict.items(), key=lambda x: x[1])[0]
        
    def _read_versions(self, repo_name: str) -> Tuple[List[str], Dict[str, str]]:
        """读取版本信息"""
        all_vers = []
        idx2ver = {}
        
        ver_file = os.path.join(self.ver_idx_path, f"{repo_name}_idx")
        with open(ver_file, 'r') as f:
            ver_data = json.load(f)
            for ver_entry in ver_data:
                all_vers.append(ver_entry["ver"])
                idx2ver[ver_entry["idx"]] = ver_entry["ver"]
                
        return all_vers, idx2ver
        
    def _read_weights(self, repo_name: str) -> Dict[str, float]:
        """读取权重信息"""
        weight_file = os.path.join(self.weight_path, f"{repo_name}_weights")
        with open(weight_file, 'r') as f:
            return json.load(f)
            
    def _analyze_usage(
        self, 
        repo_name: str, 
        version: str, 
        input_dict: Dict[str, List[str]]
    ) -> Tuple[int, int, int, bool]:
        """分析函数使用情况"""
        used = 0
        unused = 0
        modified = 0
        str_change = False
        
        # 读取预测版本的函数信息
        ver_file = os.path.join(
            self.repo_func_path,
            repo_name,
            f"fuzzy_{version}.hidx"
        )
        
        with open(ver_file, 'r') as f:
            next(f)  # 跳过标题行
            for line in f:
                if not line.strip():
                    continue
                    
                parts = line.strip().split('\t')
                hash_val = parts[0]
                paths = parts[1:]
                
                # 检查函数使用情况
                if hash_val in input_dict:
                    used += 1
                    # 检查结构变化
                    if not any(p in t for p in paths for t in input_dict[hash_val]):
                        str_change = True
                else:
                    # 检查修改的函数
                    modified_found = False
                    for in_hash in input_dict:
                        if tlsh.diff(hash_val, in_hash) <= self.tlsh_threshold:
                            modified += 1
                            modified_found = True
                            # 检查结构变化
                            if not any(p in t for p in paths for t in input_dict[in_hash]):
                                str_change = True
                            break
                            
                    if not modified_found:
                        unused += 1
                        
        return used, unused, modified, str_change
        
    def process_files_parallel(self, files: List[Tuple[str, str]]) -> Dict[str, List[str]]:
        """并行处理文件
        
        Args:
            files: 文件信息列表，每项为(文件路径, 仓库路径)元组
            
        Returns:
            处理结果字典
        """
        def process_file_chunk(chunk: List[Tuple[str, str]]) -> Dict[str, List[str]]:
            result = {}
            for file_path, repo_path in chunk:
                try:
                    file_result, _, _, _ = self.process_file(file_path, repo_path)
                    result.update(file_result)
                except Exception as e:
                    logger.error(f"处理文件失败 {file_path}: {str(e)}")
            return result
            
        return self.parallel_manager.process_items(
            items=files,
            process_func=process_file_chunk,
            pool_name="file_processor"
        )
        
    def process_components_parallel(self, components: List[Tuple[str, Dict, str, Dict]]) -> List[str]:
        """并行处理组件
        
        Args:
            components: 组件信息列表，每项为(组件名, 输入函数字典, 输入仓库名, 平均函数数)元组
            
        Returns:
            检测结果列表
        """
        def process_component_chunk(chunk: List[Tuple[str, Dict, str, Dict]]) -> List[str]:
            results = []
            for component_info in chunk:
                try:
                    result = self.process_component(component_info)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"处理组件失败: {str(e)}")
            return results
            
        return self.parallel_manager.process_items(
            items=components,
            process_func=process_component_chunk,
            pool_name="component_processor"
        )
        
    def detect(self, input_path: str, input_repo: str):
        """执行代码克隆检测
        
        Args:
            input_path: 输入代码路径
            input_repo: 输入仓库名
        """
        logger.info(f"开始检测仓库: {input_repo}")
        
        try:
            # 收集C/C++文件
            cpp_files = []
            for root, _, files in os.walk(input_path):
                for file in files:
                    if file.endswith(('.c', '.cc', '.cpp', '.h', '.hpp')):
                        cpp_files.append((
                            os.path.join(root, file),
                            input_path
                        ))
                        
            # 并行处理文件
            input_dict = self.process_files_parallel(cpp_files)
            
            # 准备组件处理任务
            components = [
                (oss, input_dict, input_repo, self.ave_funcs)
                for oss in self.component_db
            ]
            
            # 并行处理组件
            results = self.process_components_parallel(components)
            
            # 写入结果
            result_file = os.path.join(self.result_path, f"result_{input_repo}")
            with open(result_file, 'w') as f:
                for result in results:
                    f.write(f"{result}\n")
                    
            logger.info(f"检测完成: {input_repo}")
            
        except Exception as e:
            logger.error(f"检测失败: {str(e)}")
        finally:
            self.cleanup()
            
    def cleanup(self):
        """清理资源"""
        self.resource_manager.close_all()
        self.parallel_manager.close_all()
        self.cache.clear()

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("Usage: python detector.py <input_path>")
        sys.exit(1)
        
    input_path = sys.argv[1]
    input_repo = os.path.basename(input_path)
    
    detector = Detector()
    detector.detect(input_path, input_repo)

if __name__ == "__main__":
    main()
