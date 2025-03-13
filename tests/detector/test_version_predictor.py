"""版本预测器测试模块

该模块实现了对版本预测器的测试用例。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
from datetime import datetime, timedelta
import numpy as np
from detector.version_predictor import VersionPredictor

class TestVersionPredictor(unittest.TestCase):
    """版本预测器测试类"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.predictor = VersionPredictor()
        
        # 生成测试数据
        self.training_data = self._generate_test_data()
        self.version_dates = self._generate_version_dates()
        
    def _generate_test_data(self):
        """生成测试数据"""
        return [
            {
                'lines_added': 100,
                'lines_deleted': 50,
                'files_changed': 5,
                'commit_frequency': 10,
                'author_experience': 100,
                'commit_time': datetime.now() - timedelta(days=30),
                'content': 'def test_function():\n    pass'
            },
            {
                'lines_added': 200,
                'lines_deleted': 100,
                'files_changed': 10,
                'commit_frequency': 15,
                'author_experience': 150,
                'commit_time': datetime.now() - timedelta(days=20),
                'content': 'class TestClass:\n    def method(self):\n        pass'
            }
        ]
        
    def _generate_version_dates(self):
        """生成版本日期"""
        base_date = datetime.now() - timedelta(days=60)
        return [
            base_date + timedelta(days=i*15)
            for i in range(5)
        ]
        
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.predictor)
        self.assertIsNotNone(self.predictor.models)
        self.assertIsNotNone(self.predictor.scaler)
        
    def test_feature_extraction(self):
        """测试特征提取"""
        features = self.predictor._extract_features(self.training_data)
        
        self.assertIsInstance(features, np.ndarray)
        self.assertEqual(len(features), len(self.training_data))
        
    def test_time_feature_extraction(self):
        """测试时序特征提取"""
        time_features = self.predictor._extract_time_features(
            self.training_data[0]
        )
        
        self.assertIsInstance(time_features, list)
        self.assertEqual(len(time_features), 4)  # 4个时序特征
        
    def test_time_interval_computation(self):
        """测试时间间隔计算"""
        intervals = self.predictor._compute_time_intervals(
            self.version_dates
        )
        
        self.assertIsInstance(intervals, np.ndarray)
        self.assertEqual(len(intervals), len(self.version_dates) - 1)
        
    def test_model_training(self):
        """测试模型训练"""
        self.predictor.train(
            self.training_data,
            self.version_dates
        )
        
        # 验证模型是否已训练
        for model in self.predictor.models.values():
            self.assertTrue(hasattr(model, 'predict'))
            
    def test_version_prediction(self):
        """测试版本预测"""
        # 先训练模型
        self.predictor.train(
            self.training_data,
            self.version_dates
        )
        
        # 进行预测
        prediction = self.predictor.predict(self.training_data)
        
        self.assertIsInstance(prediction, dict)
        self.assertIn('predicted_interval', prediction)
        self.assertIn('confidence_interval', prediction)
        self.assertIn('model_contributions', prediction)
        
    def test_model_update(self):
        """测试模型更新"""
        # 先训练模型
        self.predictor.train(
            self.training_data,
            self.version_dates
        )
        
        # 准备新数据
        new_data = [{
            'lines_added': 150,
            'lines_deleted': 75,
            'files_changed': 7,
            'commit_frequency': 12,
            'author_experience': 120,
            'commit_time': datetime.now() - timedelta(days=10),
            'content': 'def new_function():\n    return True'
        }]
        
        new_date = datetime.now()
        
        # 更新模型
        self.predictor.update(new_data, new_date)
        
        # 验证更新后的预测
        prediction = self.predictor.predict(new_data)
        self.assertIsInstance(prediction, dict)
        
    def test_model_evaluation(self):
        """测试模型评估"""
        # 先训练模型
        self.predictor.train(
            self.training_data,
            self.version_dates
        )
        
        # 准备测试数据
        test_data = self._generate_test_data()
        test_dates = [
            datetime.now() + timedelta(days=i*15)
            for i in range(3)
        ]
        
        # 评估模型
        metrics = self.predictor.evaluate(test_data, test_dates)
        
        self.assertIsInstance(metrics, dict)
        for model_metrics in metrics.values():
            self.assertIn('mse', model_metrics)
            self.assertIn('rmse', model_metrics)
            self.assertIn('r2', model_metrics)
            
    def test_confidence_interval(self):
        """测试置信区间计算"""
        X = np.array([[1, 2, 3], [4, 5, 6]])
        predictions = [10, 12, 15]
        
        interval = self.predictor._compute_confidence_interval(
            X,
            predictions
        )
        
        self.assertIsInstance(interval, tuple)
        self.assertEqual(len(interval), 2)
        self.assertLess(interval[0], interval[1])
        
    def test_error_handling(self):
        """测试错误处理"""
        # 测试空数据
        empty_prediction = self.predictor.predict([])
        self.assertEqual(empty_prediction, {})
        
        # 测试无效数据
        invalid_data = [{'invalid_key': 'value'}]
        features = self.predictor._extract_features(invalid_data)
        self.assertEqual(len(features), 1)
        
        # 测试无效日期
        invalid_dates = []
        intervals = self.predictor._compute_time_intervals(invalid_dates)
        self.assertEqual(len(intervals), 0)
        
if __name__ == '__main__':
    unittest.main() 