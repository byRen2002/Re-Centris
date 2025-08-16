"""
数据集收集工具。
此工具用于从本地开源项目仓库中收集C/C++代码,并对函数进行哈希处理以便后续分析。
对于每个项目，存储时对每个tag生成一个hidx文件，里面第一行存储项目名、文件数、函数数、代码行数，
后面每行存储一个哈希值和若干个文件路径，哈希值为使用ctags提取的函数体TLSH哈希，文件路径为相对路径。
"""

import os
import sys
import subprocess
import re
import tlsh # 用于生成局部敏感哈希(Locality Sensitive Hashing))
import datetime
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Tuple, List, Set
import threading
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
import logging
import signal
import time
import concurrent.futures.process

"""全局变量"""
# 获取当前文件所在的目录
current_file_path = os.path.abspath(__file__)
# 获取项目根目录
project_dir = os.path.dirname(os.path.dirname(current_file_path))
analyse_file_dir = os.path.join(project_dir,"analyse_file")

# 定义各种路径
repo_dir = os.path.join(project_dir,"repos")	# 本地仓库的存储路径
tag_date_path = analyse_file_dir + "/oss_collector/repo_date"		# 存储标签日期的路径
result_path	= analyse_file_dir + "/oss_collector/repo_functions"	# 存储结果的路径
log_path = analyse_file_dir +  "/logs/oss_collector"  # 日志存储目录
status_path = analyse_file_dir + "/oss_collector/status.json" # 状态文件路径
temp_path = analyse_file_dir + "/oss_collector/temp"  # 临时文件目录
ctags_path	= "/usr/local/bin/ctags" 			# Ctags工具的路径,用于解析C/C++代码


# 创建必要的目录
shouldMake = [tag_date_path, result_path, log_path, temp_path]
for eachRepo in shouldMake:
    if not os.path.isdir(eachRepo):
        os.makedirs(eachRepo, exist_ok=True)


# 生成日志文件名，包含时间戳
log_file = os.path.join(log_path, f"collector_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 修改日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),  # 文件处理器
        logging.StreamHandler()  # 控制台处理器
    ]
)

# 生成TLSH哈希
def computeTlsh(string):
    """
    使用TLSH算法计算输入字符串的哈希值
    TLSH是一种部敏感哈希算法,可以用于相似性比较
    """
    string 	= str.encode(string)  # 将字符串转换为字节串
    hs 		= tlsh.forcehash(string)  # 计算TLSH哈希
    return hs


def removeComment(string):
    """
    删除C/C++风格的注释
    使用正则表达式匹配并删除单行注释、多行注释,保留字符串字面量
    """
    c_regex = re.compile(
        r'(?P<comment>//.*?$|[{}]+)|(?P<multilinecomment>/\*.*?\*/)|(?P<noncomment>\'(\\.|[^\\\'])*\'|"(\\.|[^\\"])*"|.[^/\'"]*)',
        re.DOTALL | re.MULTILINE)
    return ''.join([c.group('noncomment') for c in c_regex.finditer(string) if c.group('noncomment')])

def normalize(string):
    """
    规范化输入字符串：删除换行符、制表符、花括号和空格，并转换为小写
    这有助于减少代码格式差异对哈希结果的影响
    """
    return ''.join(string.replace('\n', '').replace('\r', '').replace('\t', '').replace('{', '').replace('}', '').split(' ')).lower()

def read_file_safely(file_path):
    """
    安全地读取文件内容，优化性能的版本
    """
    if not os.path.exists(file_path):
        logging.warning(f"文件不存在（可能在当前tag中已被删除）: {file_path}")
        return ""
    
    # 常见编码优先级排序（按使用频率）
    primary_encodings = ['utf-8', 'ascii', 'gb18030', 'latin-1']
    
    try:
        # 只读取一次文件内容
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # 1. 首先尝试最常见的编码
        for encoding in primary_encodings:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        
        # 2. 如果常见编码都失败，再使用chardet（避免大多数情况下使用这个耗时操作）
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
        
        # 3. 最后的备选方案：使用latin-1强制解码
        return content.decode('latin-1', errors='ignore')
            
    except IOError as e:
        logging.error(f"读取文件时发生IO错误 {file_path}: {str(e)}")
        return ""
    except Exception as e:
        logging.error(f"读取文件时发生未知错误 {file_path}: {str(e)}")
        return ""

def cleanup_temp_files(max_age_hours: int = 24):
    """
    清理超过指定时间的临时文件
    """
    try:
        if not os.path.exists(temp_path):
            return

        # 检查目录是否为空
        if not os.listdir(temp_path):
            return

        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for item in os.listdir(temp_path):
            item_path = os.path.join(temp_path, item)
            try:
                # 检查文件/目录的修改时间
                if current_time - os.path.getmtime(item_path) > max_age_seconds:
                    if os.path.isdir(item_path):
                        import shutil
                        shutil.rmtree(item_path, ignore_errors=True)
                        logging.debug(f"已清理过期临时目录: {item_path}")
                    else:
                        os.remove(item_path)
                        logging.debug(f"已清理过期临时文件: {item_path}")
            except Exception as e:
                logging.warning(f"清理临时文件失败 {item_path}: {str(e)}")
                continue
                
    except Exception as e:
        logging.warning(f"清理临时文件目录失败: {str(e)}")

def convert_to_utf8(file_path: str) -> Tuple[str, str]:
    """
    将文件转换为UTF-8编码,返回临时文件路径和原始编码
    """
    temp_dir = None
    temp_file = None
    try:
        # 读取原始文件内容
        content = read_file_safely(file_path)
        if not content:
            return None, None
            
        # 创建临时目录在项目目录下而不是系统/tmp目录
        import tempfile
        import threading
        
        # 使用线程ID确保不同线程/进程间的临时目录不冲突
        thread_id = threading.get_ident()
        temp_dir_name = f'centris_{thread_id}_{int(time.time() * 1000000) % 1000000}'
        temp_dir = os.path.join(temp_path, temp_dir_name)
        
        # 确保临时目录存在
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except OSError as e:
            if e.errno == 28:  # No space left on device
                logging.error(f"磁盘空间不足，无法创建临时目录 {temp_dir}")
                logging.info("尝试清理过期临时文件...")
                cleanup_temp_files(max_age_hours=1)
                try:
                    os.makedirs(temp_dir, exist_ok=True)
                    logging.info("清理临时文件后成功创建目录")
                except Exception as retry_e:
                    logging.error(f"清理临时文件后仍然无法创建目录 {temp_dir}: {str(retry_e)}")
                    return None, None
            else:
                logging.error(f"创建临时目录失败 {temp_dir}: {str(e)}")
                return None, None
        
        # 使用原始文件名创建临时文件
        temp_file = os.path.join(temp_dir, os.path.basename(file_path))
        
        # 以UTF-8编码写入临时文件
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(content)
        except OSError as e:
            if e.errno == 28:  # No space left on device
                logging.error(f"磁盘空间不足，无法写入临时文件 {temp_file}")
                logging.info("尝试清理过期临时文件...")
                cleanup_temp_files(max_age_hours=1)  # 清理1小时前的临时文件
                # 再次尝试写入
                try:
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logging.info("清理临时文件后成功写入")
                except Exception as retry_e:
                    logging.error(f"清理临时文件后仍然写入失败 {temp_file}: {str(retry_e)}")
                    return None, None
            else:
                logging.error(f"写入临时文件失败 {temp_file}: {str(e)}")
                return None, None
        except Exception as e:
            logging.error(f"写入临时文件失败 {temp_file}: {str(e)}")
            return None, None
            
        return temp_file, 'utf-8'
        
    except Exception as e:
        logging.error(f"转换文件编码失败 {file_path}: {str(e)}")
        # 清理临时文件和目录
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        if temp_dir and os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except:
                pass
        return None, None

