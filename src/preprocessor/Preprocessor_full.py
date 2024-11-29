"""
预处理器。
作者：		Seunghoon Woo (seunghoonwoo@korea.ac.kr)
修改日期： 	2020年12月16日。
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



"""全局变量"""
currentPath		= "/home/rby/Project/project-file/dependency_analysis/centris"
separator 		= "#@#"	
sep_len			= len(separator)					
# 暂时不要更改

theta 			= 0.1										# 默认值 (0.1)
tagDatePath 	= currentPath + "/OSS_Collector/repo_date/" 				# 默认路径
resultPath		= currentPath + "/OSS_Collector/repo_functions/" 		# 默认路径
verIDXpath		= currentPath + "/Preprocessor/verIDX/"					# 默认路径
initialDBPath	= currentPath + "/Preprocessor/initialSigs/"  			# 默认路径
finalDBPath		= currentPath + "/Preprocessor/componentDB/"  			# 最终组件数据库的默认路径
metaPath		= currentPath + "/Preprocessor/metaInfos/"				# 默认路径，用于保存收集的仓库的元信息
weightPath		= metaPath 	  + "/weights/"					# 默认路径，用于版本预测
funcDatePath	= currentPath + "/Preprocessor/funcDate/"				# 默认路径
log_path = currentPath + "/logs/Preprocessor"                           # 创建日志目录
# 生成目录
shouldMake 	= [verIDXpath, initialDBPath, finalDBPath, metaPath, funcDatePath, weightPath, log_path]
for eachRepo in shouldMake:
	if not os.path.isdir(eachRepo):
		os.mkdir(eachRepo)



# 生成日志文件名，包含时间戳
log_file = os.path.join(log_path, f"preprocessor_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 修改日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),  # 文件处理器
        logging.StreamHandler()  # 控制台处理器
    ]
)

funcDateDict	= {}


def extractVerDate(repoName):
    """
    提取版本（标签）日期
    
    参数：
    repoName - 仓库名称
    
    返回：
    verDateDict - 包含版本和对应日期的字典，所有标签都会被保存
