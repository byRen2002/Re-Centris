#!/usr/bin/env python3
"""测试运行器

用于运行所有单元测试、集成测试和安全测试。
支持并行测试执行和测试报告生成。

作者: byRen2002
修改日期: 2025年3月
许可证: MIT
"""

import os
import sys
import unittest
import argparse
import coverage
import xmlrunner
import concurrent.futures
from typing import List, Tuple
from datetime import datetime

def discover_tests(start_dir: str) -> List[unittest.TestSuite]:
    """发现测试用例
    
    Args:
        start_dir: 起始目录
        
    Returns:
        测试套件列表
    """
    loader = unittest.TestLoader()
    suites = []
    
    for root, _, files in os.walk(start_dir):
        if any(f.startswith('test_') and f.endswith('.py') for f in files):
            suite = loader.discover(root, pattern='test_*.py')
            suites.append(suite)
            
    return suites

def run_test_suite(suite: unittest.TestSuite) -> Tuple[int, int, List[str]]:
    """运行测试套件
    
    Args:
        suite: 测试套件
        
    Returns:
        (成功数, 失败数, 错误信息列表)
    """
    result = unittest.TestResult()
    suite.run(result)
    
    errors = []
    for test, error in result.errors:
        errors.append(f"错误 ({test}): {error}")
    for test, failure in result.failures:
        errors.append(f"失败 ({test}): {failure}")
        
    return result.testsRun - len(result.failures) - len(result.errors), \
           len(result.failures) + len(result.errors), \
           errors

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Re-Centris 测试运行器')
    parser.add_argument('--parallel', action='store_true', help='并行运行测试')
    parser.add_argument('--coverage', action='store_true', help='生成覆盖率报告')
    parser.add_argument('--xml', action='store_true', help='生成XML测试报告')
    parser.add_argument('--html', action='store_true', help='生成HTML测试报告')
    args = parser.parse_args()
    
    # 设置覆盖率收集
    if args.coverage:
        cov = coverage.Coverage()
        cov.start()
        
    # 发现测试
    suites = discover_tests('tests')
    if not suites:
        print("未发现测试用例")
        sys.exit(1)
        
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    all_errors = []
    
    # 运行测试
    if args.parallel:
        print("并行运行测试...")
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = [executor.submit(run_test_suite, suite) for suite in suites]
            for future in concurrent.futures.as_completed(futures):
                passed, failed, errors = future.result()
                passed_tests += passed
                failed_tests += failed
                all_errors.extend(errors)
                total_tests += passed + failed
    else:
        print("串行运行测试...")
        for suite in suites:
            passed, failed, errors = run_test_suite(suite)
            passed_tests += passed
            failed_tests += failed
            all_errors.extend(errors)
            total_tests += passed + failed
            
    # 生成报告
    if args.xml:
        print("生成XML报告...")
        xml_dir = 'test-reports/xml'
        os.makedirs(xml_dir, exist_ok=True)
        for suite in suites:
            xmlrunner.XMLTestRunner(output=xml_dir).run(suite)
            
    if args.html:
        print("生成HTML报告...")
        html_dir = 'test-reports/html'
        os.makedirs(html_dir, exist_ok=True)
        with open(os.path.join(html_dir, 'index.html'), 'w') as f:
            f.write(f"""
            <html>
            <head><title>测试报告</title></head>
            <body>
            <h1>测试报告 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})</h1>
            <p>总测试数: {total_tests}</p>
            <p>通过: {passed_tests}</p>
            <p>失败: {failed_tests}</p>
            <h2>错误详情:</h2>
            <pre>{'<br>'.join(all_errors)}</pre>
            </body>
            </html>
            """)
            
    if args.coverage:
        print("生成覆盖率报告...")
        cov.stop()
        cov.save()
        
        # 生成报告
        cov_dir = 'test-reports/coverage'
        os.makedirs(cov_dir, exist_ok=True)
        
        # HTML报告
        cov.html_report(directory=os.path.join(cov_dir, 'html'))
        
        # XML报告
        cov.xml_report(outfile=os.path.join(cov_dir, 'coverage.xml'))
        
    # 打印结果
    print("\n测试结果汇总:")
    print(f"总测试数: {total_tests}")
    print(f"通过: {passed_tests}")
    print(f"失败: {failed_tests}")
    
    if all_errors:
        print("\n错误详情:")
        for error in all_errors:
            print(error)
            
    # 返回状态码
    return 1 if failed_tests > 0 else 0

if __name__ == '__main__':
    sys.exit(main()) 