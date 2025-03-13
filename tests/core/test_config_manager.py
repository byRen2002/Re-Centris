"""配置管理器测试模块

该模块包含了对ConfigManager类的单元测试。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT License
"""

import unittest
import os
import tempfile
import yaml
from unittest.mock import patch, MagicMock

from core.config_manager import ConfigManager

class TestConfigManager(unittest.TestCase):
    """ConfigManager类的测试用例"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建临时配置文件
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.yaml")
        
        # 测试配置数据
        self.test_config = {
            "paths": {
                "repo": "/path/to/repo",
                "results": "/path/to/results",
                "logs": "/path/to/logs"
            },
            "performance": {
                "max_workers": 4,
                "cache_size": 1000,
                "memory_limit": 1024,
                "timeout": 300
            },
            "logging": {
                "level": "INFO",
                "max_size": 10,
                "backup_count": 5
            }
        }
        
        # 写入测试配置
        with open(self.config_file, 'w') as f:
            yaml.dump(self.test_config, f)
            
        # 创建ConfigManager实例
        self.config_manager = ConfigManager(self.config_file)
        
    def tearDown(self):
        """测试后的清理工作"""
        # 删除临时文件和目录
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
        os.rmdir(self.temp_dir)
        
    def test_load_config(self):
        """测试配置加载"""
        # 验证配置是否正确加载
        self.assertEqual(
            self.config_manager.get("paths.repo"),
            "/path/to/repo"
        )
        self.assertEqual(
            self.config_manager.get("performance.max_workers"),
            4
        )
        
    def test_get_nested_value(self):
        """测试获取嵌套配置值"""
        # 测试多层嵌套
        self.assertEqual(
            self.config_manager.get("paths.repo"),
            "/path/to/repo"
        )
        
        # 测试不存在的路径
        self.assertIsNone(
            self.config_manager.get("nonexistent.path")
        )
        
        # 测试默认值
        self.assertEqual(
            self.config_manager.get("nonexistent.path", "default"),
            "default"
        )
        
    def test_set_value(self):
        """测试设置配置值"""
        # 设置新值
        self.config_manager.set("paths.new_path", "/new/path")
        
        # 验证设置成功
        self.assertEqual(
            self.config_manager.get("paths.new_path"),
            "/new/path"
        )
        
        # 更新现有值
        self.config_manager.set("paths.repo", "/updated/path")
        self.assertEqual(
            self.config_manager.get("paths.repo"),
            "/updated/path"
        )
        
    def test_save_config(self):
        """测试配置保存"""
        # 修改配置
        self.config_manager.set("paths.new_path", "/new/path")
        
        # 保存配置
        self.config_manager.save()
        
        # 重新加载配置并验证
        new_config = ConfigManager(self.config_file)
        self.assertEqual(
            new_config.get("paths.new_path"),
            "/new/path"
        )
        
    def test_environment_override(self):
        """测试环境变量覆盖"""
        with patch.dict('os.environ', {
            'RE_CENTRIS_PATHS_REPO': '/env/path',
            'RE_CENTRIS_PERFORMANCE_MAX_WORKERS': '8'
        }):
            # 重新加载配置
            config = ConfigManager(self.config_file)
            
            # 验证环境变量覆盖
            self.assertEqual(config.get("paths.repo"), "/env/path")
            self.assertEqual(config.get("performance.max_workers"), 8)
            
    def test_validation(self):
        """测试配置验证"""
        # 测试必需字段
        invalid_config = {"paths": {}}
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            yaml.dump(invalid_config, f)
            
        with self.assertRaises(ValueError):
            ConfigManager(f.name)
            
        os.unlink(f.name)
        
    def test_type_conversion(self):
        """测试类型转换"""
        # 测试数字转换
        self.assertIsInstance(
            self.config_manager.get("performance.max_workers"),
            int
        )
        
        # 测试布尔值转换
        self.config_manager.set("feature.enabled", "true")
        self.assertIsInstance(
            self.config_manager.get("feature.enabled"),
            bool
        )
        
    def test_merge_configs(self):
        """测试配置合并"""
        # 创建另一个配置文件
        other_config = {
            "paths": {
                "temp": "/path/to/temp"
            },
            "new_section": {
                "key": "value"
            }
        }
        
        other_file = os.path.join(self.temp_dir, "other.yaml")
        with open(other_file, 'w') as f:
            yaml.dump(other_config, f)
            
        # 合并配置
        self.config_manager.merge(other_file)
        
        # 验证合并结果
        self.assertEqual(
            self.config_manager.get("paths.temp"),
            "/path/to/temp"
        )
        self.assertEqual(
            self.config_manager.get("new_section.key"),
            "value"
        )
        
        # 清理
        os.remove(other_file)

if __name__ == '__main__':
    unittest.main() 