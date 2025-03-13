"""开源软件收集器模块

该模块用于收集和处理开源代码库中的函数信息。主要功能包括:
1. 遍历本地Git仓库中的源代码文件
2. 提取函数信息
3. 计算函数的TLSH哈希值
4. 生成函数索引文件
5. 管理仓库版本和标签

作者: Re-Centris团队
版本: 1.0.0
许可证: MIT
"""

import os
import sys
import subprocess
import re
import tlsh
import datetime
import time
import json
import hashlib
import traceback
import gc
import argparse
from concurrent.futures import as_completed
from typing import Dict, Tuple, List, Set, Optional, Any, Generator
from pathlib import Path

# 导入核心模块
from core.config_manager import ConfigManager
from core.cache import Cache
from core.resource_manager import ResourceManager, safe_open
from core.memory_optimizer import MemoryOptimizer
from core.performance_monitor import PerformanceMonitor, ProgressBar
from core.logger import setup_logger, get_module_logger

# 获取模块日志记录器
logger = get_module_logger("osscollector")


class Collector:
    """开源软件收集器，用于收集和处理开源代码库中的函数信息"""
    
    def __init__(self, config_file: Optional[str] = None):
        """初始化收集器
        
        Args:
            config_file: 配置文件路径，如果为None则使用默认配置
        """
        # 加载配置
        self.config = ConfigManager(config_file)
        
        # 创建必要的目录
        self.config.create_required_directories()
        
        # 设置日志
        log_file = os.path.join(
            self.config.get_path("log_path"),
            f"collector_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        self.logger = setup_logger(
            "re-centris.osscollector",
            log_file,
            self.config.get("logging", "level", "INFO"),
            self.config.get("logging", "max_size", 10 * 1024 * 1024),
            self.config.get("logging", "backup_count", 5)
        )
        
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
        
        # 创建性能监控器
        self.performance_monitor = PerformanceMonitor("collector")
        
        # 获取支持的语言配置
        self.supported_languages = {}
        languages_config = self.config.get("languages", {})
        for lang, lang_config in languages_config.items():
            if lang_config.get("enabled", False):
                self.supported_languages[lang] = lang_config.get("extensions", [])
        
        # 如果没有启用任何语言，默认启用C/C++
        if not self.supported_languages:
            self.supported_languages["cpp"] = [".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"]
        
        # 获取ctags路径
        self.ctags_path = self.config.get("external_tools", "ctags_path", "ctags")
    
    def is_supported_file(self, filename: str) -> bool:
        """检查文件是否为支持的源文件
        
        Args:
            filename: 文件名
        
        Returns:
            是否为支持的源文件
        """
        ext = os.path.splitext(filename)[1].lower()
        
        for extensions in self.supported_languages.values():
            if ext in extensions:
                return True
        
        return False
    
    def get_file_hash(self, filepath: str) -> str:
        """计算文件MD5哈希值
        
        Args:
            filepath: 文件路径
        
        Returns:
            MD5哈希值
        """
        hasher = hashlib.md5()
        
        try:
            with open(filepath, 'rb') as f:
                buf = f.read(65536)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(65536)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希值失败 {filepath}: {e}")
            return ""
    
    def compute_tlsh(self, string: str) -> str:
        """使用TLSH算法计算输入字符串的哈希值
        
        Args:
            string: 输入字符串
        
        Returns:
            TLSH哈希值
        
        Raises:
            ValueError: 输入字符串为空
        """
        if not string:
            raise ValueError("输入字符串为空")
        
        string = str.encode(string)
        try:
            hs = tlsh.forcehash(string)
            return hs
        except Exception as e:
            logger.error(f"TLSH哈希计算失败: {e}")
            return ""
    
    def remove_comment(self, string: str) -> str:
        """删除C/C++风格的注释
        
        Args:
            string: 输入代码字符串
        
        Returns:
            删除注释后的代码
        """
        try:
            c_regex = re.compile(
                r'(?P<comment>//.*?$|[{}]+)|'
                r'(?P<multilinecomment>/\*.*?\*/)|'
                r'(?P<noncomment>\'(\\.|[^\\\'])*\'|"(\\.|[^\\"])*"|.[^/\'"]*)',
                re.DOTALL | re.MULTILINE
            )
            return ''.join([c.group('noncomment') for c in c_regex.finditer(string) if c.group('noncomment')])
        except Exception as e:
            logger.error(f"删除注释失败: {e}")
            return string
    
    def normalize(self, string: str) -> str:
        """规范化输入字符串
        
        Args:
            string: 输入字符串
        
        Returns:
            规范化后的字符串
        """
        try:
            return ''.join(
                string.replace('\n', '')
                    .replace('\r', '')
                    .replace('\t', '')
                    .replace('{', '')
                    .replace('}', '')
                    .split(' ')
            ).lower()
        except Exception as e:
            logger.error(f"规范化字符串失败: {e}")
            return string
    
    def read_file_safely(self, file_path: str) -> str:
        """安全地读取文件内容
        
        Args:
            file_path: 文件路径
        
        Returns:
            文件内容
        """
        if not os.path.exists(file_path):
            logger.warning(f"文件不存在: {file_path}")
            return ""
        
        # 常见编码优先级排序
        primary_encodings = ['utf-8', 'ascii', 'gb18030', 'latin-1']
        
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # 尝试常见编码
            for encoding in primary_encodings:
                try:
                    return content.decode(encoding)
                except UnicodeDecodeError:
                    continue
            
            # 尝试使用chardet
            try:
                import chardet
                detected = chardet.detect(content)
                if detected['confidence'] > 0.7:
                    try:
                        return content.decode(detected['encoding'])
                    except:
                        pass
            except ImportError:
                pass
            
            # 最后使用latin-1
            return content.decode('latin-1', errors='ignore')
                
        except IOError as e:
            logger.error(f"读取文件IO错误 {file_path}: {e}")
            return ""
        except Exception as e:
            logger.error(f"读取文件未知错误 {file_path}: {e}")
            return ""
    
    def process_single_file(self, file_path: str, base_path: str) -> Tuple[List[Tuple[str, str]], int, int, int]:
        """处理单个文件并返回结果
        
        Args:
            file_path: 文件路径
            base_path: 基础路径
        
        Returns:
            哈希值和文件路径对的列表, 文件数(0或1), 函数数, 代码行数
        """
        try:
            # 检查缓存
            file_hash = self.get_file_hash(file_path)
            cached_result = self.cache.get(file_hash)
            if cached_result is not None:
                return cached_result
            
            func_count = 0
            results = []
            
            content = self.read_file_safely(file_path)
            if not content:
                return [], 0, 0, 0
            
            lines = content.splitlines()
            line_count = len(lines)
            
            # 使用ctags提取函数信息
            try:
                timeout = self.config.get("performance", "timeout", 30)
                functionList = subprocess.check_output(
                    f'{self.ctags_path} -f - --kinds-C=* --fields=neKSt "{file_path}"',
                    stderr=subprocess.STDOUT,
                    shell=True,
                    timeout=timeout
                ).decode()
            except subprocess.TimeoutExpired:
                logger.warning(f"处理文件超时: {file_path}")
                return [], 0, 0, 0
            except Exception as e:
                logger.error(f"执行ctags失败: {e}")
                return [], 0, 0, 0
            
            # 预编译正则表达式
            func_pattern = re.compile(r'(function)')
            number_pattern = re.compile(r'(\d+)')
            func_search_pattern = re.compile(r'{([\S\s]*)}')
            
            # 处理函数列表
            functions = []
            for i in str(functionList).split('\n'):
                if not i:
                    continue
                    
                elemList = re.sub(r'[\t\s ]{2,}', '', i).split('\t')
                if len(elemList) >= 8 and func_pattern.fullmatch(elemList[3]):
                    functions.append((
                        int(number_pattern.search(elemList[4]).group(0)),
                        int(number_pattern.search(elemList[7]).group(0))
                    ))
            
            # 处理函数体
            for start_line, end_line in functions:
                try:
                    tmp_string = ''.join(lines[start_line - 1 : end_line])
                    
                    match = func_search_pattern.search(tmp_string)
                    if not match:
                        continue
                    
                    func_body = match.group(1)
                    func_body = self.remove_comment(func_body)
                    func_body = self.normalize(func_body)
                    func_hash = self.compute_tlsh(func_body)
                    
                    if len(func_hash) == 72 and func_hash.startswith("T1"):
                        func_hash = func_hash[2:]
                    elif func_hash in ("TNULL", "", "NULL"):
                        continue
                    
                    stored_path = file_path.replace(base_path, "")
                    results.append((func_hash, stored_path))
                    func_count += 1
                    
                except Exception as e:
                    logger.warning(f"处理函数时出错: {e}")
                    continue
            
            result = (results, 1, func_count, line_count)
            self.cache.put(file_hash, result)
            return result
            
        except Exception as e:
            logger.error(f"处理文件时出错 {file_path}: {e}")
            return [], 0, 0, 0
    
    def hashing(self, repo_path: str) -> Tuple[Dict, int, int, int]:
        """并行处理仓库中的所有源文件
        
        Args:
            repo_path: 仓库路径
        
        Returns:
            结果字典, 文件数, 函数数, 代码行数
        """
        result_dict = {}
        
        # 收集需要处理的文件
        files_to_process = []
        for path, _, files in os.walk(repo_path):
            for file in files:
                if self.is_supported_file(file):
                    files_to_process.append(os.path.join(path, file))
        
        file_count = 0
        func_count = 0
        line_count = 0
        
        # 创建进度条
        progress = ProgressBar(len(files_to_process), prefix='处理文件:', suffix='完成')
        
        # 获取最大工作进程数
        max_workers = self.config.get("performance", "max_workers")
        if max_workers is None:
            max_workers = os.cpu_count()
        
        # 使用进程池处理文件
        with self.resource_manager.get_process_pool("file_processor", max_workers) as executor:
            future_to_file = {
                executor.submit(self.process_single_file, f, repo_path): f 
                for f in files_to_process
            }
            
            for future in as_completed(future_to_file):
                try:
                    results, f_cnt, fn_cnt, ln_cnt = future.result()
                    
                    # 合并结果
                    for func_hash, file_path in results:
                        if func_hash not in result_dict:
                            result_dict[func_hash] = []
                        result_dict[func_hash].append(file_path)
                    
                    file_count += f_cnt
                    func_count += fn_cnt
                    line_count += ln_cnt
                    
                    # 更新进度
                    progress.update()
                    
                    # 更新性能监控
                    self.performance_monitor.update()
                    
                except Exception as e:
                    logger.error(f"处理文件时发生错误: {e}")
        
        return result_dict, file_count, func_count, line_count
    
    def indexing(self, res_dict: Dict, title: str, file_path: str) -> None:
        """为每个OSS建立索引并写入文件
        
        Args:
            res_dict: 结果字典
            title: 标题行
            file_path: 输出文件路径
        """
        try:
            with safe_open(file_path, 'w') as fres:
                fres.write(title + '\n')
                
                for hashval in res_dict:
                    if not hashval or hashval.isspace():
                        continue
                    
                    fres.write(hashval)
                    
                    for funcPath in res_dict[hashval]:
                        fres.write('\t' + funcPath)
                    fres.write('\n')
        except IOError as e:
            logger.error(f"写入索引文件失败: {e}")
            raise
    
    def get_repo_paths(self, base_path: str) -> List[str]:
        """获取所有仓库路径
        
        Args:
            base_path: 基础路径
        
        Returns:
            仓库路径列表
        """
        repo_paths = []
        try:
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path):
                    if '%' in item:
                        sub_items = os.listdir(item_path)
                        if len(sub_items) == 1 and os.path.isdir(os.path.join(item_path, sub_items[0])):
                            repo_paths.append(os.path.join(item_path, sub_items[0]))
                        else:
                            repo_paths.append(item_path)
                    else:
                        repo_paths.append(item_path)
        except OSError as e:
            logger.error(f"获取仓库路径失败: {e}")
            raise
            
        return repo_paths
    
    def process_single_repo(self, repo_path: str) -> None:
        """处理单个仓库
        
        Args:
            repo_path: 仓库路径
        """
        repo_name = os.path.basename(os.path.dirname(repo_path))
        if '%' not in repo_name:
            repo_name = os.path.basename(repo_path)
            
        logger.info(f"正在处理 {repo_name}")
        
        try:
            os.chdir(repo_path)
            
            # 获取标签日期
            date_command = 'git log --tags --simplify-by-decoration --pretty="format:%ai %d"'
            date_result = subprocess.check_output(date_command, stderr=subprocess.STDOUT, shell=True).decode()
            
            tag_date_file = os.path.join(self.config.get_path("tag_date_path"), repo_name)
            with safe_open(tag_date_file, 'w') as f:
                f.write(str(date_result))
            
            # 获取所有标签
            tag_command = "git tag"
            tag_result = subprocess.check_output(tag_command, stderr=subprocess.STDOUT, shell=True).decode()
            
            res_dict = {}
            file_cnt = 0
            func_cnt = 0
            line_cnt = 0
            
            # 处理仓库
            if not tag_result:
                # 处理主分支
                res_dict, file_cnt, func_cnt, line_cnt = self.hashing(repo_path)
                if res_dict:
                    result_repo_path = os.path.join(self.config.get_path("result_path"), repo_name)
                    if not os.path.isdir(result_repo_path):
                        os.makedirs(result_repo_path)
                        
                    title = '\t'.join([repo_name, str(file_cnt), str(func_cnt), str(line_cnt)])
                    result_file_path = os.path.join(result_repo_path, f'fuzzy_{repo_name}.hidx')
                    
                    self.indexing(res_dict, title, result_file_path)
            else:
                # 处理每个标签
                for tag in str(tag_result).split('\n'):
                    if tag:
                        try:
                            cleaned_tag = tag.strip().replace('"', '').replace("'", '')
                            checkout_command = ['git', 'checkout', '-f', cleaned_tag]
                            subprocess.run(
                                checkout_command, 
                                check=True,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE
                            )
                            
                            res_dict, file_cnt, func_cnt, line_cnt = self.hashing(repo_path)
                            
                            if res_dict:
                                result_repo_path = os.path.join(self.config.get_path("result_path"), repo_name)
                                if not os.path.isdir(result_repo_path):
                                    os.makedirs(result_repo_path)
                                    
                                title = '\t'.join([repo_name, str(file_cnt), str(func_cnt), str(line_cnt)])
                                result_file_path = os.path.join(result_repo_path, f'fuzzy_{tag}.hidx')
                                
                                self.indexing(res_dict, title, result_file_path)
                                
                        except subprocess.CalledProcessError as e:
                            logger.warning(f"切换到标签 {tag} 失败: {e.stderr.decode('utf-8', errors='ignore')}")
                            continue
                            
            logger.info(f"处理完成 {repo_name}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git命令执行失败: {e}")
            raise
        except Exception as e:
            logger.error(f"处理仓库失败: {e}")
            raise
    
    def process_repo_batch(self, repos: List[str]) -> None:
        """处理一批仓库
        
        Args:
            repos: 仓库路径列表
        """
        for repo_path in repos:
            try:
                start_time = time.time()
                
                self.process_single_repo(repo_path)
                
                # 更新性能监控
                elapsed = time.time() - start_time
                self.performance_monitor.update(1, elapsed)
                
            except Exception as e:
                logger.error(f"处理仓库失败 {repo_path}: {e}")
                continue
    
    def run(self) -> None:
        """运行收集器"""
        try:
            # 获取仓库路径
            repo_path = self.config.get_path("repo_path")
            repo_paths = self.get_repo_paths(repo_path)
            
            logger.info(f"找到 {len(repo_paths)} 个仓库")
            
            # 分批处理仓库
            for batch in self.memory_optimizer.batch_items(repo_paths):
                self.process_repo_batch(batch)
                
        except Exception as e:
            logger.error(f"程序执行失败: {e}")
            logger.error(traceback.format_exc())
            sys.exit(1)
        finally:
            # 保存性能报告
            report_file = os.path.join(
                self.config.get_path("log_path"),
                f"collector_performance_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            self.performance_monitor.save_report(report_file)
            
            # 清理资源
            self.resource_manager.close_all()
            self.cache.clear()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Re-Centris 开源软件收集器')
    parser.add_argument('-c', '--config', help='配置文件路径')
    args = parser.parse_args()
    
    collector = Collector(args.config)
    collector.run()


if __name__ == "__main__":
    main() 