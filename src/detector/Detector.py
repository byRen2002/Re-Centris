"""
检测器模块 - 用于检测代码克隆和依赖关系

该模块实现了基于TLSH(Trend Micro Locality Sensitive Hash)的代码克隆检测。
主要功能包括:
1. 提取源代码中的函数
2. 计算函数的TLSH哈希值
3. 与组件数据库进行匹配
4. 识别代码重用和依赖关系

主要类和函数:
- computeTlsh: 计算字符串的TLSH哈希值
- removeComment: 移除代码中的注释
- normalize: 标准化代码字符串
- hashing: 处理源代码文件并生成哈希
- detector: 执行克隆检测的主要逻辑

作者: byRen2002
修改日期: 2024年11月20日
许可证: MIT License
"""

# 导入必要的库
import os  # 用于文件和目录操作
import sys  # 用于命令行参数处理
import subprocess  # 用于执行外部命令
import re  # 用于正则表达式处理
import shutil  # 用于高级文件操作
import json  # 用于JSON数据处理
import tlsh  # 用于计算局部敏感哈希
from concurrent.futures import ProcessPoolExecutor  # 用于多进程处理
import multiprocessing  # 用于多进程支持
import concurrent.futures  # 用于并发执行
import logging  # 用于日志记录
import datetime  # 用于时间戳处理
import time  # 用于性能计时

"""缓存配置"""
CACHE_SIZE = 1000  # 缓存大小限制
CACHE_EXPIRE = 3600  # 缓存过期时间(秒)

class Cache:
    """
    通用缓存类
    
    用于缓存计算结果,减少重复计算:
    - TLSH哈希值缓存
    - 文件内容缓存
    - 函数解析结果缓存
    
    特性:
    - 支持LRU淘汰策略
    - 支持过期时间
    - 支持大小限制
    - 线程安全
    """
    
    def __init__(self, max_size=CACHE_SIZE, expire=CACHE_EXPIRE):
        """
        初始化缓存
        
        参数:
            max_size: int, 最大缓存条目数
            expire: int, 缓存过期时间(秒)
        """
        self.cache = {}  # 缓存字典
        self.max_size = max_size  # 最大大小
        self.expire = expire  # 过期时间
        self.access_times = {}  # 访问时间记录
        self._lock = multiprocessing.Lock()  # 线程锁
        
    def get(self, key):
        """获取缓存值"""
        with self._lock:
            if key not in self.cache:
                return None
                
            # 检查是否过期
            access_time = self.access_times[key]
            if time.time() - access_time > self.expire:
                del self.cache[key]
                del self.access_times[key]
                return None
                
            # 更新访问时间
            self.access_times[key] = time.time()
            return self.cache[key]
            
    def set(self, key, value):
        """设置缓存值"""
        with self._lock:
            # 检查是否需要淘汰
            if len(self.cache) >= self.max_size:
                # 按访问时间排序
                sorted_keys = sorted(self.access_times.items(), 
                                   key=lambda x: x[1])
                # 删除最早访问的项
                oldest_key = sorted_keys[0][0]
                del self.cache[oldest_key]
                del self.access_times[oldest_key]
                
            # 添加新项
            self.cache[key] = value
            self.access_times[key] = time.time()
            
    def clear(self):
        """清空缓存"""
        with self._lock:
            self.cache.clear()
            self.access_times.clear()

class ResourceManager:
    """
    资源管理类
    
    管理程序运行过程中的各种资源:
    - 文件句柄
    - 进程池
    - 内存使用
    
    特性:
    - 自动关闭资源
    - 控制资源使用上限
    - 监控资源使用情况
    """
    
    def __init__(self):
        """初始化资源管理器"""
        self.file_handles = {}  # 文件句柄字典
        self.process_pools = {}  # 进程池字典
        self._lock = multiprocessing.Lock()  # 线程锁
        
    def get_file_handle(self, path, mode='r'):
        """获取文件句柄"""
        with self._lock:
            key = (path, mode)
            if key not in self.file_handles:
                self.file_handles[key] = open(path, mode)
            return self.file_handles[key]
            
    def get_process_pool(self, name, max_workers=None):
        """获取进程池"""
        with self._lock:
            if name not in self.process_pools:
                if max_workers is None:
                    max_workers = multiprocessing.cpu_count()
                self.process_pools[name] = ProcessPoolExecutor(
                    max_workers=max_workers
                )
            return self.process_pools[name]
            
    def close_all(self):
        """关闭所有资源"""
        with self._lock:
            # 关闭文件句柄
            for handle in self.file_handles.values():
                try:
                    handle.close()
                except:
                    pass
            self.file_handles.clear()
            
            # 关闭进程池
            for pool in self.process_pools.values():
                try:
                    pool.shutdown()
                except:
                    pass
            self.process_pools.clear()
            
    def __del__(self):
        """析构时关闭资源"""
        self.close_all()

