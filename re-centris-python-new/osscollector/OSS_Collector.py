"""开源软件收集器模块 - 用于收集和处理开源代码库中的函数信息。该模块实现了基于TLSH(Trend Micro Locality Sensitive Hash)的代码函数收集和哈希处理。主要功能包括:1.遍历本地Git仓库中的源代码文件 2.提取C/C++函数信息 3.计算函数的TLSH哈希值 4.生成函数索引文件 5.管理仓库版本和标签。主要类和函数: Cache:缓存管理, ResourceManager:资源管理, MemoryOptimizer:内存优化, PerformanceMonitor:性能监控, process_single_file:处理单个文件, hashing:处理源代码文件并生成哈希, indexing:生成索引文件。作者:byRen2002 修改日期:2024年10月20日 许可证:MIT License"""

import os
import sys
import subprocess
import re
import tlsh
import datetime
import time
import json
import psutil
import threading
import multiprocessing
import logging
import signal
import shutil
import hashlib
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Dict, Tuple, List, Set, Optional, Any
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from collections import defaultdict
import traceback
import pickle
import gc
from contextlib import contextmanager
from typing import Optional, Any, Dict, List, Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

"""全局配置和路径定义"""
# 基础路径配置
current_path = "/home/rby/Project/project-file/dependency_analysis/centris"
repo_path = "/home/rby/Project/project-file/dependency_analysis/repo_src"
tag_date_path = "/home/rby/Project/project-file/dependency_analysis/centris/OSS_Collector/repo_date/"
result_path = "/home/rby/Project/project-file/dependency_analysis/centris/OSS_Collector/repo_functions/"
log_path = "/home/rby/Project/project-file/dependency_analysis/centris/logs/OSS_Collector"
ctags_path = "/usr/local/bin/ctags"
cache_path = "/home/rby/Project/project-file/dependency_analysis/centris/OSS_Collector/cache/"

# 性能相关配置
max_workers = multiprocessing.cpu_count()  # 最大工作进程数
log_max_size = 10 * 1024 * 1024  # 日志文件最大大小(10MB)
log_backup_count = 5  # 日志文件备份数量
timeout = 30  # 超时时间(秒)
cache_size = 1000  # 缓存大小
memory_limit = 0.9  # 内存使用限制(90%)

# 创建必要的目录
required_dirs = [
    log_path,
    result_path,
    tag_date_path,
    cache_path
]

for directory in required_dirs:
    if not os.path.isdir(directory):
        try:
            os.makedirs(directory)
            logging.info(f"创建目录: {directory}")
        except Exception as e:
            logging.error(f"创建目录 {directory} 失败: {e}")

# 生成日志文件名，包含时间戳
log_file = os.path.join(log_path, f"collector_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),  # 文件处理器
        logging.StreamHandler()  # 控制台处理器
    ]
)

class Cache:
    """简单的LRU缓存实现"""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._cache = {}
        self._history = []
        self._lock = threading.Lock()
        
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key in self._cache:
                self._history.remove(key)
                self._history.append(key)
                return self._cache[key]
            return None
            
    def put(self, key: str, value: Any) -> None:
        """存入缓存值"""
        with self._lock:
            if key in self._cache:
                self._history.remove(key)
            elif len(self._cache) >= self.capacity:
                oldest = self._history.pop(0)
                del self._cache[oldest]
                
            self._cache[key] = value
            self._history.append(key)
            
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._history.clear()

class ResourceManager:
    """基础资源管理器"""
    
    def __init__(self, max_workers: int):
        self.max_workers = max_workers
        self._files = {}
        self._process_pool = None
        
    def __enter__(self):
        self._process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        
    def get_file(self, path: str, mode: str = 'r') -> Any:
        """获取文件句柄"""
        if path not in self._files:
            self._files[path] = open(path, mode)
        return self._files[path]
        
    def close_file(self, path: str) -> None:
        """关闭文件句柄"""
        if path in self._files:
            self._files[path].close()
            del self._files[path]
            
    @property
    def process_pool(self) -> ProcessPoolExecutor:
        """获取进程池"""
        if not self._process_pool:
            self._process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
        return self._process_pool
        
    def cleanup(self) -> None:
        """清理所有资源"""
        for f in self._files.values():
            f.close()
        self._files.clear()
        
        if self._process_pool:
            self._process_pool.shutdown()
            self._process_pool = None

