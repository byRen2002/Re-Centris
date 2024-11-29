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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Tuple, List, Set
import threading
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
import logging
import signal

"""全局变量"""

# 定义各种路径
current_path	= "/home/rby/Project/project-file/dependency_analysis/centris"  # 当前工作目录
repo_path 	= "/home/rby/Project/project-file/dependency_analysis/repo_src"		# 本地仓库的存储路径
tag_date_path = current_path + "/OSS_Collector/repo_date/"		# 存储标签日期的路径
result_path	= current_path + "/OSS_Collector/repo_functions/"	# 存储结果的路径
log_path = current_path +  "/logs/OSS_Collector"  # 日志存储目录
ctags_path	= "/usr/local/bin/ctags" 			# Ctags工具的路径,用于解析C/C++代码


# 创建必要的目录
shouldMake = [tag_date_path, result_path, log_path]
for eachRepo in shouldMake:
    if not os.path.isdir(eachRepo):
        os.mkdir(eachRepo)


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

# 修改处理单个文件的函数
def process_single_file(file_path: str, base_path: str) -> Tuple[List[Tuple[str, str]], int, int, int]:
    """
    处理单个文件并返回结果列表
    返回: ([(hash, file_path), ...], file_count, func_count, line_count)
    """
    try:
        func_count = 0
        results = []  # 存储(hash, file_path)对
        
        content = read_file_safely(file_path)
        if not content:
            return [], 0, 0, 0

        lines = content.splitlines()
        line_count = len(lines)

        # 批量处理函数列表
        try:
            functionList = subprocess.check_output(
                f'{ctags_path} -f - --kinds-C=* --fields=neKSt "{file_path}"',
                stderr=subprocess.STDOUT,
                shell=True,
                timeout=30  # 添加超时限制
            ).decode()
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

# 优化哈希处理函数，使用进程池
def hashing(repo_path: str, max_workers: int = None) -> Tuple[Dict, int, int, int]:
    """
    并行处理仓库中的所有C/C++文件
    """
    if max_workers is None:
        max_workers = multiprocessing.cpu_count()

    possible = (".c", ".cc", ".cpp")
    result_dict = {}  # 最终的结果字典
    
    # 收集所有需要处理的文件
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
    
    # 使用进程池处理文件
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
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
    获取所有仓库路径，适应两种不同的目录结构
    """
    repo_paths = []
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if os.path.isdir(item_path):
            if '%' in item:
                # 检查是否有第二层目录
                sub_items = os.listdir(item_path)
                if len(sub_items) == 1 and os.path.isdir(os.path.join(item_path, sub_items[0])):
                    # 第二种结构：作者%仓库名/仓库名
                    repo_paths.append(os.path.join(item_path, sub_items[0]))
                else:
                    # 第一种结构：作者%仓库名
                    repo_paths.append(item_path)
            else:
                # 可能是其他类型的目录，跳过
                continue
    return repo_paths

def main():
    """
    主函数,处理指定目录下的所有Git仓库
    """
    # 设置信号处理
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    
    repo_paths = get_repo_paths(repo_path)
    total_repos = len(repo_paths)
    
    logging.info(f"开始处理 {total_repos} 个仓库")
    
    for idx, current_repo_path in enumerate(repo_paths, 1):
        repo_name = os.path.basename(os.path.dirname(current_repo_path))
        if '%' not in repo_name:
            repo_name = os.path.basename(current_repo_path)
            
        logging.info(f"[{idx}/{total_repos}] 正在处理 {repo_name}")
        
        try:
            os.chdir(current_repo_path)

            # 获取标签日期
            dateCommand = 'git log --tags --simplify-by-decoration --pretty="format:%ai %d"'
            dateResult = subprocess.check_output(dateCommand, stderr = subprocess.STDOUT, shell = True).decode()
            tagDateFile = open(os.path.join(tag_date_path, repo_name), 'w')
            tagDateFile.write(str(dateResult))
            tagDateFile.close()

            # 获取所有标签
            tagCommand = "git tag"
            tagResult = subprocess.check_output(tagCommand, stderr = subprocess.STDOUT, shell = True).decode()

            resDict = {}
            fileCnt = 0
            funcCnt = 0
            lineCnt = 0

            # 处理仓库
            if tagResult == "":
                # 没有标签，只处理主分支
                resDict, fileCnt, funcCnt, lineCnt = hashing(current_repo_path)
                if len(resDict) > 0:
                    if not os.path.isdir(os.path.join(result_path, repo_name)):
                        os.mkdir(os.path.join(result_path, repo_name))
                    title = '\t'.join([repo_name, str(fileCnt), str(funcCnt), str(lineCnt)])
                    resultFilePath = os.path.join(result_path, repo_name, f'fuzzy_{repo_name}.hidx')
                    
                    indexing(resDict, title, resultFilePath)

            else:
                # 处理每个标签（版本）
                for tag in str(tagResult).split('\n'):
                    if tag:  # 确保标签不是空字符串
                        # 保证tag存在
                        try:
                            # 清理tag名称中的特殊字符
                            cleaned_tag = tag.strip().replace('"', '').replace("'", '')
                            # 使用引号包裹tag名称，并使用更安全的checkout命令
                            checkout_command = ['git', 'checkout', '-f', cleaned_tag]
                            subprocess.run(checkout_command, 
                                        check=True,
                                        stderr=subprocess.PIPE,
                                        stdout=subprocess.PIPE)
                            resDict, fileCnt, funcCnt, lineCnt = hashing(current_repo_path)
                        except subprocess.CalledProcessError as e:
                            logging.warning(f"切换到标签 {tag} 失败: {e.stderr.decode('utf-8', errors='ignore')}")
                            continue
                        
                        if len(resDict) > 0:
                            if not os.path.isdir(os.path.join(result_path, repo_name)):
                                os.mkdir(os.path.join(result_path, repo_name))
                            title = '\t'.join([repo_name, str(fileCnt), str(funcCnt), str(lineCnt)])
                            resultFilePath = os.path.join(result_path, repo_name, f'fuzzy_{tag}.hidx')
                        
                            indexing(resDict, title, resultFilePath)
            logging.info(f"处理完成 {repo_name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"解析器错误: {e}")
            continue
        except Exception as e:
            logging.error(f"处理失败: {e}")
            continue
    logging.info("所有仓库处理完成")

""" 执行 """
if __name__ == "__main__":
    main()