2024-09-15 12:40:43 -0400  (tag: swift-DEVELOPMENT-SNAPSHOT-2024-09-16-a, tag: swift-DEVELOPMENT-SNAPSHOT-2024-09-15-a)
提取后形式为：
    verDateDict = {
        "swift-DEVELOPMENT-SNAPSHOT-2024-09-16-a": "2024-09-15",
        "swift-DEVELOPMENT-SNAPSHOT-2024-09-15-a": "2024-09-15"
    }
    """
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
                date = line[0:10]  # 提取日期 YYYY-MM-DD
                
                # 使用正则表达式匹配所有标签
                tags = re.findall(r'tag:\s*([^,)]+)', line)
                
                for tag in tags:
                    version = tag.strip()
                    if version:  # 确保版本号不为空
                        verDateDict[version] = date
                        
    except Exception as e:
        logging.error(f"处理仓库 {repoName} 时发生错误: {e}")
        
    return verDateDict

def process_single_repo(repoName):
    """
    处理单个仓库的函数
    
    参数：
    repoName - 仓库名称
    
    返回：
    repoName - 处理成功时返回仓库名称
    None - 处理失败时返回None
    """
    try:
        logging.info(f"开始处理: {repoName}")
        
        funcDateDict = {}
        tempDateDict = {}
        verDateDict = extractVerDate(repoName)
        
        verTempLst = []
        signature = {}
        verDict = {}
        idx = 0
        
        # 获取所有版本名称
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
            
            with open(os.path.join(resultPath, repoName, ("fuzzy_" + versionName + ".hidx")), 'r', encoding="UTF-8") as fp:
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
        
        # 存储函数出生日期，存储的是每个hashval最早的出生日期
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
    """
    使用ProcessPoolExecutor进行并行处理的冗余消除
    """
    repo_list = os.listdir(resultPath)
    
    # 设置进程数为CPU核心数
    num_processes = multiprocessing.cpu_count()
    logging.info(f"使用 {num_processes} 个进程进行冗余消除")
    
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        # 提交所有任务
        future_to_repo = {executor.submit(process_single_repo, repo): repo for repo in repo_list}
        
        # 等待所有任务完成并处理结果
        for future in concurrent.futures.as_completed(future_to_repo):
            repo = future_to_repo[future]
            try:
                result = future.result()
                if result:
                    logging.info(f"成功处理仓库: {result}")
            except Exception as e:
                logging.error(f"处理仓库 {repo} 时发生错误: {e}")

def process_single_meta(OSS):
    """
    处理单个仓库的元信息
    """
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
        # 处理仓库的每个函数
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

        # 写入权重文件
        with open(weightPath + "/" + repoName + "_weights", 'w') as fwei:
            fwei.write(json.dumps(weightJson))
            
        return result
        
    except Exception as e:
        logging.error(f"处理仓库元信息 {OSS} 时发生错误: {e}")
        return None

def saveMetaInfos():
    """
    使用ProcessPoolExecutor并行保存元信息
    """
    aveFuncJson = {}
    allFuncJson = {}
    unique = {}
    
    OSS_list = os.listdir(initialDBPath)
    num_processes = multiprocessing.cpu_count()
    logging.info(f"使用 {num_processes} 个进程处理元信息")
    
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        # 提交所有任务
        future_to_oss = {executor.submit(process_single_meta, oss): oss for oss in OSS_list}
        
        # 收集结果
        for future in concurrent.futures.as_completed(future_to_oss):
            try:
                result = future.result()
                if result:
                    repoName = result['repoName']
                    aveFuncJson[repoName] = result['aveFuncs']
                    allFuncJson[repoName] = result['allFuncs']
                    unique.update(result['unique'])
            except Exception as e:
                logging.error(f"处理元信息时发生错误: {e}")
    
    # 写入最终结果
    with open(metaPath + "aveFuncs", 'w') as fave:
        fave.write(json.dumps(aveFuncJson))
    
    with open(metaPath + "allFuncs", 'w') as fall:
        fall.write(json.dumps(allFuncJson))
    
    # 生成并写入唯一函数信息
    uniqueJson = []
    for hashval in unique:
        temp = {"hash": hashval, "OSS": [unique[hashval]]}
        uniqueJson.append(temp)
    
    with open(metaPath + "uniqueFuncs", 'w') as funi:
        funi.write(json.dumps(uniqueJson))

def readVerDate(verDateDict, repoName):
    """
    读取版本日期
    
    参数：
    verDateDict - 存储版本日期的字典
    repoName - 仓库名称
    
    返回：
    更新后的verDateDict
    """
    verDateDict[repoName] = {}

    if os.path.isfile(funcDatePath + repoName + "_funcdate"):
        with open(funcDatePath + repoName + "_funcdate", 'r', encoding="UTF-8") as fp:
            for eachLine in fp:
                eachLine = eachLine.strip()
                if eachLine:  # 确保行不为空
                    hashval, date = eachLine.split('\t')
                    verDateDict[repoName][hashval] = date
    return verDateDict

def getAveFuncs():
    """
    获取平均函数数
    
    返回：
    aveFuncs - 包含每个仓库平均函数数的字典
    """
    with open(metaPath + "aveFuncs", 'r', encoding = "UTF-8") as fp:
        return json.load(fp)

def process_single_segmentation(S_sig, aveFuncs, uniqueFuncs):
    """
    处理单个仓库的代码分割
    """
    try:
        S = S_sig.replace("_sig", "")
        possibleMembers = {}
        candiX = {}
        removedFuncs = []
        verDateDict = {}
        
        # 读取当前仓库的版本日期
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

            # 确定可能的成员
            for X in candiX:
                if aveFuncs[X] == 0 or len(verDateDict[X]) == 0:
                    continue
                elif (float(candiX[X])/float(aveFuncs[X])) >= theta:
                    if S not in possibleMembers:
                        possibleMembers[S] = []
                    possibleMembers[S].append(X)
                    removedFuncs.extend(temp[X])

            # 生成最终签名文件
            if S not in possibleMembers:
                shutil.copy(os.path.join(initialDBPath, S)+"_sig", os.path.join(finalDBPath, S)+"_sig")
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
    """
    使用ProcessPoolExecutor并行进行代码分割
    """
    aveFuncs = getAveFuncs()
    
    # 读取唯一函数信息
    uniqueFuncs = {}
    with open(metaPath + "uniqueFuncs", 'r', encoding="UTF-8") as fp:
        jsonStr = json.load(fp)
        for eachVal in jsonStr:
            hashval = eachVal['hash']
            uniqueFuncs[hashval] = eachVal['OSS']
    
    OSS_list = os.listdir(initialDBPath)
    tot = len(OSS_list)
    logging.info(f'[+] 读取OSS签名.. 总数: {tot}')
    
    num_processes = multiprocessing.cpu_count()
    logging.info(f"使用 {num_processes} 个进程进行代码分割")
    
    completed = 0
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        # 提交所有任务
        future_to_oss = {
            executor.submit(
                process_single_segmentation, 
                oss, 
                aveFuncs, 
                uniqueFuncs
            ): oss for oss in OSS_list
        }
        
        # 处理结果
        for future in concurrent.futures.as_completed(future_to_oss):
            try:
                result = future.result()
                completed += 1
                if result:
                    logging.info(f'进度: {completed}/{tot} - 完成: {result}')
            except Exception as e:
                logging.error(f"代码分割时发生错误: {e}")

def main():
    """
    主函数
    
    按顺序执行冗余消除、保存元信息和代码分割
    """
    redundancyElimination()
    saveMetaInfos()
    codeSegmentation()

""" 执行 """
if __name__ == "__main__":
	main()
