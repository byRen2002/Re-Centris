import unittest
import time
from typing import List
from core.parallel_manager import ParallelManager

class TestParallelManager(unittest.TestCase):
    """ParallelManager单元测试"""
    
    def setUp(self):
        """测试前准备"""
        self.manager = ParallelManager(max_workers=2)
        
    def tearDown(self):
        """测试后清理"""
        self.manager.close_all()
        
    def test_process_items_empty(self):
        """测试处理空列表"""
        result = self.manager.process_items([], lambda x: x)
        self.assertEqual(result, [])
        
    def test_process_items_single_chunk(self):
        """测试处理单个数据块"""
        def square_numbers(nums: List[int]) -> List[int]:
            return [x * x for x in nums]
            
        items = [1, 2, 3, 4, 5]
        result = self.manager.process_items(
            items=items,
            process_func=square_numbers,
            chunk_size=5
        )
        self.assertEqual(result, [1, 4, 9, 16, 25])
        
    def test_process_items_multiple_chunks(self):
        """测试处理多个数据块"""
        def sum_numbers(nums: List[int]) -> int:
            return sum(nums)
            
        items = list(range(100))
        result = self.manager.process_items(
            items=items,
            process_func=sum_numbers,
            chunk_size=10
        )
        self.assertEqual(sum(result), sum(range(100)))
        
    def test_process_items_with_threads(self):
        """测试使用线程池处理"""
        def slow_increment(nums: List[int]) -> List[int]:
            time.sleep(0.1)  # 模拟耗时操作
            return [x + 1 for x in nums]
            
        items = list(range(10))
        result = self.manager.process_items(
            items=items,
            process_func=slow_increment,
            use_threads=True,
            chunk_size=2
        )
        self.assertEqual(result, [x + 1 for x in range(10)])
        
    def test_process_items_with_progress(self):
        """测试带进度回调的处理"""
        progress_updates = []
        
        def track_progress(current: int, total: int):
            progress_updates.append((current, total))
            
        def double_numbers(nums: List[int]) -> List[int]:
            return [x * 2 for x in nums]
            
        items = list(range(5))
        result = self.manager.process_items_with_progress(
            items=items,
            process_func=double_numbers,
            progress_callback=track_progress,
            chunk_size=1
        )
        
        self.assertEqual(result, [x * 2 for x in range(5)])
        self.assertEqual(len(progress_updates), 5)
        self.assertEqual(progress_updates[-1], (5, 5))
        
    def test_error_handling(self):
        """测试错误处理"""
        def failing_func(nums: List[int]) -> List[int]:
            raise ValueError("测试错误")
            
        items = list(range(5))
        result = self.manager.process_items(
            items=items,
            process_func=failing_func
        )
        self.assertEqual(result, [])
        
    def test_pool_management(self):
        """测试池管理"""
        # 测试进程池创建和关闭
        self.manager.process_items(
            items=[1, 2, 3],
            process_func=lambda x: x,
            pool_name="test_pool"
        )
        self.assertIn("test_pool", self.manager._process_pools)
        
        # 测试关闭特定池
        self.manager.close_pool("test_pool")
        self.assertNotIn("test_pool", self.manager._process_pools)
        
        # 测试关闭所有池
        self.manager.process_items(
            items=[1, 2, 3],
            process_func=lambda x: x,
            pool_name="another_pool"
        )
        self.manager.close_all()
        self.assertEqual(len(self.manager._process_pools), 0)
        self.assertEqual(len(self.manager._thread_pools), 0)
        
    def test_large_data_processing(self):
        """测试大数据处理"""
        items = list(range(10000))
        
        def process_chunk(nums: List[int]) -> List[int]:
            return [x * x for x in nums]
            
        result = self.manager.process_items(
            items=items,
            process_func=process_chunk,
            chunk_size=100
        )
        
        self.assertEqual(len(result), 10000)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[-1], 9999 * 9999)
        
    def test_concurrent_processing(self):
        """测试并发处理"""
        start_time = time.time()
        
        def slow_process(nums: List[int]) -> List[int]:
            time.sleep(0.1)  # 模拟耗时操作
            return nums
            
        items = list(range(20))
        self.manager.process_items(
            items=items,
            process_func=slow_process,
            chunk_size=2
        )
        
        duration = time.time() - start_time
        # 由于使用2个工作进程，处理时间应该小于串行处理的一半
        self.assertLess(duration, 1.0)  # 串行需要2秒

if __name__ == '__main__':
    unittest.main() 