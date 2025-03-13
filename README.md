# Re-Centris

Re-Centris是一个高性能的代码相似度分析工具，基于TLSH(Trend Micro Locality Sensitive Hash)算法实现。它专注于代码克隆检测、开源组件识别和依赖关系分析，支持多种编程语言。

## 主要特性

- **高精度代码相似度分析**
  - 基于TLSH算法的模糊哈希匹配
  - 支持检测代码重构和变体
  - 函数级别的细粒度分析

- **多语言支持**
  - Python版本支持：C/C++、Java、Python
  - Go版本当前支持：C/C++（其他语言支持持续添加中）

- **高性能设计**
  - 多进程/协程并行处理
  - 内存映射技术
  - 智能缓存机制
  - 资源使用优化

- **丰富的分析功能**
  - 开源组件识别
  - 代码克隆检测
  - 依赖关系分析
  - 版本信息提取

## 版本选择指南

### Python版本
- 适用场景：
  - 需要分析多种编程语言
  - 需要更灵活的扩展性
  - 对易用性要求较高

### Go版本
- 适用场景：
  - 大规模代码库分析
  - 对性能要求极高
  - 主要分析C/C++代码

## 快速开始

### Python版本安装

```bash
# 1. 克隆仓库
git clone https://github.com/xxx/xxx.git
cd re-centris

# 2. 创建并激活虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. 安装依赖
pip install -r requirements.txt
```

### Go版本安装

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/re-centris-go.git
cd re-centris-go

# 2. 构建项目
go build -o re-centris ./cmd/re-centris

# 3. (可选)系统级安装
go install ./cmd/re-centris
```

## 使用示例

### Python版本

```bash
# 1. 收集开源代码信息
python -m osscollector.collector -c config.yaml

# 2. 预处理代码
python -m preprocessor.preprocessor -c config.yaml

# 3. 执行相似度检测
python -m detector.detector -c config.yaml -i path/to/input/code
```

### Go版本

```bash
# 1. 克隆并收集代码
re-centris clone repo-list.txt -o ./repos

# 2. 分析代码
re-centris analyze ./source-code -o ./analysis

# 3. 执行相似度检测
re-centris detect target-file.cpp -k ./known-files -o results.json
```

## 配置说明

配置文件使用YAML格式，支持以下主要配置项：

```yaml
paths:
  repo_path: "./repos"
  tag_date_path: "./data/repo_date"
  result_path: "./data/repo_functions"

performance:
  max_workers: 0  # 自动使用可用CPU核心数
  cache_size: 1000
  memory_limit: 0.8  # 最大内存使用率

languages:
  cpp:
    enabled: true
    extensions: [".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"]
  java:
    enabled: false
    extensions: [".java"]
  python:
    enabled: false
    extensions: [".py"]
```

## 项目结构

### Python版本
```
re-centris/
├── core/                  # 核心功能模块
├── osscollector/         # 开源代码收集
├── preprocessor/         # 代码预处理
├── detector/             # 相似度检测
├── config.yaml          
└── requirements.txt      
```

### Go版本
```
re-centris-go/
├── cmd/                  # CLI入口
├── internal/            # 核心实现
│   ├── analyzer/       # 代码分析
│   ├── collector/      # 代码收集
│   ├── detector/      # 相似度检测
│   └── preprocessor/  # 预处理
└── config.yaml
```

## 输出结果

分析结果以JSON格式输出，包含：
- 相似度评分
- 函数级别匹配信息
- 依赖关系图谱
- 版本信息追踪

## 贡献指南

欢迎提交Pull Request！请确保：

1. 代码通过所有测试
2. 添加必要的测试用例
3. 更新相关文档
4. 遵循项目代码规范

## 许可证

MIT License - 详见LICENSE文件

## 关于

由byRen2002开发维护。问题反馈请提交GitHub Issue。 