def process_single_file(file_path: str, base_path: str) -> Tuple[List[Tuple[str, str]], int, int, int]:
    """
    处理单个文件并返回结果列表
    返回: ([(hash, file_path), ...], file_count, func_count, line_count)
    """
    temp_file = None
    temp_dir = None
    try:
        func_count = 0
        results = []  # 存储(hash, file_path)对
        
        # 转换文件编码为UTF-8
        temp_file, encoding = convert_to_utf8(file_path)
        if not temp_file:
            return [], 0, 0, 0
            
        temp_dir = os.path.dirname(temp_file)
            
        # 读取转换后的文件内容
        with open(temp_file, 'r', encoding=encoding) as f:
            content = f.read()
            
        if not content:
            return [], 0, 0, 0

        lines = content.splitlines()
        line_count = len(lines)

        # 使用转换后的文件进行ctags处理
        try:
            functionList = subprocess.check_output(
                f'{ctags_path} -f - --kinds-C=* --fields=neKSt "{temp_file}"',
                stderr=subprocess.STDOUT,
                shell=True,
                timeout=300
            ).decode('utf-8')
        except subprocess.TimeoutExpired:
            logging.warning(f"处理文件超时: {file_path}")
            return [], 0, 0, 0

        # 预编译正则表达式
        func_pattern = re.compile(r'(function)')
        number_pattern = re.compile(r'(\d+)')
        func_search_pattern = re.compile(r'{([\S\s]*)}')

        # 批量处理函数
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

        # 批量处理函数体
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

        return results, 1, func_count, line_count

    except Exception as e:
        logging.error(f"处理文件时出错 {file_path}: {str(e)}")
        return [], 0, 0, 0
        
    finally:
        # 清理临时文件和目录
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                logging.warning(f"清理临时文件失败 {temp_file}: {str(e)}")
        if temp_dir and os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception as e:
                logging.warning(f"清理临时目录失败 {temp_dir}: {str(e)}")

# 优化哈希处理函数，使用进程池
def hashing(repo_path: str, max_workers: int = None) -> Tuple[Dict, int, int, int]:
    """使用多线程处理仓库中的文件"""
    possible = (".c", ".cc", ".cpp")
    result_dict = {}
    
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
    
    # 如果没有文件需要处理，直接返回空结果
    if not files_to_process:
        return result_dict, file_count, func_count, line_count
    
    # 根据文件数量动态调整线程数，确保至少为1
    # IO密集型任务，线程数可以适当增加，但避免过多线程
    if max_workers is None:
        # 计算最佳线程数：文件数和(CPU核心数*2)之间取较小值，且不超过120个线程
        cpu_count = multiprocessing.cpu_count()
        # 对于高核心服务器，设置合理的线程上限
        max_thread_limit = 120  # 设置最大线程数上限
        max_workers = max(1, min(len(files_to_process), cpu_count * 2, max_thread_limit))
    
    
    # 使用线程池处理文件
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(process_single_file, f, repo_path): f 
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
            except Exception as e:
                logging.error(f"处理文件时发生错误: {str(e)}")
    
    return result_dict, file_count, func_count, line_count

def indexing(resDict, title, filePath):
    """
    为每个OSS建立索引并写入文件
    将哈希结果写入指定的文件中
    """
    fres = open(filePath, 'w')
    fres.write(title + '\n')

    for hashval in resDict:
        if hashval == '' or hashval == ' ':
            continue

        fres.write(hashval)
        
        for funcPath in resDict[hashval]:
            fres.write('\t' + funcPath)
        fres.write('\n')

    fres.close()

def get_repo_paths(base_path):
    """
    获取所有仓库路径，避免重复
    """
    repo_paths = set()  # 使用集合去重
    
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if not os.path.isdir(item_path):
            continue
            
        if '%' not in item:
            continue
            
        # 检查第一种结构
        git_path = os.path.join(item_path, '.git')
        if os.path.exists(git_path) and os.path.isdir(git_path):
            repo_paths.add(item_path)
            continue
            
        # 检查第二种结构
        try:
            repo_name = item.split('%')[1]
            nested_path = os.path.join(item_path, repo_name)
            nested_git = os.path.join(nested_path, '.git')
            if os.path.exists(nested_git) and os.path.isdir(nested_git):
                repo_paths.add(nested_path)
        except IndexError:
            logging.warning(f"无效的目录名格式: {item}")
            continue
            
    # 添加验证
    validated_paths = set()
    for path in repo_paths:
        if os.path.exists(os.path.join(path, '.git')):
            validated_paths.add(path)
        else:
            logging.warning(f"仓库路径无效: {path}")
            
    logging.info(f"找到 {len(validated_paths)} 个有效仓库")
    return list(validated_paths)