class MemoryOptimizer:
    """
    内存优化器
    
    用于优化程序的内存使用:
    - 分批处理大文件
    - 及时释放内存
    - 控制并发数量
    
    特性:
    - 自动分批处理
    - 内存使用监控
    - 动态调整批大小
    """
    
    def __init__(self, target_memory_mb=1024):
        """
        初始化内存优化器
        
        参数:
            target_memory_mb: int, 目标内存使用量(MB)
        """
        self.target_memory = target_memory_mb * 1024 * 1024  # 转换为字节
        self.batch_size = 1000  # 初始批大小
        self._lock = multiprocessing.Lock()
        
    def get_memory_usage(self):
        """获取当前内存使用量"""
        import psutil
        process = psutil.Process()
        return process.memory_info().rss
        
    def optimize_batch_size(self):
        """优化批处理大小"""
        with self._lock:
            current_memory = self.get_memory_usage()
            
            # 根据内存使用情况调整批大小
            if current_memory > self.target_memory:
                self.batch_size = max(100, self.batch_size // 2)
            else:
                self.batch_size = min(10000, self.batch_size * 2)
                
            return self.batch_size
            
    def process_in_batches(self, items, processor):
        """
        分批处理数据
        
        参数:
            items: list, 待处理项列表
            processor: callable, 处理函数
        """
        results = []
        batch = []
        
        for item in items:
            batch.append(item)
            
            if len(batch) >= self.batch_size:
                # 处理当前批次
                results.extend(processor(batch))
                batch = []
                
                # 优化下一批的大小
                self.optimize_batch_size()
                
        # 处理剩余项
        if batch:
            results.extend(processor(batch))
            
        return results

# 创建全局资源管理器实例
resource_manager = ResourceManager()
memory_optimizer = MemoryOptimizer()

# 创建缓存实例
tlsh_cache = Cache()  # TLSH哈希值缓存
file_cache = Cache()  # 文件内容缓存
func_cache = Cache()  # 函数解析结果缓存

# 在程序退出时清理资源
import atexit
atexit.register(resource_manager.close_all)

"""全局配置和路径定义"""
# 基础路径配置
currentPath = "/home/rby/Project/project-file/dependency_analysis/centris"
theta = 0.1  # 相似度阈值 - 用于判断代码克隆的阈值

# 目录路径配置
resultPath = currentPath + "/Detector/"  # 结果输出路径
repoFuncPath = currentPath + "/OSS_Collector/repo_functions/"  # 仓库函数路径
verIDXpath = currentPath + "/Preprocessor/verIDX/"  # 版本索引路径
initialDBPath = currentPath + "/Preprocessor/initialSigs/"  # 初始签名数据库路径
finalDBPath = currentPath + "/Preprocessor/componentDB/"  # 最终组件数据库路径
metaPath = currentPath + "/Preprocessor/metaInfos/"  # 元信息路径
aveFuncPath = metaPath + "aveFuncs"  # 平均函数数量文件路径
weightPath = metaPath + "weights/"  # 权重文件路径
ctagsPath = "/usr/local/bin/ctags"  # ctags工具路径
log_path = currentPath + "/logs/Detector"  # 日志目录路径

# 性能监控配置
PERFORMANCE_MONITORING = True  # 是否启用性能监控
MONITORING_INTERVAL = 60  # 性能监控间隔(秒)

# 创建必要的目录
required_dirs = [
    log_path,
    resultPath,
    repoFuncPath,
    verIDXpath,
    initialDBPath,
    finalDBPath,
    metaPath,
    weightPath
]

for directory in required_dirs:
    if not os.path.isdir(directory):
        try:
            os.makedirs(directory)
            logging.info(f"创建目录: {directory}")
        except Exception as e:
            logging.error(f"创建目录 {directory} 失败: {e}")

# 生成日志文件名，包含时间戳
log_file = os.path.join(log_path, f"detector_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),  # 文件处理器
        logging.StreamHandler()  # 控制台处理器
    ]
)

