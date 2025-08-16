"""
检测器模块
作者: Seunghoon Woo (seunghoonwoo@korea.ac.kr)
修改日期: 2020年12月16日
"""

# 导入必要的库
import os
import sys
import subprocess
import re
import shutil
import json
import tlsh
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import concurrent.futures
import logging
import datetime
"""全局变量定义"""
# 获取当前文件所在的目录
current_file_path = os.path.abspath(__file__)
# 获取项目根目录
analyse_file_dir = os.path.join(os.path.dirname(os.path.dirname(current_file_path)),"analyse_file")

theta = 0.1  # 相似度阈值
# 定义各种路径
resultPath = analyse_file_dir + "/detector/"  # 结果输出路径
repoFuncPath = analyse_file_dir + "/oss_collector/repo_functions/"  # 仓库函数路径
verIDXpath = analyse_file_dir + "/preprocessor/verIDX/"  # 版本索引路径
initialDBPath = analyse_file_dir + "/preprocessor/initialSigs/"  # 初始签名数据库路径
finalDBPath = analyse_file_dir + "/preprocessor/componentDB/"  # 最终组件数据库路径
metaPath = analyse_file_dir + "/preprocessor/metaInfos/"  # 元信息路径
aveFuncPath = metaPath + "aveFuncs"  # 平均函数数量文件路径
weightPath = metaPath + "weights/"  # 权重文件路径
ctagsPath = "/usr/local/bin/ctags"  # ctags工具路径
log_path = analyse_file_dir + "/logs/detector"                           # 创建日志目录

# 生成目录
shouldMake 	= [resultPath,log_path]
for eachRepo in shouldMake:
	if not os.path.isdir(eachRepo):
		os.mkdir(eachRepo)
        
# 生成日志文件名，包含时间戳
log_file = os.path.join(log_path, f"detector_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 修改日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),  # 文件处理器
        logging.StreamHandler()  # 控制台处理器
    ]
)
def computeTlsh(string):
    """
    生成字符串的TLSH哈希值
    
    TLSH(Trend Micro Locality Sensitive Hash)是一种局部敏感哈希算法，
    用于计算字符串相似度。该算法具有以下特点：
    1. 相似的输入会产生相似的哈希值
    2. 对输入的细微改变不敏感
    3. 适合用于代码克隆检测
    
    参数:
        string: 待计算哈希值的字符串
    返回:
        hs: 计算得到的TLSH哈希值
    """
    string = str.encode(string)
    hs = tlsh.forcehash(string)
    return hs

def removeComment(string):
    """
    移除C/C++风格的注释
    
    处理两种类型的注释:
    1. 单行注释 (//)
    2. 多行注释 (/* */)
    
    使用正则表达式进行匹配和替换，保留代码的其他部分不变
    
    参数:
        string: 包含注释的源代码字符串
    返回:
        去除注释后的代码字符串
    """
    # Code for removing C/C++ style comments. (Imported from VUDDY and ReDeBug.)
    # ref: https://github.com/squizz617/vuddy
    c_regex = re.compile(
        r'(?P<comment>//.*?$|[{}]+)|(?P<multilinecomment>/\*.*?\*/)|(?P<noncomment>\'(\\.|[^\\\'])*\'|"(\\.|[^\\"])*"|.[^/\'"]*)',
        re.DOTALL | re.MULTILINE)
    return ''.join([c.group('noncomment') for c in c_regex.finditer(string) if c.group('noncomment')])

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
        string: 待标准化的源代码字符串
    返回:
        标准化后的字符串
    """
    return ''.join(string.replace('\n', '').replace('\r', '').replace('\t', '').replace('{', '').replace('}', '').split(' ')).lower()

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
        
    return file_result, file_count, func_count, line_count

def hashing(repoPath):
    """
    使用多进程对仓库中的C/C++函数进行哈希处理
    """
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

            # 返回检测结果 - 垂直布局格式
            result = f"检测到匹配组件:\n"
            result += f"  输入仓库: {inputRepo}\n"
            result += f"  匹配组件: {repoName}\n"
            result += f"  预测版本: {predictedVer}\n"
            result += f"  使用函数数: {used}\n"
            result += f"  未使用函数数: {unused}\n"
            result += f"  修改函数数: {modified}\n"
            result += f"  结构变化: {'是' if strChange else '否'}\n"
            result += "-" * 40 + "\n"
            return result
                            
    except Exception as e:
        logging.error(f"处理组件 {OSS} 时发生错误: {e}")
        return None

def detector(inputDict, inputRepo):
    """代码克隆检测的主要逻辑实现"""
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
        # 写入表头
        header = f"Re-Centris 代码克隆检测结果\n"
        header += f"检测时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        header += "=" * 50 + "\n\n"
        fres.write(header)

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
    resDict, fileCnt, funcCnt, lineCnt = hashing(inputPath)
    detector(resDict, inputRepo)

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
        inputPath = "/home/rby/project/Re-Centris/test_detector_project/redis"
    else:
        inputPath = sys.argv[1]

    inputRepo = inputPath.split('/')[-1]

    main(inputPath, inputRepo)