def save_status(status_dict):
    """
    保存处理状态
    """
    try:
        # 如果是 DictProxy 对象，转换为普通字典
        save_dict = dict(status_dict) if hasattr(status_dict, '_callmethod') else status_dict
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(save_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存状态文件失败: {str(e)}")

def update_repo_status(status_dict: Dict, repo_name: str, success: bool, error_msg: str = None) -> None:
    """更新仓库的处理状态
    
    Args:
        status_dict: 状态字典
        repo_name: 仓库名称
        success: 是否处理成功
        error_msg: 错误信息（如果有）
    """
    status_dict[repo_name] = {
        "success": success,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": error_msg
    }
    
    # 保存状态到文件
    try:
        # 如果是 DictProxy 对象，转换为普通字典
        save_dict = dict(status_dict) if hasattr(status_dict, '_callmethod') else status_dict
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(save_dict, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"保存状态文件失败: {str(e)}")

def check_and_repair_index(repo_path: str, git_cmd_prefix: str = "git") -> bool:
    """检查并修复损坏的索引文件"""
    git_index_path = os.path.join(repo_path, '.git', 'index')
    if not os.path.exists(git_index_path):
        return True  # 索引不存在，不需要修复
        
    try:
        # 尝试检查索引文件
        check_index_cmd = f"{git_cmd_prefix} read-tree --empty"
        check_index_result = subprocess.run(check_index_cmd, shell=True, 
                                          stdout=subprocess.PIPE, 
                                          stderr=subprocess.PIPE,
                                          text=True)
        
        # 如果错误输出中提到索引文件问题
        if "index file" in check_index_result.stderr and "smaller than expected" in check_index_result.stderr:
            logging.warning(f"检测到损坏的索引文件，尝试修复...")
            # 尝试重命名而不是直接删除
            try:
                backup_path = git_index_path + '.bak.' + str(int(time.time()))
                os.rename(git_index_path, backup_path)
                logging.info(f"原索引文件已备份为 {backup_path}")
            except Exception as e:
                logging.error(f"备份索引文件失败，尝试直接删除: {str(e)}")
                try:
                    os.remove(git_index_path)
                    logging.info(f"已删除损坏的索引文件")
                except Exception as e:
                    logging.error(f"删除索引文件失败: {str(e)}")
                    return False
                    
            # 重新创建索引
            try:
                subprocess.run(f"{git_cmd_prefix} read-tree --empty", shell=True, check=True)
                logging.info("已成功重新初始化索引")
                return True
            except Exception as e:
                logging.error(f"重新初始化索引失败: {str(e)}")
                return False
    except Exception as e:
        logging.error(f"检查索引文件时发生错误: {str(e)}")
    return True  # 没有发现问题

def cleanup_git_workspace(repo_path: str, git_cmd_prefix: str = "git") -> None:
    """清理Git工作区和锁文件"""
    # 强制清理工作目录
    cleanup_commands = [
        f"{git_cmd_prefix} merge --abort",  # 中止合并
        f"{git_cmd_prefix} rebase --abort",  # 中止rebase
        f"{git_cmd_prefix} reset --hard HEAD",  # 重置
        f"{git_cmd_prefix} clean -fdx",  # 清理未跟踪文件
        f"{git_cmd_prefix} checkout -f",  # 强制检出
        f"{git_cmd_prefix} clean -fd",  # 清理未跟踪文件和目录
        f"{git_cmd_prefix} clean -fX",  # 清理忽略的文件
    ]
    
    # 执行清理命令，忽略输出
    for cmd in cleanup_commands:
        try:
            subprocess.run(cmd, shell=True, check=False,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        except Exception:
            continue
            
    # 检查并删除lock文件
    lock_files = [
        os.path.join(repo_path, '.git', 'index.lock'),
        os.path.join(repo_path, '.git', 'HEAD.lock'),
        os.path.join(repo_path, '.git', 'refs', 'heads', '*.lock'),
        os.path.join(repo_path, '.git', 'refs', 'tags', '*.lock'),
        os.path.join(repo_path, '.git', 'ORIG_HEAD.lock')
    ]
    
    for lock_pattern in lock_files:
        try:
            import glob
            for lock_file in glob.glob(lock_pattern):
                if os.path.exists(lock_file):
                    os.remove(lock_file)
                    logging.info(f"删除了锁文件: {lock_file}")
        except Exception as e:
            logging.warning(f"删除锁文件失败: {lock_pattern}, 错误: {str(e)}")
            continue

def repair_git_repository(repo_path: str, git_cmd_prefix: str = "git") -> None:
    """尝试修复Git仓库"""
    try:
        repair_commands = [
            f"{git_cmd_prefix} fsck --full",  # 检查并修复仓库
            f"{git_cmd_prefix} gc --prune=now",  # 垃圾回收
            f"{git_cmd_prefix} prune",  # 清理冗余对象
            f"{git_cmd_prefix} repack -ad"  # 重新打包
        ]
        
        for cmd in repair_commands:
            try:
                subprocess.run(cmd, shell=True, check=False,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             timeout=60)
            except Exception:
                continue
                
        # 清理tmp目录
        tmp_dir = os.path.join(repo_path, '.git', 'objects', 'tmp')
        if os.path.exists(tmp_dir):
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
                os.makedirs(tmp_dir, exist_ok=True)
            except Exception:
                pass
    except Exception:
        pass

def handle_index_file_error(repo_path: str, tag: str, checkout_cmd: str, git_cmd_prefix: str = "git") -> bool:
    """处理索引文件损坏错误"""
    logging.error(f"Git索引文件损坏，尝试修复...")
    
    # 删除损坏的索引文件
    git_index_path = os.path.join(repo_path, '.git', 'index')
    if os.path.exists(git_index_path):
        try:
            os.remove(git_index_path)
            logging.info("已删除损坏的索引文件")
        except Exception as e:
            logging.error(f"删除索引文件失败: {str(e)}")
            return False
    
    try:
        # 重新创建索引
        subprocess.run(f"{git_cmd_prefix} read-tree --empty", shell=True, check=True)
        logging.info("已重新创建空索引")
        
        # 更新索引
        fetch_cmd = f"{git_cmd_prefix} fetch --tags --force"
        subprocess.run(fetch_cmd, shell=True, check=False,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
        
        # 再次尝试检出
        retry_result = subprocess.run(checkout_cmd,
                                   shell=True,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE,
                                   text=True)
        
        if retry_result.returncode == 0:
            logging.info(f"修复索引后成功切换到tag {tag}")
            return True
    except Exception as e:
        logging.error(f"重置仓库状态失败: {str(e)}")
    
    return False

def handle_tempfile_error(repo_path: str, tag: str, checkout_cmd: str, git_cmd_prefix: str = "git") -> bool:
    """处理tempfile错误"""
    logging.error(f"Git内部错误 (tempfile)，尝试修复...")
    
    try:
        # 重新初始化git仓库
        reinit_cmd = f"{git_cmd_prefix} init"
        subprocess.run(reinit_cmd, shell=True, check=False,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
        
        # 重新添加远程源
        try:
            remote_url_cmd = f"{git_cmd_prefix} remote get-url origin"
            remote_url = subprocess.check_output(remote_url_cmd, shell=True, text=True).strip()
            if remote_url:
                add_remote_cmd = f"{git_cmd_prefix} remote add origin {remote_url}"
                subprocess.run(add_remote_cmd, shell=True, check=False)
        except Exception:
            pass
        
        # 重新获取标签
        fetch_cmd = f"{git_cmd_prefix} fetch --tags --force"
        subprocess.run(fetch_cmd, shell=True, check=False,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     timeout=300)
        
        # 再次尝试检出
        retry_result = subprocess.run(checkout_cmd,
                                   shell=True,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE,
                                   text=True,
                                   timeout=120)
        
        if retry_result.returncode == 0:
            logging.info(f"通过仓库重初始化成功切换到tag {tag}")
            return True
    except Exception as e:
        logging.error(f"尝试修复仓库失败: {str(e)}")
    
    return False

def fix_git_error(repo_path: str, tag: str, error_msg: str, checkout_cmd: str, repo_name: str = None) -> bool:
    """根据错误类型进行针对性修复"""
    git_cmd_prefix = "git"
    
    # 如果没有提供repo_name，尝试从路径中提取
    if repo_name is None:
        repo_name = os.path.basename(os.path.dirname(repo_path))
        if '%' not in repo_name:
            repo_name = os.path.basename(repo_path)
    
    # 处理以连字符开头的标签名导致的错误
    if "unknown switch" in error_msg and tag.startswith('-'):
        logging.info(f"[{repo_name}] 检测到以连字符开头的标签名错误，使用安全的checkout命令...")
        try:
            safe_checkout_cmd = f'{git_cmd_prefix} checkout -f -- "refs/tags/{tag}"'
            retry_result = subprocess.run(safe_checkout_cmd, shell=True,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            if retry_result.returncode == 0:
                logging.info(f"[{repo_name}] 使用安全命令成功切换到tag {tag}")
                return True
        except Exception as e:
            logging.error(f"[{repo_name}] 安全checkout命令也失败: {str(e)}")
    
    # 处理Git LFS相关错误
    elif "git-lfs" in error_msg and ("not found" in error_msg or "filter-process" in error_msg):
        logging.info(f"[{repo_name}] 尝试处理Git LFS相关错误...")
        try:
            # 临时禁用LFS过滤器
            subprocess.run(f"{git_cmd_prefix} config filter.lfs.smudge 'git-lfs smudge --skip %f'", 
                         shell=True, check=False)
            subprocess.run(f"{git_cmd_prefix} config filter.lfs.process 'git-lfs filter-process --skip'", 
                         shell=True, check=False)
            subprocess.run(f"{git_cmd_prefix} config filter.lfs.clean 'git-lfs clean -- %f'", 
                         shell=True, check=False)
            
            # 重新构建checkout命令
            if tag.startswith('-'):
                safe_checkout_cmd = f'{git_cmd_prefix} checkout -f -- "refs/tags/{tag}"'
            else:
                safe_checkout_cmd = f'{git_cmd_prefix} checkout -f "refs/tags/{tag}"'
                
            retry_result = subprocess.run(safe_checkout_cmd, shell=True,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            if retry_result.returncode == 0:
                logging.info(f"[{repo_name}] 跳过LFS处理后成功切换到tag {tag}")
                return True
        except Exception as e:
            logging.error(f"[{repo_name}] 处理LFS错误失败: {str(e)}")
    
    # 处理非commit对象错误
    elif "Cannot switch branch to a non-commit" in error_msg:
        logging.info(f"[{repo_name}] 尝试通过resolve标签来处理非commit对象...")
        try:
            # 尝试获取标签指向的实际commit
            resolve_cmd = f'{git_cmd_prefix} rev-list -n 1 "refs/tags/{tag}"'
            resolve_result = subprocess.run(resolve_cmd, shell=True,
                                          capture_output=True, text=True)
            if resolve_result.returncode == 0:
                commit_hash = resolve_result.stdout.strip()
                if commit_hash:
                    # 直接checkout到commit hash
                    commit_checkout_cmd = f'{git_cmd_prefix} checkout -f {commit_hash}'
                    retry_result = subprocess.run(commit_checkout_cmd, shell=True,
                                               stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
                    if retry_result.returncode == 0:
                        logging.info(f"[{repo_name}] 通过commit hash成功切换到tag {tag}")
                        return True
        except Exception as e:
            logging.error(f"[{repo_name}] 通过commit hash切换失败: {str(e)}")
    
    # 处理index.lock文件存在错误
    elif "index.lock" in error_msg and "File exists" in error_msg:
        logging.info(f"[{repo_name}] 检测到index.lock锁文件错误，尝试删除锁文件...")
        index_lock = os.path.join(repo_path, '.git', 'index.lock')
        try:
            if os.path.exists(index_lock):
                os.remove(index_lock)
                logging.info(f"[{repo_name}] 成功删除index.lock文件")
                # 重试checkout
                retry_result = subprocess.run(checkout_cmd, shell=True,
                                           stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                if retry_result.returncode == 0:
                    return True
        except Exception as e:
            logging.error(f"[{repo_name}] 删除index.lock文件失败: {str(e)}")
    
    # 处理索引文件损坏错误
    elif "index file smaller than expected" in error_msg:
        logging.info(f"[{repo_name}] 尝试修复索引文件错误...")
        git_index_path = os.path.join(repo_path, '.git', 'index')
        
        # 备份并删除损坏的索引文件
        try:
            if os.path.exists(git_index_path):
                os.rename(git_index_path, git_index_path + '.bak.' + str(int(time.time())))
                logging.info(f"[{repo_name}] 已备份并删除损坏的索引文件")
        except Exception:
            try:
                if os.path.exists(git_index_path):
                    os.remove(git_index_path)
                    logging.info(f"[{repo_name}] 已删除损坏的索引文件")
            except Exception as e:
                logging.error(f"[{repo_name}] 删除索引文件失败: {str(e)}")
                return False
        
        # 重新创建索引并重试
        try:
            subprocess.run(f"{git_cmd_prefix} read-tree --empty", shell=True, check=False)
            retry_result = subprocess.run(checkout_cmd, shell=True, 
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            if retry_result.returncode == 0:
                return True
        except Exception:
            pass
            
    # 处理tempfile错误
    elif "tempfile.c" in error_msg and "get_tempfile_path" in error_msg:
        logging.info(f"[{repo_name}] 尝试修复tempfile错误...")
        try:
            # 清理临时目录
            tmp_dir = os.path.join(repo_path, '.git', 'objects', 'tmp')
            if os.path.exists(tmp_dir):
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
                os.makedirs(tmp_dir, exist_ok=True)
                
            # 重新初始化仓库
            subprocess.run(f"{git_cmd_prefix} init", shell=True, check=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 尝试重新获取标签
            subprocess.run(f"{git_cmd_prefix} fetch --tags --force", shell=True, check=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                         
            # 重试检出
            retry_result = subprocess.run(checkout_cmd, shell=True,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            if retry_result.returncode == 0:
                return True
        except Exception:
            pass
    
    # 处理其他错误 - 简单重试
    else:
        try:
            # 清理所有锁文件
            cleanup_git_workspace(repo_path, git_cmd_prefix)
                        
            # 获取最新标签
            subprocess.run(f"{git_cmd_prefix} fetch --tags --force", shell=True, check=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                         
            # 重试检出
            retry_result = subprocess.run(checkout_cmd, shell=True,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            if retry_result.returncode == 0:
                return True
        except Exception:
            pass
            
    return False

def cleanup_and_checkout_tag(repo_path: str, tag: str, repo_name: str = None) -> bool:
    """清理并切换到指定tag - 精简版本"""
    git_cmd_prefix = "git"
    
    # 如果没有提供repo_name，尝试从路径中提取
    if repo_name is None:
        repo_name = os.path.basename(os.path.dirname(repo_path))
        if '%' not in repo_name:
            repo_name = os.path.basename(repo_path)
    
    try:
        # 0. 首先删除可能存在的锁文件
        index_lock = os.path.join(repo_path, '.git', 'index.lock')
        if os.path.exists(index_lock):
            try:
                os.remove(index_lock)
                logging.info(f"[{repo_name}] 删除了index.lock文件")
            except Exception as e:
                logging.warning(f"[{repo_name}] 无法删除index.lock文件: {str(e)}")
        
        # 1. 检查tag是否存在
        check_tag_cmd = f'{git_cmd_prefix} show-ref --verify --quiet "refs/tags/{tag}"'
        if subprocess.run(check_tag_cmd, shell=True).returncode != 0:
            logging.warning(f"[{repo_name}] Tag {tag} 不存在")
            return False
        
        # 2. 检查tag指向的对象类型
        try:
            # 获取tag指向的对象类型
            type_cmd = f'{git_cmd_prefix} cat-file -t "refs/tags/{tag}"'
            type_result = subprocess.run(type_cmd, shell=True, 
                                       capture_output=True, text=True)
            if type_result.returncode == 0:
                obj_type = type_result.stdout.strip()
                if obj_type == 'tag':
                    # 如果是注释标签，获取其指向的commit
                    resolve_cmd = f'{git_cmd_prefix} rev-list -n 1 "refs/tags/{tag}"'
                    resolve_result = subprocess.run(resolve_cmd, shell=True,
                                                  capture_output=True, text=True)
                    if resolve_result.returncode != 0:
                        logging.warning(f"[{repo_name}] Tag {tag} 指向的不是有效的commit对象")
                        return False
                elif obj_type not in ['commit', 'tree']:
                    logging.warning(f"[{repo_name}] Tag {tag} 指向的是 {obj_type} 对象，不是commit")
                    return False
        except Exception as e:
            logging.warning(f"[{repo_name}] 检查tag {tag} 对象类型失败: {str(e)}")
            
        # 3. 最小必要清理 - 只执行最重要的操作
        try:
            # 调用清理函数删除所有锁文件
            cleanup_git_workspace(repo_path, git_cmd_prefix)
            
            # 中止可能正在进行的操作
            subprocess.run(f"{git_cmd_prefix} reset --hard", shell=True, check=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
            # 清理工作区
            subprocess.run(f"{git_cmd_prefix} clean -fdx", shell=True, check=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logging.warning(f"[{repo_name}] 清理失败，继续尝试: {str(e)}")
            
        # 4. 构建安全的checkout命令
        # 处理以连字符开头的标签名
        if tag.startswith('-'):
            checkout_cmd = f'{git_cmd_prefix} checkout -f -- "refs/tags/{tag}"'
        else:
            checkout_cmd = f'{git_cmd_prefix} checkout -f "refs/tags/{tag}"'
            
        # 5. 尝试切换到tag
        result = subprocess.run(checkout_cmd, shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              text=True)
                              
        # 6. 检查结果和错误信息
        error_msg = result.stderr.strip()
        output_msg = result.stdout.strip()
        
        # 检查是否是Git LFS相关错误
        if "git-lfs" in error_msg and "not found" in error_msg:
            logging.warning(f"[{repo_name}] Tag {tag} 需要Git LFS支持，但系统未安装git-lfs，尝试跳过LFS处理")
            # 尝试禁用LFS过滤器重新checkout
            try:
                subprocess.run(f"{git_cmd_prefix} config filter.lfs.smudge 'git-lfs smudge --skip %f'", 
                             shell=True, check=False)
                subprocess.run(f"{git_cmd_prefix} config filter.lfs.process 'git-lfs filter-process --skip'", 
                             shell=True, check=False)
                retry_result = subprocess.run(checkout_cmd, shell=True,
                                           stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                if retry_result.returncode == 0:
                    logging.info(f"[{repo_name}] 跳过LFS处理后成功切换到tag {tag}")
                    return True
            except Exception:
                pass
        
        # 检查文件删除失败但切换成功的情况
        if result.returncode != 0 and ("unable to unlink" in error_msg or "No such file or directory" in error_msg):
            # 检查是否实际上切换成功了
            if "HEAD is now at" in output_msg or "HEAD is now at" in error_msg:
                logging.info(f"[{repo_name}] Tag {tag} 切换成功（虽然有文件删除警告）")
                return True
        
        # 7. 如果成功直接返回
        if result.returncode == 0:
            # 验证切换是否真的成功
            verify_cmd = f'{git_cmd_prefix} rev-parse --verify HEAD'
            verify_result = subprocess.run(verify_cmd, shell=True,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL)
            if verify_result.returncode == 0:
                logging.debug(f"[{repo_name}] 成功切换到tag {tag}")
                return True
                                         
        # 8. 如果失败，尝试修复
        # 特别检查index.lock错误
        if "index.lock" in error_msg and "File exists" in error_msg:
            index_lock = os.path.join(repo_path, '.git', 'index.lock')
            try:
                if os.path.exists(index_lock):
                    os.remove(index_lock)
                    logging.info(f"[{repo_name}] 删除了index.lock文件，重试checkout")
                    # 重试checkout
                    retry_result = subprocess.run(checkout_cmd, shell=True,
                                               stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
                    if retry_result.returncode == 0:
                        return True
            except Exception as e:
                logging.error(f"[{repo_name}] 无法删除index.lock文件: {str(e)}")
        
        # 忽略无害错误
        harmless_errors = [
            "Previous HEAD position", "HEAD is now at", 
            "already exists, no checkout", "Switched to"
        ]
        
        # 检查是否只包含无害错误
        has_harmful_error = not all(
            any(harmless in line for harmless in harmless_errors)
            for line in error_msg.splitlines()
            if line.strip()
        )
        
        if has_harmful_error:
            logging.error(f"[{repo_name}] 切换到tag {tag} 失败: {error_msg}")
            return fix_git_error(repo_path, tag, error_msg, checkout_cmd, repo_name)
        
        return True
        
    except Exception as e:
        logging.error(f"[{repo_name}] 处理tag {tag} 时发生错误: {str(e)}")
        return False

def get_repo_tags(repo_path: str, max_retries: int = 3) -> str:
    """获取仓库的所有标签，带重试机制"""
    git_cmd_prefix = "git"
    
    # 增加获取标签的超时时间到5分钟
    timeout = 300
    
    for attempt in range(max_retries):
        try:
            # 使用更高效的命令
            tag_cmd = f"{git_cmd_prefix} tag --list"
            
            # 执行命令
            result = subprocess.run(
                tag_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return result.stdout
                
            # 如果失败，尝试fetch更新
            if attempt < max_retries - 1:
                logging.warning(f"获取标签失败，尝试fetch更新 (尝试 {attempt + 1}/{max_retries})")
                fetch_cmd = f"{git_cmd_prefix} fetch --tags --force"
                subprocess.run(fetch_cmd, shell=True, timeout=300)
                
        except subprocess.TimeoutExpired:
            if attempt < max_retries - 1:
                logging.warning(f"获取标签超时，重试中 (尝试 {attempt + 1}/{max_retries})")
                # 增加下一次重试的超时时间
                timeout *= 2
            else:
                logging.error(f"获取标签列表最终超时: {repo_path}")
                return ""
        except Exception as e:
            logging.error(f"获取标签时发生错误: {str(e)}")
            return ""
            
    return ""

def normalize_tag(tag: str) -> str:
    """
    规范化标签名,将/替换为_
    """
    return tag.replace('/', '_') if tag else tag

def process_single_repo(repo_path: str, status_dict: Dict) -> bool:
    """处理单个仓库的函数"""
    repo_name = None
    try:
        # 更安全的仓库名称提取
        try:
            repo_name = os.path.basename(os.path.dirname(repo_path))
            if '%' not in repo_name or repo_name == "Component":
                repo_name = os.path.basename(repo_path)
            # 如果仓库名还包含路径分隔符，只取最后一部分
            repo_name = repo_name.split('/')[-1].split('\\')[-1]
        except Exception as e:
            logging.error(f"提取仓库名称失败 {repo_path}: {str(e)}")
            return False
            
        logging.info(f"正在处理 {repo_name}")
        
        # 检查目录是否存在
        if not os.path.exists(repo_path):
            logging.error(f"仓库路径不存在: {repo_path}")
            update_repo_status(status_dict, repo_name, False, "仓库路径不存在")
            return False
            
        # 检查是否包含C/C++文件
        has_c_files = False
        possible_extensions = (".c", ".cc", ".cpp", ".h", ".hpp")
        for root, _, files in os.walk(repo_path):
            if any(f.endswith(possible_extensions) for f in files):
                has_c_files = True
                break
                
        if not has_c_files:
            logging.info(f"{repo_name}: 不是C/C++项目，跳过处理")
            update_repo_status(status_dict, repo_name, True, "不是C/C++项目")
            return False
            
        # 检查是否为有效的 git 仓库
        git_dir = os.path.join(repo_path, ".git")
        if not os.path.exists(git_dir) or not os.path.isdir(git_dir):
            logging.error(f"无效的 Git 仓库: {repo_path}")
            update_repo_status(status_dict, repo_name, False, "无效的 Git 仓库")
            return False
            
        # 使用文件锁确保同一时间只有一个进程操作该仓库
        lock_file = os.path.join(git_dir, "centris.lock")
        
        # 主动删除可能存在的Git锁文件
        cleanup_git_workspace(repo_path)
        
        try:
            with open(lock_file, 'x') as f:  # 创建锁文件
                try:
                    os.chdir(repo_path)
                except Exception as e:
                    logging.error(f"切换目录失败 {repo_path}: {str(e)}")
                    update_repo_status(status_dict, repo_name, False, f"切换目录失败: {str(e)}")
                    return False

                # 获取标签日期
                try:
                    git_cmd_prefix = "git"
                    dateCommand = f'{git_cmd_prefix} log --tags --simplify-by-decoration --pretty="format:%ai %d"'
                    dateResult = subprocess.run(dateCommand, 
                                             shell=True,
                                             capture_output=True,
                                             timeout=300)
                    
                    if dateResult.returncode == 0:
                        # 处理标签日期输出
                        date_output = dateResult.stdout.decode('utf-8', errors='ignore')
                        # 替换标签中的/为_
                        processed_output = re.sub(r'\((tag: [^)]*)/([^)]*)\)', r'(tag: \1_\2)', date_output)
                        
                        os.makedirs(tag_date_path, exist_ok=True)
                        with open(os.path.join(tag_date_path, repo_name), 'w') as f:
                            f.write(processed_output)
                    else:
                        error_msg = dateResult.stderr.decode('utf-8', errors='ignore').strip()
                        logging.warning(f"获取标签日期返回非零状态: {error_msg}")
                        
                except subprocess.TimeoutExpired:
                    logging.warning(f"获取标签日期超时,继续处理")
                except Exception as e:
                    logging.error(f"获取标签日期失败: {str(e)}")
                    update_repo_status(status_dict, repo_name, False, f"获取标签日期失败: {str(e)}")
                    return False

                # 获取所有标签
                tagOutput = get_repo_tags(repo_path)
                
                # 处理仓库
                total_tags = 0
                successful_tags = 0
                
                if not tagOutput or tagOutput.strip() == "":
                    # 没有标签,只处理主分支
                    resultFilePath = os.path.join(result_path, repo_name, f'fuzzy_{repo_name}.hidx')
                    if os.path.exists(resultFilePath):
                        logging.info(f"主分支/无标签项目 {repo_name} 的结果文件 {resultFilePath} 已存在，跳过处理。")
                        successful_tags = 1 # 标记为成功
                    else:
                        resDict, fileCnt, funcCnt, lineCnt = hashing(repo_path)
                        if len(resDict) > 0:
                            os.makedirs(os.path.join(result_path, repo_name), exist_ok=True)
                            title = '\t'.join([repo_name, str(fileCnt), str(funcCnt), str(lineCnt)])
                            indexing(resDict, title, resultFilePath)
                            successful_tags = 1
                    total_tags = 1
                else:
                    # 处理每个标签
                    tags = [tag for tag in str(tagOutput).split('\n') if tag and tag.strip()]
                    total_tags = len(tags)
                    
                    if total_tags == 0:
                        # 如果分割后没有有效标签，处理主分支
                        resultFilePath = os.path.join(result_path, repo_name, f'fuzzy_{repo_name}.hidx')
                        if os.path.exists(resultFilePath):
                            logging.info(f"主分支/无标签项目 {repo_name} (无有效tag后) 的结果文件 {resultFilePath} 已存在，跳过处理。")
                            successful_tags = 1
                        else:
                            resDict, fileCnt, funcCnt, lineCnt = hashing(repo_path)
                            if len(resDict) > 0:
                                os.makedirs(os.path.join(result_path, repo_name), exist_ok=True)
                                title = '\t'.join([repo_name, str(fileCnt), str(funcCnt), str(lineCnt)])
                                indexing(resDict, title, resultFilePath)
                                successful_tags = 1
                        total_tags = 1 # 确保在这种情况下 total_tags 也为1
                    else:
                        for tag in tags:
                            try:
                                # 规范化标签名
                                normalized_tag = normalize_tag(tag)
                                
                                # 构建预期的结果文件路径
                                expected_hidx_file = os.path.join(result_path, repo_name, f'fuzzy_{normalized_tag}.hidx')
                                
                                # 检查结果文件是否已存在
                                if os.path.exists(expected_hidx_file):
                                    logging.info(f"Tag {tag} (normalized: {normalized_tag}) 的结果文件 {expected_hidx_file} 已存在，跳过处理。")
                                    successful_tags += 1 
                                    continue # 跳到下一个tag
                                
                                # 清理和切换tag (使用原始tag)
                                if not cleanup_and_checkout_tag(repo_path, tag, repo_name):
                                    logging.warning(f"[{repo_name}] 跳过处理tag {tag} (因切换失败)")
                                    continue
                                
                                # 处理当前tag
                                resDict, fileCnt, funcCnt, lineCnt = hashing(repo_path)
                                if len(resDict) > 0:
                                    os.makedirs(os.path.join(result_path, repo_name), exist_ok=True)
                                    title = '\t'.join([repo_name, str(fileCnt), str(funcCnt), str(lineCnt)])
                                    # 使用规范化后的标签名保存文件 (路径与 expected_hidx_file 一致)
                                    indexing(resDict, title, expected_hidx_file)
                                    successful_tags += 1
                            except Exception as e:
                                logging.warning(f"处理标签 {tag} 失败: {str(e)}")
                                continue

                # 计算成功率并更新状态
                success_rate = (successful_tags / total_tags) if total_tags > 0 else 0
                is_success = success_rate >= 0.8  # 80%阈值
                
                status_message = (
                    f"处理完成 {successful_tags}/{total_tags} 个标签 "
                    f"(成功率: {success_rate*100:.1f}%)"
                )
                
                update_repo_status(
                    status_dict, 
                    repo_name, 
                    is_success,
                    None if is_success else f"标签处理成功率过低: {status_message}"
                )
                
                logging.info(f"{repo_name}: {status_message}")
                return is_success

        finally:
            # 确保删除锁文件
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
            except:
                pass
        
    except FileExistsError:
        if repo_name:
            logging.warning(f"仓库 {repo_name} 正在被其他进程处理，跳过")
            update_repo_status(status_dict, repo_name, False, "正在被其他进程处理，跳过")
        return False
    except Exception as e:
        error_msg = str(e)
        logging.error(f"处理仓库失败 {repo_path}: {error_msg}")
        if repo_name:
            update_repo_status(status_dict, repo_name, False, error_msg)
        return False

class BatchProcessor:
    def __init__(self, batch_size=300):  # 保留批次大小用于并行处理资源管理
        self.batch_size = batch_size
        self.repo_status_file = status_path
        self.repo_status = {}
        self.load_status()
    
    def load_status(self):
        """加载仓库处理状态"""
        # 初始化默认值
        self.repo_status = {}
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.repo_status_file), exist_ok=True)
        
        # 加载仓库处理状态
        try:
            if os.path.exists(self.repo_status_file) and os.path.getsize(self.repo_status_file) > 0:
                with open(self.repo_status_file, 'r', encoding='utf-8') as f:
                    self.repo_status = json.load(f)
                    logging.info(f"成功加载仓库状态：共 {len(self.repo_status)} 个仓库记录")
            else:
                logging.info("仓库状态文件不存在或为空，创建新文件")
                self._create_repo_status_file()
        except json.JSONDecodeError:
            logging.warning("仓库状态文件格式错误，创建新文件")
            self._create_repo_status_file()
        except Exception as e:
            logging.error(f"加载仓库状态时发生错误: {str(e)}")
            self._create_repo_status_file()
    
    def _create_repo_status_file(self):
        """创建新的仓库状态文件"""
        try:
            with open(self.repo_status_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            self.repo_status = {}
            logging.info("已创建新的仓库状态文件")
        except Exception as e:
            logging.error(f"创建仓库状态文件失败: {str(e)}")
    
    def is_repo_processed(self, repo_path: str) -> bool:
        """检查仓库是否已经成功处理过"""
        repo_name = os.path.basename(os.path.dirname(repo_path))
        if '%' not in repo_name:
            repo_name = os.path.basename(repo_path)
        if repo_name in self.repo_status:
            return self.repo_status[repo_name].get('success', False)
        return False
    
    def process_repos(self, repo_paths: List[str]):
        """处理所有仓库，跳过已处理成功的"""
        total_repos = len(repo_paths)
        
        # 过滤出未处理的仓库
        unprocessed_repos = [
            repo for repo in repo_paths 
            if not self.is_repo_processed(repo)
        ]
        
        processed_count = total_repos - len(unprocessed_repos)
        logging.info(f"共发现 {total_repos} 个仓库，其中 {processed_count} 个已成功处理，"
                   f"{len(unprocessed_repos)} 个需要处理")
        
        if not unprocessed_repos:
            logging.info("所有仓库已处理完成，无需进一步处理")
            return
            
        # 按批次处理剩余仓库（仅用于资源管理，不进行断点续传）
        total_batches = (len(unprocessed_repos) + self.batch_size - 1) // self.batch_size
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(unprocessed_repos))
            current_batch = unprocessed_repos[start_idx:end_idx]
            
            logging.info(f"处理批次 {batch_idx + 1}/{total_batches} "
                       f"(当前批次: {len(current_batch)} 个仓库)")
            
            # 处理当前批次
            self.process_batch(current_batch)
            
            # 计算总进度
            newly_processed = sum(1 for repo in current_batch 
                               if self.is_repo_processed(repo))
            processed_count += newly_processed
            
            logging.info(f"批次 {batch_idx + 1} 完成，成功处理 {newly_processed}/{len(current_batch)} 个仓库")
            logging.info(f"总进度: {processed_count}/{total_repos} "
                       f"({processed_count/total_repos*100:.2f}%)")
    
    def process_batch(self, batch_repos: List[str]):
        """处理单个批次的仓库"""
        with multiprocessing.Manager() as manager:
            status_dict = manager.dict(self.repo_status)  # 使用已加载的状态
            
            # 优化进程数配置 - 针对高核心服务器
            cpu_count = multiprocessing.cpu_count()
            
            # 高核心服务器(72核)优化策略:
            # 1. 使用核心数的80%作为基准
            # 2. 保留至少4个核心给系统和其他进程
            # 3. 不超过批次中的仓库数量
            reserved_cores = max(4, int(cpu_count * 0.2))  # 保留至少4个核心或20%核心
            max_workers = max(1, min(cpu_count - reserved_cores, len(batch_repos)))
            
            logging.info(f"使用 {max_workers} 个进程并行处理仓库 (系统共有 {cpu_count} 个CPU核心，保留 {reserved_cores} 个核心给系统)")
            
            # 跟踪已处理和失败的仓库
            processed_repos = set()
            failed_repos = set()
            
            # 使用更健壮的方式处理进程池
            for attempt in range(3):  # 最多尝试3次
                if not batch_repos:
                    break
                    
                remaining_repos = [repo for repo in batch_repos if repo not in processed_repos and repo not in failed_repos]
                if not remaining_repos:
                    break
                    
                if attempt > 0:
                    logging.info(f"第 {attempt+1} 次尝试处理剩余的 {len(remaining_repos)} 个仓库")
                
                try:
                    with ProcessPoolExecutor(max_workers=max_workers) as executor:
                        # 创建future到repo的映射
                        future_to_repo = {}
                        
                        # 提交任务
                        for repo_path in remaining_repos:
                            future = executor.submit(process_single_repo, repo_path, status_dict)
                            future_to_repo[future] = repo_path
                        
                        # 处理结果
                        for future in as_completed(future_to_repo):
                            repo_path = future_to_repo[future]
                            try:
                                success = future.result()
                                repo_name = os.path.basename(os.path.dirname(repo_path))
                                if '%' not in repo_name:
                                    repo_name = os.path.basename(repo_path)
                                
                                # 标记为已处理
                                processed_repos.add(repo_path)
                                
                                # 检查仓库状态，只在以下情况记录警告：
                                # 1. 处理失败
                                # 2. 不是因为"正在被其他进程处理"
                                # 3. 不是"不是C/C++项目"
                                if not success and repo_name in status_dict:
                                    error_msg = status_dict[repo_name].get('error', '')
                                    if (error_msg != "不是C/C++项目" and 
                                        "正在被其他进程处理" not in error_msg):
                                        logging.warning(f"处理仓库失败: {repo_path}")
                            except concurrent.futures.process.BrokenProcessPool as e:
                                # 进程池崩溃，需要重建
                                logging.error(f"进程池异常 (BrokenProcessPool): {str(e)}")
                                # 标记当前仓库为失败，但允许重试
                                failed_repos.add(repo_path)
                                
                                # 更新状态
                                repo_name = os.path.basename(os.path.dirname(repo_path))
                                if '%' not in repo_name:
                                    repo_name = os.path.basename(repo_path)
                                
                                update_repo_status(status_dict, repo_name, False, f"进程异常终止: {str(e)}")
                                
                                # 中断当前循环，重建进程池
                                break
                            except multiprocessing.ProcessError as e:
                                # 进程相关错误
                                logging.error(f"进程错误 (ProcessError): {str(e)}")
                                failed_repos.add(repo_path)
                                
                                # 更新状态
                                repo_name = os.path.basename(os.path.dirname(repo_path))
                                if '%' not in repo_name:
                                    repo_name = os.path.basename(repo_path)
                                
                                update_repo_status(status_dict, repo_name, False, f"进程错误: {str(e)}")
                                
                                # 可能需要重建进程池
                                break
                            except Exception as e:
                                logging.error(f"处理仓库异常 {repo_path}: {str(e)}")
                                failed_repos.add(repo_path)
                                
                                # 更新状态
                                repo_name = os.path.basename(os.path.dirname(repo_path))
                                if '%' not in repo_name:
                                    repo_name = os.path.basename(repo_path)
                                    
                                update_repo_status(status_dict, repo_name, False, f"处理异常: {str(e)}")
                except concurrent.futures.process.BrokenProcessPool as e:
                    # 进程池崩溃，记录日志
                    logging.error(f"进程池崩溃 (BrokenProcessPool): {str(e)}")
                    # 等待一段时间再重试
                    time.sleep(5)
                    continue
                except multiprocessing.ProcessError as e:
                    # 进程相关错误
                    logging.error(f"进程错误 (ProcessError): {str(e)}")
                    # 等待一段时间再重试
                    time.sleep(5)
                    continue
                except Exception as e:
                    logging.error(f"批处理异常: {str(e)}")
                    # 等待一段时间再重试
                    time.sleep(5)
                    continue
            
            # 处理最终失败的仓库
            for repo_path in failed_repos:
                if repo_path not in processed_repos:
                    repo_name = os.path.basename(os.path.dirname(repo_path))
                    if '%' not in repo_name:
                        repo_name = os.path.basename(repo_path)
                    
                    # 如果状态中没有记录，添加失败状态
                    if repo_name not in status_dict:
                        update_repo_status(status_dict, repo_name, False, "多次尝试后仍然失败")
            
            # 更新本地状态
            self.repo_status.update(dict(status_dict))
            # 保存到文件
            save_status(self.repo_status)

def main():
    """主函数"""
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    
    # 程序启动时清理过期的临时文件
    logging.info("清理过期临时文件...")
    cleanup_temp_files(max_age_hours=24)
    
    repo_paths = get_repo_paths(repo_dir)
    if len(repo_paths) != len(set(repo_paths)):
        logging.error("发现重复的仓库路径!")
        return
        
    total_repos = len(repo_paths)
    logging.info(f"开始处理总共 {total_repos} 个仓库")
    
    # 创建批处理器并开始处理
    processor = BatchProcessor(batch_size=300)
    processor.process_repos(repo_paths)
    
    # 处理完成后再次清理临时文件
    logging.info("清理临时文件...")
    cleanup_temp_files(max_age_hours=0)  # 清理所有临时文件
    
    logging.info("所有仓库处理完成")

if __name__ == "__main__":
    main()