class MemoryOptimizer:
    """基本内存优化器"""
    
    def __init__(self, target_memory_usage: float = 0.8):
        self.target_memory_usage = target_memory_usage
        self.current_batch_size = 1000
        self._process = psutil.Process()
        
    def get_memory_usage(self) -> float:
        """获取当前内存使用率"""
        return self._process.memory_percent() / 100
        
    def should_gc(self) -> bool:
        """判断是否需要GC"""
        return self.get_memory_usage() > self.target_memory_usage
        
    def optimize(self) -> None:
        """执行内存优化"""
        if self.should_gc():
            gc.collect()
            
    def batch_items(self, items: List[Any]) -> Generator[List[Any], None, None]:
        """分批处理数据"""
        for i in range(0, len(items), self.current_batch_size):
            batch = items[i:i + self.current_batch_size]
            yield batch
            
            # 根据内存使用调整批大小
            memory_usage = self.get_memory_usage()
            if memory_usage > self.target_memory_usage:
                self.current_batch_size = int(self.current_batch_size * 0.8)
            elif memory_usage < self.target_memory_usage * 0.7:
                self.current_batch_size = int(self.current_batch_size * 1.2)
                
            self.optimize()

class PerformanceMonitor:
    """基本性能监控器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.processed_items = 0
        self.last_log_time = self.start_time
        
    def update(self, items: int = 1) -> None:
        """更新处理项数并记录性能指标"""
        self.processed_items += items
        current_time = time.time()
        
        # 每60秒记录一次性能指标
        if current_time - self.last_log_time >= 60:
            elapsed = current_time - self.start_time
            rate = self.processed_items / elapsed
            
            logging.info(f"性能统计:")
            logging.info(f"- 总处理项数: {self.processed_items}")
            logging.info(f"- 运行时间: {elapsed:.2f}秒")
            logging.info(f"- 处理速率: {rate:.2f}项/秒")
            
            self.last_log_time = current_time

# 工具函数
def is_cpp_file(filename: str) -> bool:
    """检查是否为C/C++源文件"""
    return filename.endswith(('.c', '.cc', '.cpp', '.cxx', '.h', '.hpp'))

def get_file_hash(filepath: str) -> str:
    """计算文件MD5哈希值"""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def computeTlsh(string: str) -> str:
    """使用TLSH算法计算输入字符串的哈希值。参数:string:输入字符串。返回:str:TLSH哈希值。异常:ValueError:输入字符串为空"""
    if not string:
        raise ValueError("Empty input string")
        
    string = str.encode(string)
    try:
        hs = tlsh.forcehash(string)
        return hs
    except Exception as e:
        logging.error(f"TLSH hash computation failed: {str(e)}")
        return ""

def removeComment(string: str) -> str:
    """删除C/C++风格的注释。参数:string:输入代码字符串。返回:str:删除注释后的代码"""
    c_regex = re.compile(
        r'(?P<comment>//.*?$|[{}]+)|'
        r'(?P<multilinecomment>/\*.*?\*/)|'
        r'(?P<noncomment>\'(\\.|[^\\\'])*\'|"(\\.|[^\\"])*"|.[^/\'"]*)',
        re.DOTALL | re.MULTILINE
    )
    return ''.join([c.group('noncomment') for c in c_regex.finditer(string) if c.group('noncomment')])

def normalize(string: str) -> str:
    """规范化输入字符串。参数:string:输入字符串。返回:str:规范化后的字符串"""
    return ''.join(
        string.replace('\n', '')
              .replace('\r', '')
              .replace('\t', '')
              .replace('{', '')
              .replace('}', '')
              .split(' ')
    ).lower()

def read_file_safely(file_path: str) -> str:
    """安全地读取文件内容。参数:file_path:文件路径。返回:str:文件内容。异常:IOError:文件读取错误"""
    if not os.path.exists(file_path):
        logging.warning(f"文件不存在: {file_path}")
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
        logging.error(f"读取文件IO错误 {file_path}: {str(e)}")
        return ""
    except Exception as e:
        logging.error(f"读取文件未知错误 {file_path}: {str(e)}")
        return ""

def process_single_file(file_path: str, base_path: str, cache: Cache) -> Tuple[List[Tuple[str, str]], int, int, int]:
    """处理单个文件并返回结果。参数:file_path:文件路径,base_path:基础路径,cache:缓存对象。返回:Tuple[List[Tuple[str, str]], int, int, int]:哈希值和文件路径对的列表,文件数(0或1),函数数,代码行数"""
    try:
        # 检查缓存
        file_hash = get_file_hash(file_path)
        cached_result = cache.get(file_hash)
        if cached_result is not None:
            return cached_result

        func_count = 0
        results = []
        
        content = read_file_safely(file_path)
        if not content:
            return [], 0, 0, 0

        lines = content.splitlines()
        line_count = len(lines)

        # 使用ctags提取函数信息
        try:
            functionList = subprocess.check_output(
                f'{ctags_path} -f - --kinds-C=* --fields=neKSt "{file_path}"',
                stderr=subprocess.STDOUT,
                shell=True,
                timeout=30
            ).decode()
        except subprocess.TimeoutExpired:
            logging.warning(f"处理文件超时: {file_path}")
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
                func_body = removeComment(func_body)
                func_body = normalize(func_body)
                func_hash = computeTlsh(func_body)

                if len(func_hash) == 72 and func_hash.startswith("T1"):
                    func_hash = func_hash[2:]
                elif func_hash in ("TNULL", "", "NULL"):
                    continue

                stored_path = file_path.replace(base_path, "")
                results.append((func_hash, stored_path))
                func_count += 1

            except Exception as e:
                logging.warning(f"处理函数时出错: {str(e)}")
                continue

        result = (results, 1, func_count, line_count)
        cache.put(file_hash, result)
        return result

    except Exception as e:
        logging.error(f"处理文件时出错 {file_path}: {str(e)}")
        return [], 0, 0, 0

def hashing(repo_path: str, cache: Cache) -> Tuple[Dict, int, int, int]:
    """并行处理仓库中的所有C/C++文件。参数:repo_path:仓库路径,cache:缓存对象。返回:Tuple[Dict, int, int, int]:结果字典,文件数,函数数,代码行数"""
    possible = (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp")
    result_dict = defaultdict(list)
    
    # 收集需要处理的文件
    files_to_process = set()
    for path, _, files in os.walk(repo_path):
        files_to_process.update(
            os.path.join(path, file)
            for file in files
            if file.endswith(possible)
        )
    
    file_count = 0
    func_count = 0
    line_count = 0
    
    # 创建进度条
    progress = ProgressBar(len(files_to_process), prefix='Processing files:', suffix='Complete')
    
    # 使用进程池处理文件
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(process_single_file, f, repo_path, cache): f 
            for f in files_to_process
        }
        
        for future in as_completed(future_to_file):
            try:
                results, f_cnt, fn_cnt, ln_cnt = future.result()
                
                # 合并结果
                for func_hash, file_path in results:
                    result_dict[func_hash].append(file_path)
                
                file_count += f_cnt
                func_count += fn_cnt
                line_count += ln_cnt
                
                # 更新进度
                progress.update()
                
            except Exception as e:
                logging.error(f"处理文件时发生错误: {str(e)}")
    
    return result_dict, file_count, func_count, line_count

def indexing(resDict: Dict, title: str, filePath: str) -> None:
    """为每个OSS建立索引并写入文件。参数:resDict:结果字典,title:标题行,filePath:输出文件路径"""
    try:
        with open(filePath, 'w') as fres:
            fres.write(title + '\n')

            for hashval in resDict:
                if not hashval or hashval.isspace():
                    continue

                fres.write(hashval)
                
                for funcPath in resDict[hashval]:
                    fres.write('\t' + funcPath)
                fres.write('\n')
    except IOError as e:
        logging.error(f"写入索引文件失败: {str(e)}")
        raise

def get_repo_paths(base_path: str) -> List[str]:
    """获取所有仓库路径。参数:base_path:基础路径。返回:List[str]:仓库路径列表"""
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
    except OSError as e:
        logging.error(f"获取仓库路径失败: {str(e)}")
        raise
        
    return repo_paths

def main() -> None:
    """主函数,处理指定目录下的所有Git仓库"""
    try:
        # 创建资源管理器
        with ResourceManager(max_workers=multiprocessing.cpu_count()) as rm:
            # 创建缓存
            cache = Cache(cache_size)
            
            # 创建内存优化器
            memory_optimizer = MemoryOptimizer()
            
            # 创建性能监控器
            monitor = PerformanceMonitor()
            
            try:
                # 获取仓库路径
                repo_paths = get_repo_paths(repo_path)
                
                # 分批处理仓库
                for batch in memory_optimizer.batch_items(repo_paths):
                    process_repo_batch(batch, rm, cache, monitor)
                    
            except Exception as e:
                logging.error(f"处理仓库时出错: {e}")
                
    except Exception as e:
        logging.error(f"程序执行失败: {e}")
        logging.error(traceback.format_exc())
        sys.exit(1)

def process_repo_batch(
    repos: List[str],
    rm: ResourceManager,
    cache: Cache,
    monitor: PerformanceMonitor
) -> None:
    """处理一批仓库"""
    for repo_path in repos:
        try:
            start_time = time.time()
            
            process_single_repo(repo_path, rm, cache)
            
            # 更新性能监控
            monitor.update()
            
        except Exception as e:
            logging.error(f"处理仓库失败 {repo_path}: {e}")
            continue

# 1. 添加ProgressBar类定义
class ProgressBar:
    """显示处理进度"""
    
    def __init__(self, total: int, prefix: str = '', suffix: str = ''):
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.current = 0
        self._lock = threading.Lock()

    def update(self, n: int = 1) -> None:
        """更新进度"""
        with self._lock:
            self.current += n
            percentage = 100 * (self.current / float(self.total))
            filled = int(50 * self.current // self.total)
            bar = '=' * filled + '-' * (50 - filled)
            print(f'\r{self.prefix} |{bar}| {percentage:.1f}% {self.suffix}', end='')
            if self.current == self.total:
                print()

# 2. 添加process_single_repo函数定义
def process_single_repo(repo_path: str, rm: ResourceManager, cache: Cache) -> None:
    """处理单个仓库"""
    repo_name = os.path.basename(os.path.dirname(repo_path))
    if '%' not in repo_name:
        repo_name = os.path.basename(repo_path)
        
    logging.info(f"正在处理 {repo_name}")
    
    try:
        os.chdir(repo_path)

        # 获取标签日期
        dateCommand = 'git log --tags --simplify-by-decoration --pretty="format:%ai %d"'
        dateResult = subprocess.check_output(dateCommand, stderr=subprocess.STDOUT, shell=True).decode()
        
        tag_date_file = os.path.join(tag_date_path, repo_name)
        with open(tag_date_file, 'w') as f:
            f.write(str(dateResult))

        # 获取所有标签
        tagCommand = "git tag"
        tagResult = subprocess.check_output(tagCommand, stderr=subprocess.STDOUT, shell=True).decode()

        resDict = {}
        fileCnt = 0
        funcCnt = 0
        lineCnt = 0

        # 处理仓库
        if not tagResult:
            # 处理主分支
            resDict, fileCnt, funcCnt, lineCnt = hashing(repo_path, cache)
            if resDict:
                result_repo_path = os.path.join(result_path, repo_name)
                if not os.path.isdir(result_repo_path):
                    os.makedirs(result_repo_path)
                    
                title = '\t'.join([repo_name, str(fileCnt), str(funcCnt), str(lineCnt)])
                resultFilePath = os.path.join(result_repo_path, f'fuzzy_{repo_name}.hidx')
                
                indexing(resDict, title, resultFilePath)
        else:
            # 处理每个标签
            for tag in str(tagResult).split('\n'):
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
                        
                        resDict, fileCnt, funcCnt, lineCnt = hashing(repo_path, cache)
                        
                        if resDict:
                            result_repo_path = os.path.join(result_path, repo_name)
                            if not os.path.isdir(result_repo_path):
                                os.makedirs(result_repo_path)
                                
                            title = '\t'.join([repo_name, str(fileCnt), str(funcCnt), str(lineCnt)])
                            resultFilePath = os.path.join(result_repo_path, f'fuzzy_{tag}.hidx')
                            
                            indexing(resDict, title, resultFilePath)
                            
                    except subprocess.CalledProcessError as e:
                        logging.warning(f"切换到标签 {tag} 失败: {e.stderr.decode('utf-8', errors='ignore')}")
                        continue
                        
        logging.info(f"处理完成 {repo_name}")
        
    except subprocess.CalledProcessError as e:
        logging.error(f"Git命令执行失败: {e}")
        raise
    except Exception as e:
        logging.error(f"处理仓库失败: {e}")
        raise

if __name__ == "__main__":
    main()

