"""
预处理器 - 用于处理开源代码库的函数提取和分析

该模块实现了以下主要功能:
1. 提取仓库版本日期信息
2. 消除冗余函数
3. 保存元信息
4. 代码分割

主要类:
- Cache: 缓存计算结果
- ResourceManager: 管理文件句柄等资源
- PerformanceMonitor: 监控处理性能
- MemoryOptimizer: 优化内存使用

作者: byRen2002
修改日期: 2024年10月25日
许可证: MIT License
"""

import os
import sys
import re
import shutil
import json
import math
import tlsh
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
import concurrent.futures
import logging
import datetime
import time

# 缓存配置
CACHE_SIZE = 1000  # 缓存大小限制
CACHE_EXPIRE = 3600  # 缓存过期时间(秒)

class Cache:
    """
    通用缓存类
    
    用于缓存计算结果,减少重复计算:
    - TLSH哈希值缓存
    - 文件内容缓存
    - 函数解析结果缓存
    """
    
    def __init__(self, max_size=CACHE_SIZE, expire=CACHE_EXPIRE):
        self.cache = {}
        self.max_size = max_size
        self.expire = expire
        self.access_times = {}
        self._lock = multiprocessing.Lock()
        
    def get(self, key):
        """获取缓存值"""
        with self._lock:
            if key not in self.cache:
                return None
                
            access_time = self.access_times[key]
            if time.time() - access_time > self.expire:
                del self.cache[key]
                del self.access_times[key]
                return None
                
            self.access_times[key] = time.time()
            return self.cache[key]
            
    def set(self, key, value):
        """设置缓存值"""
        with self._lock:
            if len(self.cache) >= self.max_size:
                sorted_keys = sorted(self.access_times.items(), 
                                   key=lambda x: x[1])
                oldest_key = sorted_keys[0][0]
                del self.cache[oldest_key]
                del self.access_times[oldest_key]
                
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
    """
    
    def __init__(self):
        self.file_handles = {}
        self.process_pools = {}
        self._lock = multiprocessing.Lock()
        
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
            for handle in self.file_handles.values():
                try:
                    handle.close()
                except:
                    pass
            self.file_handles.clear()
            
            for pool in self.process_pools.values():
                try:
                    pool.shutdown()
                except:
                    pass
            self.process_pools.clear()
            
    def __del__(self):
        """析构时关闭资源"""
        self.close_all()

class PerformanceMonitor:
    """
    性能监控类
    
    用于监控和记录程序运行过程中的性能指标:
    - 处理速度
    - 资源消耗
    - 进度统计
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.processed_items = 0
        self.last_log_time = self.start_time
        
    def update(self, items=1):
        """更新处理项数并记录性能指标"""
        self.processed_items += items
        current_time = time.time()
        
        if current_time - self.last_log_time >= 60:  # 每60秒记录一次
            elapsed = current_time - self.start_time
            rate = self.processed_items / elapsed
            
            logging.info(f"性能统计:")
            logging.info(f"- 总处理项数: {self.processed_items}")
            logging.info(f"- 运行时间: {elapsed:.2f}秒")
            logging.info(f"- 处理速率: {rate:.2f}项/秒")
            
            self.last_log_time = current_time

class MemoryOptimizer:
    """
    内存优化器
    
    用于优化程序的内存使用:
    - 分批处理大文件
    - 及时释放内存
    - 控制并发数量
    """
    
    def __init__(self, target_memory_mb=1024):
        self.target_memory = target_memory_mb * 1024 * 1024
        self.batch_size = 1000
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
                results.extend(processor(batch))
                batch = []
                self.optimize_batch_size()
                
        if batch:
            results.extend(processor(batch))
            
        return results

# 全局配置
currentPath = "/home/rby/Project/project-file/dependency_analysis/centris"
separator = "#@#"
sep_len = len(separator)
theta = 0.1

# 路径配置
tagDatePath = currentPath + "/OSS_Collector/repo_date/"
resultPath = currentPath + "/OSS_Collector/repo_functions/"
verIDXpath = currentPath + "/Preprocessor/verIDX/"
initialDBPath = currentPath + "/Preprocessor/initialSigs/"
finalDBPath = currentPath + "/Preprocessor/componentDB/"
metaPath = currentPath + "/Preprocessor/metaInfos/"
weightPath = metaPath + "/weights/"
funcDatePath = currentPath + "/Preprocessor/funcDate/"
log_path = currentPath + "/logs/Preprocessor"