class PerformanceMonitor:
    """
    性能监控类
    
    用于监控和记录程序运行过程中的性能指标:
    - CPU使用率
    - 内存使用情况
    - 处理速度
    - 资源消耗
    """
    
    def __init__(self):
        """初始化性能监控器"""
        self.start_time = time.time()
        self.processed_items = 0
        self.last_log_time = self.start_time
        
    def update(self, items=1):
        """
        更新处理项数并记录性能指标
        
        参数:
            items: int, 新处理的项数
        """
        self.processed_items += items
        current_time = time.time()
        
        # 检查是否需要记录性能指标
        if current_time - self.last_log_time >= MONITORING_INTERVAL:
            elapsed = current_time - self.start_time
            rate = self.processed_items / elapsed
            
            # 记录性能指标
            logging.info(f"性能统计:")
            logging.info(f"- 总处理项数: {self.processed_items}")
            logging.info(f"- 运行时间: {elapsed:.2f}秒")
            logging.info(f"- 处理速率: {rate:.2f}项/秒")
            
            self.last_log_time = current_time

def validate_input_path(path):
    """
    验证输入路径的有效性
    
    检查:
    1. 路径是否存在
    2. 是否为目录
    3. 是否可读
    4. 是否包含源代码文件
    
    参数:
        path: str, 输入路径
        
    返回:
        bool: 路径是否有效
        
    抛出:
        ValueError: 当路径无效时
    """
    if not os.path.exists(path):
        raise ValueError(f"路径不存在: {path}")
    
    if not os.path.isdir(path):
        raise ValueError(f"路径不是目录: {path}")
        
    if not os.access(path, os.R_OK):
        raise ValueError(f"路径不可读: {path}")
        
    # 检查是否包含源代码文件
    has_source = False
    for root, _, files in os.walk(path):
        if any(f.endswith(('.c', '.cc', '.cpp')) for f in files):
            has_source = True
            break
            
    if not has_source:
        raise ValueError(f"目录中未找到C/C++源代码文件: {path}")
        
    return True

def computeTlsh(string):
    """
    生成字符串的TLSH哈希值
    
    TLSH(Trend Micro Locality Sensitive Hash)是一种局部敏感哈希算法，
    用于计算字符串相似度。该算法具有以下特点:
    1. 相似的输入会产生相似的哈希值
    2. 对输入的细微改变不敏感
    3. 适合用于代码克隆检测
    
    参数:
        string: str, 待计算哈希值的字符串
        
    返回:
        str: 计算得到的TLSH哈希值
        
    示例:
        >>> hash_value = computeTlsh("int main() { return 0; }")
        >>> print(hash_value)
        'T1A123...'
    """
    try:
        # 将输入字符串转换为字节串
        string = str.encode(string)
        
        # 计算TLSH哈希值
        hs = tlsh.forcehash(string)
        
        return hs
    except Exception as e:
        logging.error(f"计算TLSH哈希值时出错: {e}")
        return None

def removeComment(string):
    """
    移除C/C++风格的注释
    
    处理两种类型的注释:
    1. 单行注释 (//)
    2. 多行注释 (/* */)
    
    使用正则表达式进行匹配和替换，保留代码的其他部分不变
    
    参数:
        string: str, 包含注释的源代码字符串
        
    返回:
        str: 去除注释后的代码字符串
        
    示例:
        >>> code = "int x = 1; // 初始化x\n/* 这是\n多行注释 */\nint y = 2;"
        >>> print(removeComment(code))
        'int x = 1; \nint y = 2;'
    """
    try:
        # 定义匹配注释的正则表达式
        c_regex = re.compile(
            r'(?P<comment>//.*?$|[{}]+)|(?P<multilinecomment>/\*.*?\*/)|(?P<noncomment>\'(\\.|[^\\\'])*\'|"(\\.|[^\\"])*"|.[^/\'"]*)',
            re.DOTALL | re.MULTILINE
        )
        
        # 提取非注释部分
        result = ''.join([c.group('noncomment') for c in c_regex.finditer(string) if c.group('noncomment')])
        
        return result
    except Exception as e:
        logging.error(f"移除注释时出错: {e}")
        return string

