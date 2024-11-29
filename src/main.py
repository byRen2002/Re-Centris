import os
import subprocess
import re
def clone_repositories(repo_list_file, clone_path):
    """
    克隆GitHub仓库，包括所有标签，并将文件夹命名为'作者%仓库'的形式
    
    :param repo_list_file: 包含GitHub仓库URL的文件路径
    :param clone_path: 克隆仓库的目标路径
    """
    with open(repo_list_file, 'r') as f:
        repo_urls = f.read().splitlines()

    for repo_url in repo_urls:
        # 从URL中提取作者和仓库名
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            print(f"无法解析仓库URL: {repo_url}")
            continue

        author, repo_name = match.groups()
        repo_name = repo_name[:-4]
        
        # 创建目标文件夹名称
        folder_name = f"{author}%{repo_name}"
        target_path = os.path.join(clone_path, folder_name)
        # 如果目标文件夹已存在，跳过克隆
        if os.path.exists(target_path):
            print(f"仓库 {folder_name} 已存在，跳过克隆")
            continue

        try:
            # 克隆仓库，包括所有标签
            print(f"正在克隆 {repo_url} 到 {target_path}")
            repo_url = repo_url + ' ' + target_path
            subprocess.check_output(repo_url, stderr = subprocess.STDOUT, shell = True).decode()
            # 切换到仓库目录
            os.chdir(target_path)

            # 获取所有远程分支和标签
            # subprocess.run(['git', 'fetch', '--all'], check=True)

            print(f"成功克隆仓库 {folder_name}")

        except subprocess.CalledProcessError as e:
            print(f"克隆仓库 {repo_url} 时出错: {e}")
        except Exception as e:
            print(f"处理仓库 {repo_url} 时发生错误: {e}")

    # print("所有仓库克隆完成")
clone_repositories('/home/rby/Project/project-file/dependency_analysis/sample', '/home/rby/Project/project-file/dependency_analysis/repo_src')
