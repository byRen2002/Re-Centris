"""版本预测器

该模块实现了改进的版本预测功能。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_squared_error, r2_score
import pandas as pd
from datetime import datetime
from .semantic_analyzer import SemanticAnalyzer

class VersionPredictor:
    """版本预测器类"""
    
    def __init__(self, config: Dict = None):
        """初始化版本预测器
        
        参数:
            config: 配置参数字典
        """
        self.config = config or {}
        self.semantic_analyzer = SemanticAnalyzer()
        
        # 特征缩放器
        self.scaler = StandardScaler()
        
        # 模型集成
        self.models = {
            'rf': RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42
            ),
            'gb': GradientBoostingRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=42
            )
        }
        
        # 版本历史缓存
        self._version_history = {}
        
    def train(
        self,
        training_data: List[Dict],
        version_dates: List[datetime]
    ) -> None:
        """训练版本预测模型
        
        参数:
            training_data: 训练数据列表
            version_dates: 版本日期列表
        """
        try:
            # 提取特征
            X = self._extract_features(training_data)
            
            # 计算时间间隔作为目标变量
            y = self._compute_time_intervals(version_dates)
            
            # 特征缩放
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            for name, model in self.models.items():
                # 交叉验证
                scores = cross_val_score(
                    model, X_scaled, y,
                    cv=5,
                    scoring='neg_mean_squared_error'
                )
                mse_scores = -scores
                logging.info(
                    f"{name} 交叉验证MSE: "
                    f"{np.mean(mse_scores):.4f} (+/- {np.std(mse_scores):.4f})"
                )
                
                # 训练最终模型
                model.fit(X_scaled, y)
                
        except Exception as e:
            logging.error(f"训练版本预测模型时出错: {e}")
            
    def predict(self, code_changes: List[Dict]) -> Dict:
        """预测下一个版本的时间
        
        参数:
            code_changes: 代码变更列表
            
        返回:
            预测结果字典
        """
        try:
            # 提取特征
            X = self._extract_features(code_changes)
            
            # 特征缩放
            X_scaled = self.scaler.transform(X)
            
            # 模型集成预测
            predictions = []
            weights = {
                'rf': 0.6,
                'gb': 0.4
            }
            
            for name, model in self.models.items():
                pred = model.predict(X_scaled)[0]
                predictions.append(pred * weights[name])
                
            # 加权平均预测
            final_prediction = sum(predictions)
            
            # 计算置信区间
            confidence_interval = self._compute_confidence_interval(
                X_scaled,
                predictions
            )
            
            return {
                'predicted_interval': final_prediction,
                'confidence_interval': confidence_interval,
                'model_contributions': {
                    name: pred
                    for name, pred in zip(self.models.keys(), predictions)
                }
            }
            
        except Exception as e:
            logging.error(f"预测版本时出错: {e}")
            return {}
            
    def update(
        self,
        new_data: List[Dict],
        actual_version_date: datetime
    ) -> None:
        """增量更新模型
        
        参数:
            new_data: 新的训练数据
            actual_version_date: 实际版本日期
        """
        try:
            # 提取特征
            X_new = self._extract_features(new_data)
            
            # 计算实际时间间隔
            last_version_date = max(self._version_history.keys())
            y_new = (actual_version_date - last_version_date).days
            
            # 更新版本历史
            self._version_history[actual_version_date] = new_data
            
            # 特征缩放
            X_new_scaled = self.scaler.transform(X_new)
            
            # 增量更新模型
            for model in self.models.values():
                if hasattr(model, 'partial_fit'):
                    model.partial_fit(X_new_scaled, [y_new])
                else:
                    # 重新训练不支持增量学习的模型
                    X_all = self._extract_features(
                        [d for data in self._version_history.values()
                         for d in data]
                    )
                    y_all = self._compute_time_intervals(
                        list(self._version_history.keys())
                    )
                    X_all_scaled = self.scaler.transform(X_all)
                    model.fit(X_all_scaled, y_all)
                    
        except Exception as e:
            logging.error(f"增量更新模型时出错: {e}")
            
    def evaluate(
        self,
        test_data: List[Dict],
        actual_dates: List[datetime]
    ) -> Dict:
        """评估模型性能
        
        参数:
            test_data: 测试数据列表
            actual_dates: 实际版本日期列表
            
        返回:
            评估指标字典
        """
        try:
            # 提取特征
            X_test = self._extract_features(test_data)
            
            # 计算实际时间间隔
            y_test = self._compute_time_intervals(actual_dates)
            
            # 特征缩放
            X_test_scaled = self.scaler.transform(X_test)
            
            # 评估各个模型
            metrics = {}
            for name, model in self.models.items():
                y_pred = model.predict(X_test_scaled)
                
                metrics[name] = {
                    'mse': mean_squared_error(y_test, y_pred),
                    'rmse': np.sqrt(mean_squared_error(y_test, y_pred)),
                    'r2': r2_score(y_test, y_pred)
                }
                
            return metrics
            
        except Exception as e:
            logging.error(f"评估模型时出错: {e}")
            return {}
            
    def _extract_features(self, data: List[Dict]) -> np.ndarray:
        """提取预测特征
        
        参数:
            data: 代码变更数据列表
            
        返回:
            特征矩阵
        """
        features = []
        try:
            for item in data:
                # 代码变更特征
                change_features = [
                    item.get('lines_added', 0),
                    item.get('lines_deleted', 0),
                    item.get('files_changed', 0),
                    item.get('commit_frequency', 0),
                    item.get('author_experience', 0)
                ]
                
                # 语义特征
                if 'content' in item:
                    semantic_features = self.semantic_analyzer.extract_features(
                        item['content']
                    )
                    if 'tfidf' in semantic_features:
                        change_features.extend(semantic_features['tfidf'])
                        
                # 时序特征
                time_features = self._extract_time_features(item)
                change_features.extend(time_features)
                
                features.append(change_features)
                
            return np.array(features)
            
        except Exception as e:
            logging.error(f"提取特征时出错: {e}")
            return np.array([])
            
    def _extract_time_features(self, item: Dict) -> List[float]:
        """提取时序特征
        
        参数:
            item: 代码变更数据
            
        返回:
            时序特征列表
        """
        try:
            # 计算时间相关特征
            current_time = datetime.now()
            commit_time = item.get('commit_time', current_time)
            
            time_features = [
                # 距离上次提交的时间
                (current_time - commit_time).days,
                
                # 一周中的天数
                commit_time.weekday(),
                
                # 一天中的小时
                commit_time.hour,
                
                # 是否为工作日
                1 if commit_time.weekday() < 5 else 0
            ]
            
            return time_features
            
        except Exception as e:
            logging.error(f"提取时序特征时出错: {e}")
            return [0] * 4
            
    def _compute_time_intervals(
        self,
        dates: List[datetime]
    ) -> np.ndarray:
        """计算版本时间间隔
        
        参数:
            dates: 版本日期列表
            
        返回:
            时间间隔数组
        """
        try:
            # 按时间排序
            sorted_dates = sorted(dates)
            
            # 计算相邻版本的时间间隔（天数）
            intervals = []
            for i in range(1, len(sorted_dates)):
                interval = (sorted_dates[i] - sorted_dates[i-1]).days
                intervals.append(interval)
                
            return np.array(intervals)
            
        except Exception as e:
            logging.error(f"计算时间间隔时出错: {e}")
            return np.array([])
            
    def _compute_confidence_interval(
        self,
        X: np.ndarray,
        predictions: List[float],
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """计算预测的置信区间
        
        参数:
            X: 特征矩阵
            predictions: 各模型的预测结果
            confidence: 置信水平
            
        返回:
            置信区间元组 (下界, 上界)
        """
        try:
            # 计算预测标准差
            pred_std = np.std(predictions)
            
            # 计算置信区间
            from scipy import stats
            
            mean_pred = np.mean(predictions)
            degrees_of_freedom = len(predictions) - 1
            t_value = stats.t.ppf((1 + confidence) / 2, degrees_of_freedom)
            
            margin_of_error = t_value * pred_std / np.sqrt(len(predictions))
            
            return (
                mean_pred - margin_of_error,
                mean_pred + margin_of_error
            )
            
        except Exception as e:
            logging.error(f"计算置信区间时出错: {e}")
            return (0.0, 0.0) 