def normalize(string):
    """
    标准化输入字符串
    
    执行以下标准化步骤:
    1. 移除所有换行符(\n)、回车符(\r)和制表符(\t)
    2. 移除所有花括号({})
    3. 移除所有空格
    4. 将所有字符转换为小写
    
    这种标准化处理可以:
    - 消除代码格式化差异的影响
    - 便于后续的相似度比较
    
    参数:
        string: str, 待标准化的源代码字符串
        
    返回:
        str: 标准化后的字符串
        
    示例:
        >>> code = "void main() {\n    printf('Hello');\n}"
        >>> print(normalize(code))
        'voidmainprintf('hello');'
    """
    try:
        # 执行标准化处理
        normalized = string.replace('\n', '')  # 移除换行符
        normalized = normalized.replace('\r', '')  # 移除回车符
        normalized = normalized.replace('\t', '')  # 移除制表符
        normalized = normalized.replace('{', '')  # 移除左花括号
        normalized = normalized.replace('}', '')  # 移除右花括号
        normalized = ''.join(normalized.split())  # 移除所有空格
        normalized = normalized.lower()  # 转换为小写
        
        return normalized
    except Exception as e:
        logging.error(f"标准化字符串时出错: {e}")
        return string

def process_single_file(file_info):
    """
    处理单个文件的函数
    
    参数:
        file_info: tuple (filePath, repoPath)
            filePath: 文件完整路径
            repoPath: 仓库根路径
    
    返回:
        tuple: (file_result, file_count, func_count, line_count)
            file_result: dict, 该文件的哈希结果
            file_count: int, 处理文件数(0或1)
            func_count: int, 函数数量
            line_count: int, 代码行数
    """
    filePath, repoPath = file_info
    
    # 使用文件缓存
    cached_content = file_cache.get(filePath)
    if cached_content:
        return cached_content
        
    # 使用资源管理器获取文件句柄
    try:
        f = resource_manager.get_file_handle(filePath, 'r')
        lines = f.readlines()
    except Exception as e:
        logging.error(f"读取文件失败: {e}")
        return {}, 0, 0, 0

    # 初始化返回值
    file_result = {}
    file_count = 0
    func_count = 0
    line_count = 0
    
    try:
        # 使用ctags提取函数信息
        functionList = subprocess.check_output(ctagsPath + ' -f - --kinds-C=* --fields=neKSt "' + filePath + '"',
                                            stderr=subprocess.STDOUT, shell=True).decode()

        # 打开并读取源文件内容
        with open(filePath, 'r', encoding="UTF-8") as f:
            lines = f.readlines()

        # 初始化函数解析变量
        allFuncs = str(functionList).split('\n')
        func = re.compile(r'(function)')
        number = re.compile(r'(\d+)')
        funcSearch = re.compile(r'{([\S\s]*)}')

        file_count = 1

        # 处理文件中的每个函数
        for i in allFuncs:
            elemList = re.sub(r'[\t\s ]{2,}', '', i)
            elemList = elemList.split('\t')
            funcBody = ""

            if i != '' and len(elemList) >= 8 and func.fullmatch(elemList[3]):
                funcStartLine = int(number.search(elemList[4]).group(0))
                funcEndLine = int(number.search(elemList[7]).group(0))

                tmpString = "".join(lines[funcStartLine - 1 : funcEndLine])

                if funcSearch.search(tmpString):
                    funcBody = funcBody + funcSearch.search(tmpString).group(1)
                else:
                    funcBody = " "

                funcBody = removeComment(funcBody)
                funcBody = normalize(funcBody)
                funcHash = computeTlsh(funcBody)

                if len(funcHash) == 72 and funcHash.startswith("T1"):
                    funcHash = funcHash[2:]
                elif funcHash == "TNULL" or funcHash == "" or funcHash == "NULL":
                    continue

                storedPath = filePath.replace(repoPath, "")
                if funcHash not in file_result:
                    file_result[funcHash] = []
                file_result[funcHash].append(storedPath)

                line_count += len(lines)
                func_count += 1

    except Exception as e:
        logging.error(f"处理文件 {filePath} 时出错: {e}")
        
    # 缓存结果
    result = (file_result, file_count, func_count, line_count)
    file_cache.set(filePath, result)
    
    return result

