"""
压力测试脚本 - 使用 locust 进行高并发测试
"""
import asyncio
import aiohttp
import time
import statistics
from typing import Dict, List, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StressTester:
    """压力测试器"""
    
    def __init__(self, base_url: str = "http://localhost:7799"):
        self.base_url = base_url
        self.results: Dict[str, Any] = {}
    
    async def stress_test_endpoint(
        self,
        endpoint: str,
        concurrent_users: int,
        requests_per_user: int = 10
    ) -> Dict[str, Any]:
        """
        对单个端点进行压力测试
        
        Args:
            endpoint: API 端点
            concurrent_users: 并发用户数
            requests_per_user: 每个用户发送的请求数
        """
        logger.info(f"\n压力测试：{endpoint}, 并发数：{concurrent_users}")
        
        async with aiohttp.ClientSession() as session:
            response_times: List[float] = []
            success_count = 0
            error_count = 0
            
            async def make_request(user_id: int, req_id: int):
                nonlocal success_count, error_count
                start = time.perf_counter()
                try:
                    async with session.get(f"{self.base_url}{endpoint}") as resp:
                        duration = time.perf_counter() - start
                        response_times.append(duration)
                        if resp.status == 200:
                            success_count += 1
                        else:
                            error_count += 1
                except Exception as e:
                    duration = time.perf_counter() - start
                    response_times.append(duration)
                    error_count += 1
            
            # 创建所有任务
            tasks = []
            for user in range(concurrent_users):
                for req in range(requests_per_user):
                    tasks.append(make_request(user, req))
            
            # 执行测试
            start_time = time.perf_counter()
            
            # 分批次执行以避免过度负载
            batch_size = 100
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                await asyncio.gather(*batch)
            
            total_duration = time.perf_counter() - start_time
            
            # 计算统计信息
            if response_times:
                avg_response = statistics.mean(response_times) * 1000
                min_response = min(response_times) * 1000
                max_response = max(response_times) * 1000
                p95_response = statistics.quantiles(response_times, n=100)[94] * 1000 if len(response_times) > 1 else max_response
                p99_response = statistics.quantiles(response_times, n=100)[98] * 1000 if len(response_times) > 1 else max_response
            else:
                avg_response = min_response = max_response = p95_response = p99_response = 0
            
            total_requests = success_count + error_count
            requests_per_second = total_requests / total_duration if total_duration > 0 else 0
            
            return {
                "endpoint": endpoint,
                "concurrent_users": concurrent_users,
                "total_requests": total_requests,
                "success_count": success_count,
                "error_count": error_count,
                "success_rate_percent": round(success_count / total_requests * 100, 2) if total_requests > 0 else 0,
                "total_duration_seconds": round(total_duration, 2),
                "requests_per_second": round(requests_per_second, 2),
                "avg_response_time_ms": round(avg_response, 2),
                "min_response_time_ms": round(min_response, 2),
                "max_response_time_ms": round(max_response, 2),
                "p95_response_time_ms": round(p95_response, 2),
                "p99_response_time_ms": round(p99_response, 2),
            }
    
    async def run_stress_tests(self):
        """运行所有压力测试"""
        logger.info("\n" + "="*60)
        logger.info("开始压力测试")
        logger.info("="*60)
        
        # 测试不同并发级别
        test_configs = [
            ("/api/v1/health", 10),
            ("/api/v1/health", 50),
            ("/api/v1/health", 100),
        ]
        
        for endpoint, concurrent in test_configs:
            try:
                result = await self.stress_test_endpoint(endpoint, concurrent, requests_per_user=10)
                test_name = f"stress_{endpoint.replace('/', '_')}_{concurrent}_users"
                self.results[test_name] = result
                logger.info(f"✓ {test_name}: {result['requests_per_second']} req/s, "
                           f"成功率 {result['success_rate_percent']}%")
            except Exception as e:
                logger.error(f"压力测试失败 {endpoint} ({concurrent} 并发): {e}")
        
        return self.results


async def main():
    """主函数"""
    tester = StressTester()
    results = await tester.run_stress_tests()
    
    # 打印汇总
    print("\n\n" + "="*60)
    print("压力测试汇总")
    print("="*60)
    
    for test_name, result in results.items():
        print(f"\n{test_name}:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    
    # 保存结果
    with open("stress_test_results.json", "w", encoding="utf-8") as f:
        import json
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存到 stress_test_results.json")


if __name__ == "__main__":
    asyncio.run(main())
