import os
import subprocess
import re
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import logging
from typing import List, Tuple, Optional

# 配置日志
def setup_logging(log_file: str = 'clone.log', level: str = 'INFO'):
    """设置日志配置"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

logger = logging.getLogger(__name__)

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

def clone_single_repo(repo_info: Tuple[str, str, str], clone_path: str, timeout: int = 300) -> Tuple[bool, str]:
    """
    克隆单个仓库

    Args:
        repo_info: 包含作者名,仓库名,URL的元组
        clone_path: 克隆目标路径
        timeout: 超时时间(秒)

    Returns:
        Tuple[bool, str]: (克隆是否成功, 错误信息或成功信息)
    """
    author, repo_name, repo_url = repo_info
    folder_name = f"{author}%{repo_name}"
    target_path = os.path.join(clone_path, folder_name)

    if os.path.exists(target_path):
        message = f"仓库 {folder_name} 已存在，跳过克隆"
        logger.info(message)
        return True, message

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

        start_time = time.time()
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout
        )

        elapsed_time = time.time() - start_time
        message = f"成功克隆仓库 {folder_name} (耗时: {elapsed_time:.1f}s)"
        logger.info(message)
        return True, message

    except subprocess.TimeoutExpired:
        message = f"克隆超时 {folder_name}: 超过 {timeout} 秒"
        logger.error(message)
        # 清理可能的部分克隆目录
        if os.path.exists(target_path):
            try:
                import shutil
                shutil.rmtree(target_path)
            except:
                pass
        return False, message

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        message = f"克隆仓库 {folder_name} 失败: {error_msg}"
        logger.error(message)
        return False, message

    except Exception as e:
        message = f"处理仓库 {folder_name} 时发生错误: {str(e)}"
        logger.error(message)
        return False, message

def read_repo_list(repo_list_file: str) -> List[str]:
    """
    从文件读取仓库URL列表

    Args:
        repo_list_file: 包含GitHub仓库URL的文件路径

    Returns:
        List[str]: 仓库URL列表
    """
    repos = []
    try:
        with open(repo_list_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):  # 跳过空行和注释
                    repos.append(line)
        logger.info(f"从 {repo_list_file} 读取到 {len(repos)} 个仓库")
        return repos
    except FileNotFoundError:
        logger.error(f"文件不存在: {repo_list_file}")
        return []
    except Exception as e:
        logger.error(f"读取文件失败 {repo_list_file}: {str(e)}")
        return []

def clone_repositories(repo_urls: List[str], clone_path: str, max_workers: int = 5, timeout: int = 300):
    """
    并行克隆多个GitHub仓库

    Args:
        repo_urls: GitHub仓库URL列表
        clone_path: 克隆仓库的目标路径
        max_workers: 最大并行工作线程数
        timeout: 单个仓库克隆超时时间(秒)
    """
    # 确保目标目录存在
    os.makedirs(clone_path, exist_ok=True)

    if not repo_urls:
        logger.warning("仓库列表为空")
        return

    # 解析所有仓库URL
    repo_infos = []
    for url in repo_urls:
        try:
            repo_infos.append(parse_repo_url(url))
        except ValueError as e:
            logger.error(str(e))
            continue

    if not repo_infos:
        logger.error("没有有效的仓库URL")
        return

    logger.info(f"开始克隆 {len(repo_infos)} 个仓库，使用 {max_workers} 个并行线程")

    # 统计信息
    success_count = 0
    failed_count = 0
    skipped_count = 0

    # 使用线程池并行克隆
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有克隆任务
        future_to_repo = {
            executor.submit(clone_single_repo, repo_info, clone_path, timeout): repo_info
            for repo_info in repo_infos
        }

        # 使用tqdm显示进度
        with tqdm(total=len(repo_infos), desc="克隆进度", unit="repo") as pbar:
            for future in as_completed(future_to_repo):
                repo_info = future_to_repo[future]
                try:
                    success, message = future.result()
                    if success:
                        if "已存在" in message:
                            skipped_count += 1
                            pbar.set_description(f"跳过 {repo_info[1]}")
                        else:
                            success_count += 1
                            pbar.set_description(f"完成 {repo_info[1]}")
                    else:
                        failed_count += 1
                        pbar.set_description(f"失败 {repo_info[1]}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"处理仓库 {repo_info[1]} 时发生错误: {str(e)}")
                finally:
                    pbar.update(1)
                    # 更新进度条后缀信息
                    pbar.set_postfix({
                        '成功': success_count,
                        '跳过': skipped_count,
                        '失败': failed_count
                    })

    # 输出最终统计
    total = len(repo_infos)
    logger.info(f"克隆完成! 总计: {total}, 成功: {success_count}, 跳过: {skipped_count}, 失败: {failed_count}")

def main():
    """主函数，处理命令行参数"""
    parser = argparse.ArgumentParser(
        description='GitHub仓库批量克隆工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python Clone_Repo.py -f repo_list.txt -o ./repos
  python Clone_Repo.py -f repo_list.txt -o ./repos -w 10 --timeout 600
  python Clone_Repo.py -f repo_list.txt -o ./repos --log-level DEBUG
        """
    )

    parser.add_argument('-f', '--file', required=True,
                        help='包含GitHub仓库URL的文件路径')
    parser.add_argument('-o', '--output', default='./repos',
                        help='克隆仓库的目标目录 (默认: ./repos)')
    parser.add_argument('-w', '--workers', type=int, default=5,
                        help='并行线程数 (默认: 5)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='单个仓库克隆超时时间(秒) (默认: 300)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default='INFO', help='日志级别 (默认: INFO)')
    parser.add_argument('--log-file', default='clone.log',
                        help='日志文件路径 (默认: clone.log)')

    args = parser.parse_args()

    # 设置日志
    setup_logging(args.log_file, args.log_level)

    # 读取仓库列表
    repo_urls = read_repo_list(args.file)
    if not repo_urls:
        logger.error("没有找到有效的仓库URL")
        return 1

    # 开始克隆
    try:
        clone_repositories(repo_urls, args.output, args.workers, args.timeout)
        return 0
    except KeyboardInterrupt:
        logger.info("用户中断操作")
        return 1
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}")
        return 1

if __name__ == "__main__":
    exit(main())