def hashing(repoPath):
    """
    使用多进程对仓库中的C/C++函数进行哈希处理
    """
    perf_monitor = PerformanceMonitor()
    
    possible = (".c", ".cc", ".cpp")
    
    logging.info(f"开始处理仓库: {repoPath}")
    
    # 收集所有需要处理的文件
    files_to_process = []
    for path, _, files in os.walk(repoPath):
        for file in files:
            if file.endswith(possible):
                filePath = os.path.join(path, file)
                files_to_process.append((filePath, repoPath))

    total_files = len(files_to_process)
    logging.info(f"找到 {total_files} 个待处理的C/C++源文件")

    # 初始化结果
    final_dict = {}
    processed_files = 0
    total_funcs = 0
    total_lines = 0
    
    num_processes = multiprocessing.cpu_count()
    logging.info(f"使用 {num_processes} 个进程并行处理文件")

    # 使用进程池并行处理文件
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        # 提交所有任务
        future_to_file = {executor.submit(process_single_file, file_info): file_info 
                         for file_info in files_to_process}
        
        # 处理完成的任务结果
        for future in concurrent.futures.as_completed(future_to_file):
            file_info = future_to_file[future]
            try:
                file_result, file_count, func_count, line_count = future.result()
                
                # 合并哈希结果
                for hash_val, paths in file_result.items():
                    if hash_val not in final_dict:
                        final_dict[hash_val] = []
                    final_dict[hash_val].extend(paths)
                
                # 累加统计数据
                processed_files += file_count
                total_funcs += func_count
                total_lines += line_count
                
                
            except Exception as e:
                logging.error(f"处理文件 {file_info[0]} 时发生错误: {e}")

    logging.info(f"仓库处理完成: 处理了 {processed_files} 个文件, {total_funcs} 个函数, 共 {total_lines} 行代码")
    return final_dict, processed_files, total_funcs, total_lines

def getAveFuncs():
    """
    获取平均函数数量
    
    功能:
    - 从指定的 aveFuncPath 文件中读取仓库函数统计信息
    - 文件格式为 JSON，包含每个仓库的平均函数数量数据
    返回:
    - aveFuncs: dict 类型
        - key: 仓库名称(str)
        - value: 该仓库的平均函数数量(float/int)

    """
    # 初始化空字典存储结果
    aveFuncs = {}
    
    # 以 UTF-8 编码打开文件读取 JSON 数据
    with open(aveFuncPath, 'r', encoding = "UTF-8") as fp:
        aveFuncs = json.load(fp)
    
    return aveFuncs

def readComponentDB():
    """
    读取组件数据库
    
    功能:
    - 遍历 finalDBPath 目录下的所有组件签名文件
    - 为每个开源组件(OSS)收集其函数哈希值
    
    返回:
    - componentDB: dict类型
        - key: 开源组件名称
        - value: 该组件包含的所有函数哈希值列表
    """
    componentDB = {}
    jsonLst = []

    for OSS in os.listdir(finalDBPath):
        componentDB[OSS] = []
        with open(finalDBPath + OSS, 'r', encoding = "UTF-8") as fp:
            jsonLst = json.load(fp)

            for eachHash in jsonLst:
                hashval = eachHash["hash"]
                componentDB[OSS].append(hashval)

    return componentDB