# 创建必要目录
required_dirs = [
    verIDXpath,
    initialDBPath, 
    finalDBPath,
    metaPath,
    funcDatePath,
    weightPath,
    log_path
]

for directory in required_dirs:
    if not os.path.isdir(directory):
        try:
            os.makedirs(directory)
            logging.info(f"创建目录: {directory}")
        except Exception as e:
            logging.error(f"创建目录 {directory} 失败: {e}")

# 配置日志
log_file = os.path.join(log_path, 
    f"preprocessor_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 创建全局资源管理器实例
resource_manager = ResourceManager()
memory_optimizer = MemoryOptimizer()

# 创建缓存实例
tlsh_cache = Cache()
file_cache = Cache()
func_cache = Cache()

# 注册退出时的资源清理
import atexit
atexit.register(resource_manager.close_all)

def extractVerDate(repoName):
    """提取版本日期信息"""
    verDateDict = {}
    repo_path = os.path.join(tagDatePath, repoName)
    
    if not os.path.isfile(repo_path):
        return verDateDict
        
    try:
        with open(repo_path, 'r', encoding="UTF-8") as fp:
            for line in fp:
                if "tag:" not in line:
                    continue
                    
                line = line.strip()
                date = line[0:10]
                
                tags = re.findall(r'tag:\s*([^,)]+)', line)
                
                for tag in tags:
                    version = tag.strip()
                    if version:
                        verDateDict[version] = date
                        
    except Exception as e:
        logging.error(f"处理仓库 {repoName} 时发生错误: {e}")
        
    return verDateDict

def process_single_repo(repoName):
    """处理单个仓库"""
    try:
        logging.info(f"开始处理: {repoName}")
        
        funcDateDict = {}
        tempDateDict = {}
        verDateDict = extractVerDate(repoName)
        
        verTempLst = []
        signature = {}
        verDict = {}
        idx = 0
        
        # 获取版本列表
        for eachVersion in os.listdir(os.path.join(resultPath, repoName)):
            versionName = eachVersion.split("fuzzy_")[1].replace(".hidx", "")
            if versionName == '' or versionName == ' ':
                continue
            verTempLst.append(versionName)
        verTempLst.sort()
        
        # 处理每个版本
        for versionName in verTempLst:
            verDict[versionName] = idx
            idx += 1
            
            with open(os.path.join(resultPath, repoName, 
                     ("fuzzy_" + versionName + ".hidx")), 'r', encoding="UTF-8") as fp:
                next(fp)
                for line in fp:
                    if line.strip() == '' or line.strip() == ' ':
                        continue
                        
                    hashval = line.split('\t')[0]
                    if hashval not in signature:
                        signature[hashval] = []
                        tempDateDict[hashval] = []
                    signature[hashval].append(str(idx-1))
                    
                    if versionName in verDateDict:
                        tempDateDict[hashval].append(verDateDict[versionName])
                    else:
                        tempDateDict[hashval].append("NODATE")
        
        # 存储函数日期
        for hashval in tempDateDict:
            tempDateDict[hashval].sort()
            funcDateDict[hashval] = tempDateDict[hashval][0]
        
        # 写入函数日期文件
        with open(funcDatePath + repoName + "_funcdate", 'w') as fdate:
            for hashval in funcDateDict:
                fdate.write(hashval + '\t' + funcDateDict[hashval] + '\n')
        
        # 存储版本索引
        with open(verIDXpath + repoName + "_idx", 'w') as fidx:
            saveJson = []
            for verName in verTempLst:
                temp = {"ver": verName, "idx": str(verDict[verName])}
                saveJson.append(temp)
            fidx.write(json.dumps(saveJson))
        
        # 存储OSS签名
        with open(initialDBPath + repoName + "_sig", 'w') as f:
            saveJson = []
            for hashval in signature:
                temp = {"hash": hashval, "vers": signature[hashval]}
                saveJson.append(temp)
            f.write(json.dumps(saveJson))
            
        return repoName
        
    except Exception as e:
        logging.error(f"处理仓库 {repoName} 时发生错误: {e}")
        return None

def redundancyElimination():
    """使用ProcessPoolExecutor进行并行的冗余消除"""
    perf_monitor = PerformanceMonitor()
    
    repo_list = os.listdir(resultPath)
    total_repos = len(repo_list)
    logging.info(f"开始处理 {total_repos} 个仓库")
    
    num_processes = multiprocessing.cpu_count()
    logging.info(f"使用 {num_processes} 个进程进行冗余消除")
    
    processed = 0
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        future_to_repo = {
            executor.submit(process_single_repo, repo): repo 
            for repo in repo_list
        }
        
        for future in concurrent.futures.as_completed(future_to_repo):
            repo = future_to_repo[future]
            processed += 1
            try:
                result = future.result()
                if result:
                    logging.info(f"成功处理仓库: {result}")
                    
                progress = (processed / total_repos) * 100
                if processed % 10 == 0:
                    logging.info(f"进度: {progress:.2f}% ({processed}/{total_repos})")
                    
                perf_monitor.update()
                    
            except Exception as e:
                logging.error(f"处理仓库 {repo} 时发生错误: {e}")

def process_single_meta(OSS):
    """处理单个仓库的元信息"""
    try:
        weightJson = {}
        repoName = OSS.replace("_sig", "")
        totFuncs = 0
        totVers = len(os.listdir(resultPath + repoName))
        
        if totVers == 0:
            return None
            
        result = {
            'repoName': repoName,
            'aveFuncs': 0,
            'allFuncs': 0,
            'unique': {},
            'weights': {}
        }
        
        with open(initialDBPath + OSS, 'r', encoding="UTF-8") as fs:
            jsonStr = json.load(fs)
            totFuncs = len(jsonStr)
            
            for eachJson in jsonStr:
                hashval = eachJson['hash']
                verlst = eachJson['vers']
                
                result['unique'][hashval] = repoName
                weightJson[hashval] = math.log(float(totVers)/float(len(verlst)))

            result['aveFuncs'] = int(totFuncs/totVers)
            result['allFuncs'] = int(totFuncs)
            result['weights'] = weightJson

        with open(weightPath + "/" + repoName + "_weights", 'w') as fwei:
            fwei.write(json.dumps(weightJson))
            
        return result
        
    except Exception as e:
        logging.error(f"处理仓库元信息 {OSS} 时发生错误: {e}")
        return None

def saveMetaInfos():
    """使用ProcessPoolExecutor并行保存元信息"""
    perf_monitor = PerformanceMonitor()
    
    aveFuncJson = {}
    allFuncJson = {}
    unique = {}
    
    OSS_list = os.listdir(initialDBPath)
    total_oss = len(OSS_list)
    logging.info(f"开始处理 {total_oss} 个仓库的元信息")
    
    num_processes = multiprocessing.cpu_count()
    logging.info(f"使用 {num_processes} 个进程处理元信息")
    
    processed = 0
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        future_to_oss = {
            executor.submit(process_single_meta, oss): oss 
            for oss in OSS_list
        }
        
        for future in concurrent.futures.as_completed(future_to_oss):
            processed += 1
            try:
                result = future.result()
                if result:
                    repoName = result['repoName']
                    aveFuncJson[repoName] = result['aveFuncs']
                    allFuncJson[repoName] = result['allFuncs']
                    unique.update(result['unique'])
                    
                progress = (processed / total_oss) * 100
                if processed % 10 == 0:
                    logging.info(f"进度: {progress:.2f}% ({processed}/{total_oss})")
                    
                perf_monitor.update()
                    
            except Exception as e:
                logging.error(f"处理元信息时发生错误: {e}")
    
    # 写入最终结果
    with open(metaPath + "aveFuncs", 'w') as fave:
        fave.write(json.dumps(aveFuncJson))
    
    with open(metaPath + "allFuncs", 'w') as fall:
        fall.write(json.dumps(allFuncJson))
    
    uniqueJson = []
    for hashval in unique:
        temp = {"hash": hashval, "OSS": [unique[hashval]]}
        uniqueJson.append(temp)
    
    with open(metaPath + "uniqueFuncs", 'w') as funi:
        funi.write(json.dumps(uniqueJson))

def readVerDate(verDateDict, repoName):
    """读取版本日期"""
    verDateDict[repoName] = {}

    if os.path.isfile(funcDatePath + repoName + "_funcdate"):
        with open(funcDatePath + repoName + "_funcdate", 'r', encoding="UTF-8") as fp:
            for eachLine in fp:
                eachLine = eachLine.strip()
                if eachLine:
                    hashval, date = eachLine.split('\t')
                    verDateDict[repoName][hashval] = date
    return verDateDict

def getAveFuncs():
    """获取平均函数数"""
    with open(metaPath + "aveFuncs", 'r', encoding = "UTF-8") as fp:
        return json.load(fp)

def process_single_segmentation(S_sig, aveFuncs, uniqueFuncs):
    """处理单个仓库的代码分割"""
    try:
        S = S_sig.replace("_sig", "")
        possibleMembers = {}
        candiX = {}
        removedFuncs = []
        verDateDict = {}
        
        verDateDict = readVerDate(verDateDict, S)
        
        with open(initialDBPath + S_sig, 'r', encoding="UTF-8") as fs:
            jsonStr = json.load(fs)
            if len(jsonStr) == 0:
                return None
                
            temp = {}
            for eachVal in jsonStr:
                hashval = eachVal['hash']
                
                for OSS in uniqueFuncs[hashval]:
                    if OSS == S:
                        continue

                    if OSS not in candiX:
                        temp[OSS] = []
                        candiX[OSS] = 0

                    if OSS not in verDateDict:
                        verDateDict = readVerDate(verDateDict, OSS)
                    
                    try:
                        for S_hashval in verDateDict[S]:
                            score = tlsh.diffxlen(hashval, S_hashval)
                            if int(score) <= 30:
                                if verDateDict[S][hashval] == "NODATE" or verDateDict[OSS][hashval] == "NODATE":
                                    candiX[OSS] += 1
                                    temp[OSS].append(hashval)
                                elif verDateDict[OSS][hashval] <= verDateDict[S][hashval]:
                                    candiX[OSS] += 1
                                    temp[OSS].append(hashval)
                    except:
                        pass

            for X in candiX:
                if aveFuncs[X] == 0 or len(verDateDict[X]) == 0:
                    continue
                elif (float(candiX[X])/float(aveFuncs[X])) >= theta:
                    if S not in possibleMembers:
                        possibleMembers[S] = []
                    possibleMembers[S].append(X)
                    removedFuncs.extend(temp[X])

            if S not in possibleMembers:
                shutil.copy(os.path.join(initialDBPath, S)+"_sig", 
                          os.path.join(finalDBPath, S)+"_sig")
            else:
                removedFuncs = set(removedFuncs)
                saveJson = []
                with open(os.path.join(finalDBPath, S)+"_sig", 'w') as fres:
                    for eachVal in jsonStr:
                        hashval = eachVal['hash']
                        if hashval not in removedFuncs:
                            versLst = eachVal['vers']
                            temp = {"hash": hashval, "vers": versLst}
                            saveJson.append(temp)
                    fres.write(json.dumps(saveJson))
        
        return S_sig
        
    except Exception as e:
        logging.error(f"处理仓库分割 {S_sig} 时发生错误: {e}")
        return None

def codeSegmentation():
    """使用ProcessPoolExecutor并行进行代码分割"""
    perf_monitor = PerformanceMonitor()
    
    aveFuncs = getAveFuncs()
    
    uniqueFuncs = {}
    with open(metaPath + "uniqueFuncs", 'r', encoding="UTF-8") as fp:
        jsonStr = json.load(fp)
        for eachVal in jsonStr:
            hashval = eachVal['hash']
            uniqueFuncs[hashval] = eachVal['OSS']
    
    OSS_list = os.listdir(initialDBPath)
    total_oss = len(OSS_list)
    logging.info(f'开始代码分割,共 {total_oss} 个仓库')
    
    num_processes = multiprocessing.cpu_count()
    logging.info(f"使用 {num_processes} 个进程进行代码分割")
    
    processed = 0
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        future_to_oss = {
            executor.submit(
                process_single_segmentation, 
                oss, 
                aveFuncs, 
                uniqueFuncs
            ): oss for oss in OSS_list
        }
        
        for future in concurrent.futures.as_completed(future_to_oss):
            processed += 1
            try:
                result = future.result()
                if result:
                    progress = (processed / total_oss) * 100
                    if processed % 10 == 0:
                        logging.info(f"进度: {progress:.2f}% ({processed}/{total_oss})")
                    
                    perf_monitor.update()
                    
            except Exception as e:
                logging.error(f"代码分割时发生错误: {e}")

def main():
    """主函数"""
    try:
        redundancyElimination()
        saveMetaInfos()
        codeSegmentation()
    finally:
        # 清理资源
        resource_manager.close_all()
        # 清理缓存
        tlsh_cache.clear()
        file_cache.clear()
        func_cache.clear()

if __name__ == "__main__":
    main()
