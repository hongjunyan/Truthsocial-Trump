FROM mcr.microsoft.com/playwright/python:v1.41.0-focal

WORKDIR /app

# 複製需要的檔案
COPY requirements.txt .
COPY monitor.py .
COPY config.py .

# 安裝python套件
RUN pip install --no-cache-dir -r requirements.txt

# 創建資料目錄
RUN mkdir -p /app/data

# 設置環境變量
ENV PYTHONUNBUFFERED=1

# 安裝Playwright瀏覽器
RUN playwright install chromium

# 運行監控腳本
CMD ["python", "monitor.py"] 