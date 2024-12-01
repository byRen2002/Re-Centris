# Centris代码克隆与依赖分析工具
Centris 是一种用于识别开源组件的工具。具体来说，Centris 可以精确、可扩展地识别组件，即使它们通过代码 / 结构修改而被重用。。本工具通过四个主要步骤完成代码克隆检测:克隆远程仓库、收集库信息、提取代码签名、执行相似度检测。

## 功能特点

- **远程仓库克隆**: 支持批量克隆GitHub仓库
- **代码信息收集**: 自动提取和管理代码库元数据
- **签名生成**: 使用Universal-Ctags提取函数级别特征
- **克隆检测**: 基于TLSH算法的代码相似度分析
- **高性能处理**: 多进程并行处理
- **内存优化**: 支持大规模代码分析
- **详细日志**: 完整的执行记录

## 系统要求

- Linux操作系统
- Python 3.7+
- Git
- Universal-Ctags 5.9.0+：用于函数解析
- Python3-tlsh：用于函数哈希
- 足够的磁盘空间用于克隆代码库

## 安装

1. 安装Python依赖:
  ``` bash
  pip install -r requirements.txt
  ```

2. 安装Universal-Ctags:
``` bash
    $ git clone https://github.com/universal-ctags/ctags.git
    $ cd ctags
    $ ./autogen.sh
    $ ./configure  # use --prefix=/where/you/want to override installation directory, defaults to /usr/local
    $ make
    $ make install # may require extra privileges depending on where to install
```
## 使用流程

### 1. 克隆远程仓库

使用Clone_Repo模块克隆GitHub仓库，用以构建组件数据库

```bash
python Clone_Repo.py 
```

### 2. 收集库信息

使用OSS_Collector收集已克隆仓库的信息:

```bash
python OSS_Collector.py
```


### 3. 提取代码签名

通过两种方式通过预处理创建组件 DB：使用完整的预处理器（Preprocessor_full.py，在本文中使用）或精简版本的预处理器（Preprocessor_lite.py）。唯一的区别是是否包括两个软件的共同功能甚至相似的功能（对于完整），还是只考虑完全相同的功能（对于精简版）。如果使用 lite 预处理器创建组件 DB，则运行时间比完整预处理器短得多，但组件识别准确性会略有降低

```bash
python Preprocessor_full.py
```
或
```bash
python Preprocessor_lite.py
```


### 4. 执行克隆检测

使用Detector模块进行相似度检测:

```bash
python Detector.py  --target /path/to/target
```
参数说明:
- `--target`: 目标代码目录



## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件