def readAllVers(repoName):
    """
    读取仓库的所有版本信息
    
    功能:
    - 从版本索引文件中读取指定仓库的版本信息
    - 构建版本号列表和版本索引映射
    
    参数:
        repoName: str, 仓库名称
    
    返回:
        allVerList: list, 所有版本号的列表
        idx2Ver: dict, 版本索引到版本号的映射
            - key: 版本索引(int)
            - value: 版本号(str)
    """
    allVerList = []
    idx2Ver = {}
    
    with open(verIDXpath + repoName + "_idx", 'r', encoding = "UTF-8") as fp:
        tempVerList = json.load(fp)

        for eachVer in tempVerList:
            allVerList.append(eachVer["ver"])
            idx2Ver[eachVer["idx"]] = eachVer["ver"]

    return allVerList, idx2Ver

def readWeigts(repoName):
    """
    读取仓库函数的权重信息
    
    功能:
    - 从权重文件中读取指定仓库的函数权重信息
    - 权重用于版本匹配时的相似度计算
    
    参数:
        repoName: str, 仓库名称
    
    返回:
        weightDict: dict, 函数权重映射
            - key: 函数哈希值
            - value: 对应的权重值
    """
    weightDict = {}

    with open(weightPath + repoName + "_weights", 'r', encoding = "UTF-8") as fp:
        weightDict = json.load(fp)

    return weightDict

def process_single_component(component_info):
    """
    处理单个组件的函数
    
    参数:
        component_info: tuple (OSS, inputDict, inputRepo, aveFuncs)
            OSS: 组件名称
            inputDict: 输入代码的哈希字典
            inputRepo: 输入仓库名称
            aveFuncs: 平均函数数量字典
    
    返回:
        result_line: 检测结果行，如果没有匹配则返回None
    """
    OSS, inputDict, inputRepo, aveFuncs = component_info
    
    try:
        commonFunc = []  # 存储共同函数
        repoName = OSS.split('_sig')[0]  # 提取组件名称
        totOSSFuncs = float(aveFuncs[repoName])  # 获取组件的平均函数数量
        
        if totOSSFuncs == 0.0:
            return None
            
        # 计算共同函数数量
        comOSSFuncs = 0.0
        for hashval in componentDB[OSS]:
            if hashval in inputDict:
                commonFunc.append(hashval)
                comOSSFuncs += 1.0

        # 如果相似度超过阈值，进行详细分析
        if (comOSSFuncs/totOSSFuncs) >= theta:
            # 版本预测
            verPredictDict = {}  # 存储版本预测结果
            allVerList, idx2Ver = readAllVers(repoName)
            
            # 初始化版本预测权重
            for eachVersion in allVerList:
                verPredictDict[eachVersion] = 0.0

            # 读取函数权重信息
            weightDict = readWeigts(repoName)

            # 计算各版本的加权得分
            with open(initialDBPath + OSS, 'r', encoding = "UTF-8") as fi:
                jsonLst = json.load(fi)
                for eachHash in jsonLst:
                    hashval = eachHash["hash"]
                    verlist = eachHash["vers"]

                    if hashval in commonFunc:
                        for addedVer in verlist:
                            verPredictDict[idx2Ver[addedVer]] += weightDict[hashval]

            # 选择得分最高的版本作为预测结果
            sortedByWeight = sorted(verPredictDict.items(), key=lambda x: x[1], reverse=True)
            predictedVer = sortedByWeight[0][0]
            
            # 分析函数使用情况
            predictOSSDict = {}  # 存储预测版本的函数信息
            with open(repoFuncPath + repoName + '/fuzzy_' + predictedVer + '.hidx', 'r', encoding = "UTF-8") as fo:
                body = ''.join(fo.readlines()).strip()
                for eachLine in body.split('\n')[1:]:
                    ohash = eachLine.split('\t')[0]
                    opath = eachLine.split('\t')[1]
                    predictOSSDict[ohash] = opath.split('\t')

            # 统计函数使用情况
            used = 0      # 直接使用的函数数量
            unused = 0    # 未使用的函数数量
            modified = 0  # 修改过的函数数量
            strChange = False  # 结构变化标记

            # 分析每个函数的使用情况
            for ohash in predictOSSDict:
                flag = 0  # 函数匹配标记

                # 检查完全匹配的函数
                if ohash in inputDict:
                    used += 1
                    # 检查函数位置是否发生变化
                    nflag = 0
                    for opath in predictOSSDict[ohash]:
                        for tpath in inputDict[ohash]:
                            if opath in tpath:
                                nflag = 1
                    if nflag == 0:
                        strChange = True
                    flag = 1
                    
                else:
                    # 检查修改过的函数(基于TLSH相似度)
                    for thash in inputDict:
                        score = tlsh.diffxlen(ohash, thash)
                        if int(score) <= 30:  # TLSH相似度阈值
                            modified += 1
                            # 检查修改函数的位置变化
                            nflag = 0
                            for opath in predictOSSDict[ohash]:
                                for tpath in inputDict[thash]:
                                    if opath in tpath:
                                        nflag = 1
                            if nflag == 0:
                                strChange = True
                            flag = 1
                            break

                # 未使用的函数计数
                if flag == 0:
                    unused += 1

            # 返回检测结果
            return '\t'.join([inputRepo, repoName, predictedVer, 
                            str(used), str(unused), str(modified), 
                            str(strChange)])
                            
    except Exception as e:
        logging.error(f"处理组件 {OSS} 时发生错误: {e}")
        return None

