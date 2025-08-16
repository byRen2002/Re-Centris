"""Re-Centris 检测器包 - 基于TLSH的代码克隆和依赖关系检测工具。

主要功能:
1. 代码克隆检测 - 使用TLSH算法检测代码克隆
2. 依赖关系分析 - 分析组件间的依赖关系
3. 版本预测 - 预测使用的组件版本

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

from .run_detector import Detector

__all__ = ['Detector'] 