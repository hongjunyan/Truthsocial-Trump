FROM mcr.microsoft.com/playwright/python:v1.41.0-focal

WORKDIR /app

# 复制需要的文件
COPY requirements.txt .
COPY monitor.py .
COPY config.py .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 创建数据目录
RUN mkdir -p /app/data

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 安装Playwright浏览器
RUN playwright install chromium

# 运行监控脚本
CMD ["python", "monitor.py"] 