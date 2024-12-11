import os
import subprocess
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import logging
from typing import List, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clone.log'),
        logging.StreamHandler()
    ]
)

def parse_repo_url(repo_url: str) -> Tuple[str, str, str]:
    """
    解析GitHub仓库URL,返回作者和仓库名
    
    Args:
        repo_url: GitHub仓库URL
        
    Returns:
        Tuple[str, str, str]: 作者名,仓库名,目标路径
    """
    match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
    if not match:
        raise ValueError(f"无法解析仓库URL: {repo_url}")
    
    author, repo_name = match.groups()
    repo_name = repo_name[:-4] if repo_name.endswith('.git') else repo_name
    
    return author, repo_name, repo_url

def clone_single_repo(repo_info: Tuple[str, str, str], clone_path: str) -> bool:
    """
    克隆单个仓库
    
    Args:
        repo_info: 包含作者名,仓库名,URL的元组
        clone_path: 克隆目标路径
        
    Returns:
        bool: 克隆是否成功
    """
    author, repo_name, repo_url = repo_info
    folder_name = f"{author}%{repo_name}"
    target_path = os.path.join(clone_path, folder_name)

    if os.path.exists(target_path):
        logging.info(f"仓库 {folder_name} 已存在,跳过克隆")
        return True

    try:
        # 优化的git clone命令
        cmd = [
            'git', 'clone',
            '--depth', '1',  # 只克隆最新版本
            '--single-branch',  # 只克隆默认分支
            '--no-tags',  # 不克隆标签
            repo_url,
            target_path
        ]
        
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        logging.info(f"成功克隆仓库 {folder_name}")
        return True

    except subprocess.CalledProcessError as e:
        logging.error(f"克隆仓库 {repo_url} 失败: {e.stderr.decode()}")
        return False
    except Exception as e:
        logging.error(f"处理仓库 {repo_url} 时发生错误: {str(e)}")
        return False

def clone_repositories(repo_list_file: str, clone_path: str, max_workers: int = 5):
    """
    并行克隆多个GitHub仓库
    
    Args:
        repo_list_file: 包含GitHub仓库URL的文件路径
        clone_path: 克隆仓库的目标路径
        max_workers: 最大并行工作线程数
    """
    # 确保目标目录存在
    os.makedirs(clone_path, exist_ok=True)
    
    # 读取仓库URL列表
    try:
        with open(repo_list_file, 'r', buffering=8192) as f:
            repo_urls = [url.strip() for url in f if url.strip()]
    except Exception as e:
        logging.error(f"读取仓库列表文件失败: {str(e)}")
        return

    if not repo_urls:
        logging.warning("仓库列表为空")
        return

    # 解析所有仓库URL
    repo_infos = []
    for url in repo_urls:
        try:
            repo_infos.append(parse_repo_url(url))
        except ValueError as e:
            logging.error(str(e))
            continue

    # 使用线程池并行克隆
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有克隆任务
        future_to_repo = {
            executor.submit(clone_single_repo, repo_info, clone_path): repo_info 
            for repo_info in repo_infos
        }
        
        # 使用tqdm显示进度
        with tqdm(total=len(repo_infos), desc="克隆进度") as pbar:
            for future in as_completed(future_to_repo):
                repo_info = future_to_repo[future]
                try:
                    success = future.result()
                    if success:
                        pbar.set_description(f"成功克隆 {repo_info[1]}")
                    else:
                        pbar.set_description(f"克隆失败 {repo_info[1]}")
                except Exception as e:
                    logging.error(f"处理仓库 {repo_info[1]} 时发生错误: {str(e)}")
                finally:
                    pbar.update(1)

    logging.info("所有仓库克隆完成")

if __name__ == "__main__":
    clone_repositories(
        '/home/rby/Project/project-file/dependency_analysis/sample',
        '/home/rby/Project/project-file/dependency_analysis/repo_src'
    )
