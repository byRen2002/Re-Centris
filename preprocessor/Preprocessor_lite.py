"""预处理器模块 - 用于预处理开源代码库。主要功能:1.冗余消除-移除重复函数签名 2.元信息保存-保存版本、函数数量等元数据 3.代码分割-基于相似度的代码分割。主要类和函数:PreprocessorConfig(配置管理),SignatureProcessor(签名处理),MetaInfoManager(元信息管理),CodeSegmenter(代码分割)。作者:Seunghoon Woo,修改:byRen2002,许可证:MIT"""

import os
import sys
import re
import shutil
import json
import math
import logging
import datetime
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

# 复用Detector中的工具类
from detector.Detector import (
    Cache, 
    ResourceManager,
    MemoryOptimizer,
    PerformanceMonitor
)

class PreprocessorConfig:
    """配置管理类"""
    
    def __init__(self):
        """初始化配置"""
        self.current_path = os.getcwd()
        self.separator = "#@#"
        self.sep_len = len(self.separator)
        self.theta = 0.1  # 相似度阈值
        
        # 路径配置
        self.tag_date_path = "../osscollector/repo_date/"
        self.result_path = "../osscollector/repo_functions/"
        self.ver_idx_path = f"{self.current_path}/verIDX/"
        self.initial_db_path = f"{self.current_path}/initialSigs/"
        self.final_db_path = f"{self.current_path}/componentDB/"
        self.meta_path = f"{self.current_path}/metaInfos/"
        self.weight_path = f"{self.meta_path}/weights/"
        self.func_date_path = f"{self.current_path}/funcDate/"
        
        # 创建必要目录
        self._create_directories()
        
        # 日志配置
        self._setup_logging()
        
    def _create_directories(self):
        """创建必要的目录"""
        dirs = [
            self.ver_idx_path,
            self.initial_db_path, 
            self.final_db_path,
            self.meta_path,
            self.func_date_path,
            self.weight_path
        ]
        
        for directory in dirs:
            if not os.path.isdir(directory):
                os.makedirs(directory)
                logging.info(f"创建目录: {directory}")
                
    def _setup_logging(self):
        """配置日志"""
        log_path = f"{self.current_path}/logs/preprocessor"
        if not os.path.exists(log_path):
            os.makedirs(log_path)
            
        log_file = os.path.join(
            log_path,
            f"preprocessor_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

class SignatureProcessor:
    """签名处理类"""
    
    def __init__(self, config):
        """初始化签名处理器,参数:config:PreprocessorConfig实例"""
        self.config = config
        self.resource_manager = ResourceManager()
        self.cache = Cache()
        self.perf_monitor = PerformanceMonitor()
        
    def extract_ver_date(self, repo_name):
        """提取版本日期信息"""
        ver_date_dict = {}
        
        try:
            tag_file = os.path.join(self.config.tag_date_path, repo_name)
            if not os.path.isfile(tag_file):
                return ver_date_dict
                
            with self.resource_manager.get_file_handle(tag_file, 'r') as fp:
                lines = [l.strip('\n\r') for l in fp.readlines()]
                
                for line in lines:
                    if "tag:" not in line:
                        continue
                        
                    date = line[0:10]
                    version_list = []
                    
                    if "," in line:
                        ver_list = [x for x in line.split("tag: ")]
                        for val in ver_list[1:]:
                            if ',' in val:
                                version_list.append(val.split(',')[0])
                            elif ')' in val:
                                version_list.append(val.split(')')[0])
                    else:
                        version_list = [(line.split('tag: ')[1][:-1])]
                        
                    for version in version_list:
                        ver_date_dict[version] = date
                        
        except Exception as e:
            logging.error(f"提取版本日期时出错: {e}")
            
        return ver_date_dict
        
    def process_single_repo(self, repo_name):
        """处理单个仓库的签名"""
        logging.info(f"开始处理仓库: {repo_name}")
        
        try:
            func_date_dict = {}
            temp_date_dict = {}
            ver_date_dict = self.extract_ver_date(repo_name)
            
            # 处理版本信息
            ver_temp_lst = []
            signature = {}
            ver_dict = {}
            idx = 0
            
            # 获取所有版本
            for version in os.listdir(os.path.join(self.config.result_path, repo_name)):
                version_name = version.split("fuzzy_")[1].replace(".hidx", "")
                if version_name and version_name != " ":
                    ver_temp_lst.append(version_name)
            ver_temp_lst.sort()
            
            # 处理每个版本
            for version_name in ver_temp_lst:
                version_file = os.path.join(
                    self.config.result_path,
                    repo_name,
                    f"fuzzy_{version_name}.hidx"
                )
                
                with self.resource_manager.get_file_handle(version_file, 'r') as fp:
                    ver_dict[version_name] = idx
                    idx += 1
                    
                    body = ''.join(fp.readlines()).strip()
                    for line in body.split('\n')[1:-1]:
                        if not line or line == ' ':
                            continue
                            
                        hashval = line.split('\t')[0]
                        if hashval not in signature:
                            signature[hashval] = []
                            temp_date_dict[hashval] = []
                            
                        signature[hashval].append(str(idx-1))
                        
                        if version_name in ver_date_dict:
                            temp_date_dict[hashval].append(ver_date_dict[version_name])
                        else:
                            temp_date_dict[hashval].append("NODATE")
                            
            # 保存函数出生日期
            for hashval in temp_date_dict:
                temp_date_dict[hashval].sort()
                func_date_dict[hashval] = temp_date_dict[hashval][0]
                
            self._save_func_dates(repo_name, func_date_dict)
            self._save_version_indexes(repo_name, ver_temp_lst, ver_dict)
            self._save_signatures(repo_name, signature)
            
            logging.info(f"仓库 {repo_name} 处理完成")
            
        except Exception as e:
            logging.error(f"处理仓库 {repo_name} 时出错: {e}")
            
    def _save_func_dates(self, repo_name, func_date_dict):
        """保存函数日期信息"""
        try:
            with open(f"{self.config.func_date_path}{repo_name}_funcdate", 'w') as f:
                for hashval, date in func_date_dict.items():
                    f.write(f"{hashval}\t{date}\n")
        except Exception as e:
            logging.error(f"保存函数日期时出错: {e}")
            
    def _save_version_indexes(self, repo_name, ver_list, ver_dict):
        """保存版本索引"""
        try:
            save_json = []
            for ver_name in ver_list:
                save_json.append({
                    "ver": ver_name,
                    "idx": str(ver_dict[ver_name])
                })
                
            with open(f"{self.config.ver_idx_path}{repo_name}_idx", 'w') as f:
                json.dump(save_json, f)
        except Exception as e:
            logging.error(f"保存版本索引时出错: {e}")
            
    def _save_signatures(self, repo_name, signature):
        """保存签名信息"""
        try:
            save_json = []
            for hashval, vers in signature.items():
                save_json.append({
                    "hash": hashval,
                    "vers": vers
                })
                
            with open(f"{self.config.initial_db_path}{repo_name}_sig", 'w') as f:
                json.dump(save_json, f)
        except Exception as e:
            logging.error(f"保存签名时出错: {e}")

class MetaInfoManager:
    """元信息管理类"""
    
    def __init__(self, config):
        self.config = config
        self.resource_manager = ResourceManager()
        
    def save_meta_infos(self):
        """保存元信息"""
        ave_func_json = {}
        all_func_json = {}
        unique_json = []
        unique = {}
        
        try:
            # 处理每个仓库的签名
            for oss in os.listdir(self.config.initial_db_path):
                weight_json = {}
                repo_name = oss.replace("_sig", "")
                tot_funcs = 0
                tot_vers = len(os.listdir(
                    os.path.join(self.config.result_path, repo_name)
                ))
                
                if tot_vers == 0:
                    continue
                    
                # 读取签名文件
                with self.resource_manager.get_file_handle(
                    os.path.join(self.config.initial_db_path, oss), 'r'
                ) as fs:
                    json_str = json.load(fs)
                    tot_funcs = len(json_str)
                    
                    for each_json in json_str:
                        hashval = each_json['hash']
                        ver_lst = each_json['vers']
                        
                        if hashval not in unique:
                            unique[hashval] = []
                            
                        unique[hashval].append(repo_name)
                        weight_json[hashval] = math.log(
                            float(tot_vers)/float(len(ver_lst))
                        )
                        
                ave_func_json[repo_name] = int(tot_funcs/tot_vers)
                all_func_json[repo_name] = int(tot_funcs)
                
                # 保存权重信息
                with open(f"{self.config.weight_path}{repo_name}_weights", 'w') as f:
                    json.dump(weight_json, f)
                    
            # 保存唯一函数信息
            for func_hash in unique:
                unique_json.append({
                    "hash": func_hash,
                    "OSS": unique[func_hash]
                })
                
            # 保存各类元信息
            with open(f"{self.config.meta_path}aveFuncs", 'w') as f:
                json.dump(ave_func_json, f)
            with open(f"{self.config.meta_path}allFuncs", 'w') as f:
                json.dump(all_func_json, f)
            with open(f"{self.config.meta_path}uniqueFuncs", 'w') as f:
                json.dump(unique_json, f)
                
        except Exception as e:
            logging.error(f"保存元信息时出错: {e}")

class CodeSegmenter:
    """代码分割类"""
    
    def __init__(self, config):
        self.config = config
        self.resource_manager = ResourceManager()
        self.memory_optimizer = MemoryOptimizer()
        
    def segment_code(self):
        """执行代码分割"""
        try:
            # 获取平均函数数
            ave_funcs = self._get_ave_funcs()
            
            # 读取唯一函数信息
            unique_funcs = {}
            with self.resource_manager.get_file_handle(
                f"{self.config.meta_path}uniqueFuncs", 'r'
            ) as fp:
                json_str = json.load(fp)
                for val in json_str:
                    unique_funcs[val['hash']] = val['OSS']
                    
            # 处理每个签名文件
            ver_date_dict = {}
            for s_sig in os.listdir(self.config.initial_db_path):
                s = s_sig.replace("_sig", "")
                
                possible_members = {}
                candi_x = {}
                removed_funcs = []
                
                if s not in ver_date_dict:
                    ver_date_dict = self._read_ver_date(ver_date_dict, s)
                    
                # 处理签名文件
                with self.resource_manager.get_file_handle(
                    os.path.join(self.config.initial_db_path, s_sig), 'r'
                ) as fs:
                    json_str = json.load(fs)
                    if not json_str:
                        continue
                        
                    temp = {}
                    for val in json_str:
                        hashval = val['hash']
                        
                        for oss in unique_funcs[hashval]:
                            if oss == s:
                                continue
                                
                            if oss not in candi_x:
                                temp[oss] = []
                                candi_x[oss] = 0
                                
                            if oss not in ver_date_dict:
                                ver_date_dict = self._read_ver_date(ver_date_dict, oss)
                                
                            try:
                                if hashval not in ver_date_dict[s]:
                                    continue
                                    
                                if (ver_date_dict[s][hashval] == "NODATE" or
                                    ver_date_dict[oss][hashval] == "NODATE"):
                                    candi_x[oss] += 1
                                    temp[oss].append(hashval)
                                elif ver_date_dict[oss][hashval] <= ver_date_dict[s][hashval]:
                                    candi_x[oss] += 1
                                    temp[oss].append(hashval)
                            except:
                                pass
                                
                    # 处理候选组件
                    for x in candi_x:
                        if (ave_funcs[x] == 0 or
                            len(ver_date_dict[x]) == 0):
                            continue
                            
                        if (float(candi_x[x])/float(ave_funcs[x])) >= self.config.theta:
                            if s not in possible_members:
                                possible_members[s] = []
                                
                            possible_members[s].append(x)
                            removed_funcs.extend(temp[x])
                            
                    # 保存处理结果
                    if s not in possible_members:
                        shutil.copy(
                            os.path.join(self.config.initial_db_path, s_sig),
                            os.path.join(self.config.final_db_path, s_sig)
                        )
                    else:
                        removed_funcs = set(removed_funcs)
                        save_json = []
                        
                        for val in json_str:
                            hashval = val['hash']
                            if hashval not in removed_funcs:
                                save_json.append({
                                    "hash": hashval,
                                    "vers": val['vers']
                                })
                                
                        with open(os.path.join(self.config.final_db_path, s_sig), 'w') as f:
                            json.dump(save_json, f)
                            
        except Exception as e:
            logging.error(f"代码分割时出错: {e}")
            
    def _get_ave_funcs(self):
        """获取平均函数数"""
        ave_funcs = {}
        try:
            with self.resource_manager.get_file_handle(
                f"{self.config.meta_path}aveFuncs", 'r'
            ) as fp:
                ave_funcs = json.load(fp)
        except Exception as e:
            logging.error(f"读取平均函数数时出错: {e}")
        return ave_funcs
        
    def _read_ver_date(self, ver_date_dict, repo_name):
        """读取版本日期信息"""
        ver_date_dict[repo_name] = {}
        
        try:
            func_date_file = f"{self.config.func_date_path}{repo_name}_funcdate"
            if os.path.isfile(func_date_file):
                with self.resource_manager.get_file_handle(func_date_file, 'r') as fp:
                    body = ''.join(fp.readlines()).strip()
                    for line in body.split('\n'):
                        hashval, date = line.split('\t')
                        ver_date_dict[repo_name][hashval] = date
        except Exception as e:
            logging.error(f"读取版本日期时出错: {e}")
            
        return ver_date_dict

def main():
    """主函数"""
    try:
        # 初始化配置
        config = PreprocessorConfig()
        
        # 创建处理器实例
        sig_processor = SignatureProcessor(config)
        meta_manager = MetaInfoManager(config)
        code_segmenter = CodeSegmenter(config)
        
        # 多进程处理仓库
        with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
            repos = os.listdir(config.result_path)
            futures = [
                executor.submit(sig_processor.process_single_repo, repo)
                for repo in repos
            ]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"处理仓库时出错: {e}")
                    
        # 保存元信息
        meta_manager.save_meta_infos()
        
        # 执行代码分割
        code_segmenter.segment_code()
        
    except Exception as e:
        logging.error(f"程序执行出错: {e}")
    finally:
        # 清理资源
        ResourceManager().close_all()

if __name__ == "__main__":
    main()