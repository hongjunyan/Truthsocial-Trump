# Truth Social 川普發文監控

這個專案監控唐納德·川普在 Truth Social 上的發文，並在有新發文時通過 Gmail 發送通知。

## 功能

- 定期檢查川普在 Truth Social 上的發文
- 檢測新發文並通過 Gmail 發送通知
- 防止重複通知
- 使用 Docker 容器化方便部署

## 配置與使用

### 前提條件

- Docker 和 Docker Compose
- Gmail 帳號（需要設置應用密碼）

### 使用步驟

1. 克隆儲存庫到本地

2. 修改 `.env` 檔案，填入您的郵箱資訊：
   ```
   GMAIL_USER=你的Gmail地址
   GMAIL_PASSWORD=你的Gmail應用密碼
   RECIPIENTS_FILE=/app/recipients.txt
   CHECK_INTERVAL_MINUTES=30  # 檢查間隔（分鐘）
   ```

3. 構建並啟動容器：
   ```bash
   docker-compose up -d
   ```

4. 查看日誌：
   ```bash
   docker-compose logs -f
   ```

### Gmail 應用密碼設置

1. 訪問您的 Google 帳號
2. 導航到安全性設置
3. 啟用兩步驗證
4. 創建應用密碼
5. 在 `.env` 檔案中使用該應用密碼

## 注意事項

- 請確保您的 Gmail 帳號已啟用「不夠安全的應用」訪問權限或使用應用密碼
- 程式使用 Playwright 進行網頁抓取，可能需要隨著網站變化進行更新 