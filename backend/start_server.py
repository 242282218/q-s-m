#!/usr/bin/env python3
"""
启动服务器的简单脚本
"""
import subprocess
import sys
import time

if __name__ == "__main__":
    # 使用不同的端口，避免端口占用问题
    port = 7799
    
    print(f"启动服务器，端口：{port}")
    
    # 启动uvicorn服务器
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", 
            "app.main:app", 
            f"--port", str(port),
            "--host", "0.0.0.0",
            "--log-level", "info"
        ],
        cwd=".",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # 等待服务器启动
    time.sleep(3)
    
    # 检查服务器是否启动成功
    if process.poll() is not None:
        print("服务器启动失败！")
        # 打印输出
        if process.stdout:
            for line in process.stdout:
                print(line.strip())
    else:
        print(f"服务器成功启动，访问地址：http://localhost:{port}")
        print("按 Ctrl+C 停止服务器")
        
        try:
            # 等待用户中断
            process.wait()
        except KeyboardInterrupt:
            print("\n停止服务器...")
            process.terminate()
            process.wait(timeout=5)
            print("服务器已停止")
        except Exception as e:
            print(f"\n停止服务器时发生错误：{e}")
            process.kill()
            process.wait(timeout=5)
