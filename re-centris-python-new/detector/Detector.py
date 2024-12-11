"""基于TLSH的代码克隆和依赖关系检测器"""

# 导入必要的库
import os, sys, subprocess, re, shutil, json, tlsh
from concurrent.futures import ProcessPoolExecutor
import multiprocessing, concurrent.futures
import logging, datetime, time

"""缓存配置"""
CACHE_SIZE = 1000  # 缓存大小限制
CACHE_EXPIRE = 3600  # 缓存过期时间(秒)

class Cache:
    """支持LRU淘汰、过期时间、大小限制和线程安全的通用缓存类"""
    
    def __init__(self, max_size=CACHE_SIZE, expire=CACHE_EXPIRE):
        self.cache = {}
        self.max_size = max_size
        self.expire = expire
        self.access_times = {}
        self._lock = multiprocessing.Lock()

class ResourceManager:
    """管理文件句柄和进程池等资源的管理器,支持自动关闭和使用监控"""
    
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
    """优化内存使用的工具类,支持分批处理、动态调整和内存监控"""
    
    def __init__(self, target_memory_mb=1024):
        """初始化内存优化器"""
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
        """分批处理数据"""
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
theta = 0.1  # 相似度阈值

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
    """监控和记录程序运行性能指标的工具类"""
    
    def __init__(self):
        """初始化性能监控器"""
        self.start_time = time.time()
        self.processed_items = 0
        self.last_log_time = self.start_time
        
    def update(self, items=1):
        """更新处理项数并记录性能指标"""
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
    """验证输入路径是否存在、可读且包含源代码文件"""
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
    """计算字符串的TLSH哈希值"""
    try:
        string = str.encode(string)
        hs = tlsh.forcehash(string)
        return hs
    except Exception as e:
        logging.error(f"计算TLSH哈希值时出错: {e}")
        return None

def removeComment(string):
    """移除C/C++代码中的注释"""
    try:
        c_regex = re.compile(
            r'(?P<comment>//.*?$|[{}]+)|(?P<multilinecomment>/\*.*?\*/)|(?P<noncomment>\'(\\.|[^\\\'])*\'|"(\\.|[^\\"])*"|.[^/\'"]*)',
            re.DOTALL | re.MULTILINE
        )
        result = ''.join([c.group('noncomment') for c in c_regex.finditer(string) if c.group('noncomment')])
        return result
    except Exception as e:
        logging.error(f"移除注释时出错: {e}")
        return string

def normalize(string):
    """标准化代码字符串,移除空白字符和格式化差异"""
    try:
        normalized = string.replace('\n', '')
        normalized = normalized.replace('\r', '')
        normalized = normalized.replace('\t', '')
        normalized = normalized.replace('{', '')
        normalized = normalized.replace('}', '')
        normalized = ''.join(normalized.split())
        normalized = normalized.lower()
        return normalized
    except Exception as e:
        logging.error(f"标准化字符串时出错: {e}")
        return string

def process_single_file(file_info):
    """处理单个文件,返回哈希结果和统计信息"""
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
    """使用多进程对仓库中的C/C++函数进行哈希处理"""
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
    """从JSON文件中读取仓库的平均函数数量统计信息"""
    aveFuncs = {}
    with open(aveFuncPath, 'r', encoding = "UTF-8") as fp:
        aveFuncs = json.load(fp)
    return aveFuncs

def readComponentDB():
    """读取组件数据库中的函数哈希值信息"""
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
    """读取仓库的版本信息和索引映射"""
    allVerList = []
    idx2Ver = {}
    
    with open(verIDXpath + repoName + "_idx", 'r', encoding = "UTF-8") as fp:
        tempVerList = json.load(fp)

        for eachVer in tempVerList:
            allVerList.append(eachVer["ver"])
            idx2Ver[eachVer["idx"]] = eachVer["ver"]

    return allVerList, idx2Ver

def readWeigts(repoName):
    """读取仓库函数的权重信息用于相似度计算"""
    weightDict = {}

    with open(weightPath + repoName + "_weights", 'r', encoding = "UTF-8") as fp:
        weightDict = json.load(fp)

    return weightDict

def process_single_component(component_info):
    """处理单个组件,分析代码克隆和依赖关系"""
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
    """执行代码克隆检测的主要逻辑"""
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
    """处理输入代码并执行克隆检测"""
    try:
        resDict, fileCnt, funcCnt, lineCnt = hashing(inputPath)
        detector(resDict, inputRepo)
    finally:
        resource_manager.close_all()
        tlsh_cache.clear()
        file_cache.clear() 
        func_cache.clear()

# 程序入口
if __name__ == "__main__":
    """根据运行模式选择输入路径并执行检测"""
    testmode = 0
    if testmode:
        inputPath = currentPath + "/crown"
    else:
        inputPath = sys.argv[1]
    inputRepo = inputPath.split('/')[-1]
    main(inputPath, inputRepo)
