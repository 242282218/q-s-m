from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# 获取所有路由
routes = app.routes
print("所有注册的HTTP路由：")
for route in routes:
    if hasattr(route, 'methods'):
        print(f"路径: {route.path}, 方法: {route.methods}")

# 测试根路径
response = client.get("/")
print(f"\n根路径状态码: {response.status_code}")

# 测试夸克搜索路由
response = client.get("/api/quark/search/tmdb/299536?media_type=movie&max_results=5")
print(f"夸克搜索路由状态码: {response.status_code}")
print(f"响应内容: {response.text}")