def detector(inputDict, inputRepo):
    """代码克隆检测的主要逻辑实现"""
    perf_monitor = PerformanceMonitor()
    
    # 读取组件数据库
    logging.info(f"开始检测仓库: {inputRepo}")
    logging.info("正在加载组件数据库...")
    global componentDB  # 声明为全局变量，以便进程间共享
    componentDB = readComponentDB()
    logging.info(f"已加载 {len(componentDB)} 个组件的数据")
    
    # 获取各组件的平均函数数量
    aveFuncs = getAveFuncs()
    
    # 准备并行处理的组件列表
    components_to_process = [
        (OSS, inputDict, inputRepo, aveFuncs) 
        for OSS in componentDB
    ]
    
    total_components = len(components_to_process)
    processed_components = 0
    
    num_processes = multiprocessing.cpu_count()
    logging.info(f"使用 {num_processes} 个进程并行处理组件")
    
    # 打开结果文件
    with open(resultPath + "result_" + inputRepo, 'w') as fres:
        # 使用进程池并行处理组件
        with ProcessPoolExecutor(max_workers=num_processes) as executor:
            # 提交所有任务
            future_to_component = {
                executor.submit(process_single_component, component_info): component_info[0]
                for component_info in components_to_process
            }
            
            # 处理完成的任务结果
            for future in concurrent.futures.as_completed(future_to_component):
                OSS = future_to_component[future]
                processed_components += 1
                
                try:
                    result = future.result()
                    if result:
                        fres.write(result + '\n')
                        logging.info(f"发现匹配组件: {OSS}")
                    
                    # 输出进度
                    progress = (processed_components / total_components) * 100
                    if processed_components % 10 == 0:  # 每处理10个组件输出一次进度
                        logging.info(f"组件分析进度: {progress:.2f}% ({processed_components}/{total_components})")
                        
                    perf_monitor.update()  # 更新性能统计
                    
                except Exception as e:
                    logging.error(f"处理组件 {OSS} 的结果时发生错误: {e}")

    logging.info(f"检测完成: {inputRepo}")

def main(inputPath, inputRepo):
    """
    主函数
    参数:
        inputPath: 输入代码路径
        inputRepo: 输入仓库名称
    
    处理流程:
    1. 调用hashing()对输入代码进行哈希处理
    2. 调用detector()执行检测过程
    """
    try:
        resDict, fileCnt, funcCnt, lineCnt = hashing(inputPath)
        detector(resDict, inputRepo)
    finally:
        # 清理所有资源
        resource_manager.close_all()
        # 清理缓存
        tlsh_cache.clear()
        file_cache.clear() 
        func_cache.clear()

# 程序入口
if __name__ == "__main__":
    """
    程序入口点
    
    支持两种运行模式:
    - 测试模式: 使用预设的crown项目路径
    - 正常模式: 从命令行参数获取项目路径
    """
    testmode = 0  # 初始化测试模式标志

    if testmode:
        inputPath = currentPath + "/crown"
    else:
        inputPath = sys.argv[1]

    inputRepo = inputPath.split('/')[-1]

    main(inputPath, inputRepo)
