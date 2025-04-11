import json
import logging
import os
import smtplib
import time
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import urllib.parse
import random

import schedule
from playwright.sync_api import sync_playwright

from config import (CHECK_INTERVAL_MINUTES, DATA_FILE, GMAIL_PASSWORD,
                   GMAIL_USER, RECIPIENT_EMAIL, TRUTH_SOCIAL_URL)

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 調試文件保存目錄
DEBUG_DIR = "debug"
DATA_DIR = "data"  # 數據保存目錄

class TruthSocialMonitor:
    def __init__(self):
        self.data_file = DATA_FILE
        self.seen_posts = self._load_seen_posts()
        self._create_directories()
        # 載入收件人列表
        self.recipients = self._load_recipients()
        logger.info(f"已載入 {len(self.recipients)} 個收件人: {', '.join(self.recipients)}")
    
    def _create_directories(self):
        """創建必要的目錄"""
        for directory in [DEBUG_DIR, DATA_DIR]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logger.info(f"創建目錄: {directory}")
    
    def _load_seen_posts(self):
        """加載已經發送通知的貼文ID"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"無法解析 {self.data_file}，將創建新文件")
                return {}
        return {}
    
    def _save_seen_posts(self):
        """保存已經發送通知的貼文ID"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.seen_posts, f, ensure_ascii=False, indent=2)
    
    def _calculate_jaccard_similarity(self, str1, str2):
        """計算兩個字符串的 Jaccard 相似度"""
        # 將字符串轉換為單詞集合
        set1 = set(re.findall(r'\w+', str1.lower()))
        set2 = set(re.findall(r'\w+', str2.lower()))
        
        # 計算 Jaccard 相似度
        if not set1 or not set2:
            return 0
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0

    def _is_similar_content(self, new_content, existing_contents, threshold=0.7):
        def _clean_content(_content: str):
            tokens = _content.split(" ")
            if len(tokens) > 3:
                return " ".join(tokens[:-3])
            else:
                return _content
        new_content = _clean_content(new_content)

        """檢查新內容是否與現有內容相似"""
        for content in existing_contents:
            content = _clean_content(content)
            similarity = self._calculate_jaccard_similarity(new_content, content)
            if similarity >= threshold:
                return True
        return False

    def _extract_posts_from_page(self, page, source_identifier):
        """從頁面提取貼文"""
        posts = []
        
        # 嘗試不同的選擇器找出貼文元素
        selectors = [
            # 從截圖分析的可能選擇器
            "[role='article']",
            "article",
            "div.timeline-item",
            "div.status-wrapper",
            "div.status",
            # 一些更通用的選擇器
            "div[role='article']",
            ".truth-item",
            ".truth-card",
            ".post-card",
            ".entry-content",
        ]
        
        post_elements = []
        used_selector = ""
        
        for selector in selectors:
            elements = page.query_selector_all(selector)
            if elements and len(elements) > 0:
                logger.info(f"使用選擇器 '{selector}' 找到 {len(elements)} 個元素")
                if len(elements) > len(post_elements):
                    post_elements = elements
                    used_selector = selector
        
        # 處理找到的元素
        for i, element in enumerate(post_elements):
            try:
                # 提取元素內容
                text_content = element.inner_text().strip()
                
                # 只處理足夠長的內容，這可能是一個實際貼文
                if len(text_content) < 50:
                    continue
                
                # 只關注特定用戶的貼文
                if ("Trump" not in text_content and 
                    "@realDonaldTrump" not in text_content):
                    continue
                
                # 保存元素截圖以供分析
                try:
                    element.screenshot(path=os.path.join(DEBUG_DIR, f"{source_identifier}_post_{i}.png"))
                except:
                    pass
                
                # 提取日期信息
                date_element = element.query_selector("time") or element.query_selector("[datetime]")
                post_date = "unknown"
                if date_element:
                    post_date = date_element.inner_text() or date_element.get_attribute("datetime") or "unknown"
                
                # 清理文本內容
                clean_content = " ".join(text_content.split())
                
                # 確保不是 cookie 政策或其他非貼文內容
                if ("cookie" in clean_content.lower() and 
                    "privacy" in clean_content.lower()):
                    continue
                
                posts.append({
                    "id": f"{source_identifier}_post_{i}_{datetime.now().isoformat()}",
                    "content": clean_content,
                    "date": post_date,
                    "author": "@realDonaldTrump",
                    "selector_used": used_selector,
                    "source": source_identifier,
                    "crawled_at": datetime.now().isoformat()
                })
                
                logger.info(f"從 {source_identifier} 提取到貼文 {i}: {clean_content[:50]}...")
            except Exception as e:
                logger.error(f"處理 {source_identifier} 元素 {i} 時出錯: {str(e)}")
        
        return posts

    def _remove_duplicates_using_jaccard(self, posts, similarity_threshold=0.7):
        """使用 Jaccard 相似度去除重複貼文"""
        unique_posts = []
        existing_contents = []
        
        for post in posts:
            content = post.get("content", "").lower()
            
            # 跳過太短的內容
            if len(content) < 20:
                continue
                
            # 檢查是否與現有內容相似
            if not self._is_similar_content(content, existing_contents, similarity_threshold):
                existing_contents.append(content)
                unique_posts.append(post)
                logger.info(f"添加唯一貼文: {content[:50]}...")
            else:
                logger.info(f"發現重複貼文: {content[:50]}...")
        
        logger.info(f"使用 Jaccard 相似度去重: 從 {len(posts)} 個貼文減少到 {len(unique_posts)} 個")
        return unique_posts
    
    def send_notification(self, posts):
        """通過Gmail發送通知，將多個貼文整合到一封郵件中"""
        try:
            if not posts:
                logger.info("沒有新貼文需要發送通知")
                return False
            
            # 準備所有貼文的內容，用於ChatGPT摘要和翻譯
            all_post_contents = ""
            for post in posts:
                post_date = post.get('date', 'unknown')
                post_content = post.get('content', '')
                all_post_contents += f"日期: {post_date}\n內容: {post_content}\n\n"
            
            # URL編碼所有貼文內容
            encoded_content = urllib.parse.quote(all_post_contents)
            
            # 創建ChatGPT摘要和翻譯的URL
            summary_prompt = "請用繁體中文摘要以下內容:"
            translation_prompt = "請將以下的貼文內容翻譯成繁體中文:"
            
            summary_url = f"https://chatgpt.com/?q={urllib.parse.quote(summary_prompt)}{encoded_content}"
            translation_url = f"https://chatgpt.com/?q={urllib.parse.quote(translation_prompt)}{encoded_content}"
            summary_url = summary_url[:8121]
            translation_url = translation_url[:8121]
            
            msg = MIMEMultipart()
            msg['From'] = f'Trump Truth Social Monitor'
            msg['To'] = ','.join(self.recipients)
            msg['Subject'] = f"Truth Social 新貼文通知 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # 構建郵件內容，包含所有新貼文
            body = f"""
            <html>
            <body>
                <h2>川普在Truth Social上發布了新內容</h2>
                <div style="margin-bottom: 20px; padding: 10px; background-color: #f0f8ff; border-radius: 5px;">
                    <p>快速功能:</p>
                    <p><a href="{summary_url}" target="_blank" style="display: inline-block; margin-right: 15px; padding: 8px 15px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 4px;">由ChatGPT摘要</a>
                    <a href="{translation_url}" target="_blank" style="display: inline-block; padding: 8px 15px; background-color: #2196F3; color: white; text-decoration: none; border-radius: 4px;">由ChatGPT翻譯</a></p>
                </div>
                <p>發現 {len(posts)} 則新貼文:</p>
            """
            
            # 添加每一則貼文
            for i, post in enumerate(posts, 1):
                post_date = post.get('date', 'unknown')
                post_content = post.get('content', '')
                
                body += f"""
                <div style="margin-bottom: 20px; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                    <h3>貼文 {i}</h3>
                    <p><strong>發布時間:</strong> {post_date}</p>
                    <p><strong>內容:</strong></p>
                    <blockquote style="background-color: #f9f9f9; padding: 10px; border-left: 4px solid #ccc;">
                        {post_content}
                    </blockquote>
                </div>
                """
            
            body += f"""
                <p><a href="{TRUTH_SOCIAL_URL}">查看更多 Truth Social 內容</a></p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, 'html'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, self.recipients, msg.as_string())
            server.quit()
            
            logger.info(f"已發送包含 {len(posts)} 則新貼文的通知郵件")
            return True
        except Exception as e:
            logger.error(f"發送email失敗: {str(e)}")
            return False
    
    def fetch_posts(self):
        """使用增強版的爬蟲功能抓取Truth Social的貼文"""
        logger.info("開始抓取貼文...")
        
        try:
            with sync_playwright() as p:
                # 使用更擬人化的瀏覽器設定
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
                    ]
                )
                
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/New_York",
                    permissions=["geolocation"],
                    has_touch=False,
                    # 添加額外的HTTP頭部
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Accept-Encoding": "gzip, deflate, br",
                        "DNT": "1",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Pragma": "no-cache",
                        "Cache-Control": "no-cache",
                    }
                )
                
                # 添加模擬真實用戶的JavaScript
                context.add_init_script("""
                    // 覆蓋 navigator.webdriver
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => false,
                    });
                    
                    // 覆蓋其他可能被檢測的屬性
                    window.navigator.chrome = {
                        runtime: {},
                    };
                    
                    // 添加隨機鼠標移動函數
                    const originalQuery = document.querySelector;
                    document.querySelector = function() {
                        // 添加一些隨機延遲
                        return originalQuery.apply(document, arguments);
                    };
                """)
                
                page = context.new_page()
                
                # 模擬真實用戶行為
                # 先訪問一個常見網站，然後再訪問目標網站
                logger.info("先訪問 Google 再訪問目標網站...")
                page.goto("https://www.google.com", wait_until="networkidle")
                page.wait_for_timeout(3000)  # 隨機等待 3 秒
                
                # 處理 cookie 同意對話框
                try:
                    if page.query_selector("button:has-text('Accept all')"):
                        page.click("button:has-text('Accept all')")
                        page.wait_for_timeout(1000)
                except:
                    pass
                
                # 使用更加人性化的方式訪問目標網站
                logger.info(f"訪問 {TRUTH_SOCIAL_URL}")
                page.goto(TRUTH_SOCIAL_URL, wait_until="domcontentloaded", timeout=60000)
                
                # 隨機等待以模擬人類行為
                wait_time = 3000 + (1000 * (2 * (random.random() - 0.5)))
                page.wait_for_timeout(wait_time)
                
                # 模擬滑鼠隨機移動和滾動
                page.mouse.move(random.randint(100, 700), random.randint(100, 500))
                
                # 等待更長時間讓頁面完全加載
                page.wait_for_load_state("networkidle", timeout=60000)
                logger.info("頁面已加載，等待內容顯示...")
                
                # 保存初始頁面截圖
                page.screenshot(path=os.path.join(DEBUG_DIR, "initial_page.png"))
                
                # 處理 cookie 接受按鈕
                try:
                    accept_button = page.query_selector("button:has-text('Accept')")
                    if accept_button:
                        logger.info("點擊接受 cookie 按鈕")
                        accept_button.click()
                        page.wait_for_timeout(2000)
                except:
                    pass
                
                # 檢查是否遇到 Cloudflare 挑戰頁面
                if "Cloudflare" in page.title():
                    logger.warning("遇到 Cloudflare 挑戰頁面，嘗試等待更長時間...")
                    # 保存 Cloudflare 頁面以供分析
                    page.screenshot(path=os.path.join(DEBUG_DIR, "cloudflare_challenge.png"))
                    # 等待更長時間允許 Cloudflare 檢查完成
                    page.wait_for_timeout(30000)  # 等待 30 秒
                
                # 收集初始頁面的貼文
                initial_posts = self._extract_posts_from_page(page, "initial")
                logger.info(f"初始頁面找到 {len(initial_posts)} 個貼文")
                
                all_posts = initial_posts.copy()
                
                # 滾動頁面收集更多貼文
                for i in range(3):
                    logger.info(f"第 {i+1} 次滾動")
                    # 使用更自然的滾動
                    page.evaluate("window.scrollBy({top: 800, left: 0, behavior: 'smooth'})")
                    # 隨機等待時間
                    page.wait_for_timeout(2000 + random.randint(500, 2000))
                    
                    # 截圖當前頁面
                    page.screenshot(path=os.path.join(DEBUG_DIR, f"scroll_{i+1}.png"))
                    
                    # 提取本次滾動後看到的貼文
                    scroll_posts = self._extract_posts_from_page(page, f"scroll_{i+1}")
                    logger.info(f"第 {i+1} 次滾動後找到 {len(scroll_posts)} 個貼文")
                    
                    all_posts.extend(scroll_posts)
                
                # 保存最終頁面源碼，用於進一步分析
                with open(os.path.join(DEBUG_DIR, "final_page.html"), "w", encoding="utf-8") as f:
                    f.write(page.content())
                
                browser.close()
                
                # 使用 Jaccard 相似度去重
                if all_posts:
                    unique_posts = self._remove_duplicates_using_jaccard(all_posts)
                    logger.info(f"成功獲取 {len(unique_posts)} 個去重後的貼文")
                    return unique_posts
                else:
                    logger.warning("未找到任何貼文")
                    return []
                
        except Exception as e:
            logger.error(f"爬蟲過程中發生嚴重錯誤: {str(e)}")
            return []
    
    def check_and_notify(self):
        """檢查新貼文並發送通知"""
        try:
            # 重新載入收件人列表（確保每次檢查使用最新的收件人設定）
            self.recipients = self._load_recipients()
            
            posts = self.fetch_posts()
            
            # 找出新貼文
            new_posts = []
            # 從已通知記錄中提取所有內容用於相似度檢查
            existing_contents = [post_info.get("content", "") for post_info in self.seen_posts.values()]
            
            logger.info(f"比對 {len(posts)} 個新抓取貼文與 {len(existing_contents)} 個已通知貼文")
            
            for post in posts:
                post_content = post.get("content", "")
                post_id = post.get("id", "")
                
                # 跳過太短的內容
                if len(post_content) < 100:
                    # 比方說純影片的內容
                    logger.info(f"跳過太短的貼文: {post_content}...")
                    continue
                    
                # 檢查ID是否已存在（精確匹配）
                if post_id in self.seen_posts:
                    logger.info(f"跳過已通知的貼文ID: {post_id}")
                    continue
                    
                # 使用 Jaccard 相似度檢查內容是否相似（模糊匹配）
                if self._is_similar_content(post_content, existing_contents):
                    logger.info(f"跳過相似內容貼文: {post_content[:50]}...")
                    # 仍然記錄這個ID以避免未來再次檢查
                    self.seen_posts[post_id] = {
                        "content": post_content,
                        "date": post.get("date", "unknown"),
                        "notified_at": "skipped_similar",
                        "skipped_at": datetime.now().isoformat()
                    }
                    continue
                
                # 這是新貼文，添加到通知列表
                new_posts.append(post)
                self.seen_posts[post_id] = {
                    "content": post_content,
                    "date": post.get("date", "unknown"),
                    "notified_at": datetime.now().isoformat()
                }
            
            # 所有新貼文整合到一封郵件中發送
            notification_sent = False
            if new_posts:
                notification_sent = self.send_notification(new_posts)
            
            # 保存已通知貼文
            self._save_seen_posts()
            
            if new_posts:
                status = "成功" if notification_sent else "失敗"
                logger.info(f"發現 {len(new_posts)} 個新貼文，發送整合通知 {status}")
            else:
                logger.info("沒有發現新貼文")
                
        except Exception as e:
            logger.error(f"檢查過程出錯: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _load_recipients(self):
        """從檔案中載入收件人列表"""
        recipients = []
        
        # 先檢查環境變數中的收件人檔案路徑
        recipients_file = os.environ.get('RECIPIENTS_FILE', '/app/recipients.txt')
        
        try:
            # 檢查檔案是否存在
            if os.path.exists(recipients_file):
                with open(recipients_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        # 去除空白並忽略註解行
                        email = line.strip()
                        if email and not email.startswith('#'):
                            recipients.append(email)
                logger.info(f"從檔案 {recipients_file} 中載入收件人列表")
            else:
                # 如果檔案不存在，嘗試從環境變數中讀取單一收件人
                if RECIPIENT_EMAIL:
                    recipients = [RECIPIENT_EMAIL]
                    logger.info(f"使用環境變數中的收件人: {RECIPIENT_EMAIL}")
                else:
                    logger.warning("未找到收件人檔案，且環境變數中沒有設定 RECIPIENT_EMAIL")
        except Exception as e:
            logger.error(f"讀取收件人檔案時發生錯誤: {str(e)}")
            if RECIPIENT_EMAIL:
                recipients = [RECIPIENT_EMAIL]
                logger.info(f"使用環境變數中的備用收件人: {RECIPIENT_EMAIL}")
        
        # 確保至少有一個收件人
        if not recipients:
            logger.warning("沒有設定收件人，通知將無法發送")
            
        return recipients

def main():
    """主函數，設置定時任務"""
    monitor = TruthSocialMonitor()
    
    # 首次啟動立即運行一次
    monitor.check_and_notify()
    
    # 定義檢查函數
    def scheduled_check():
        monitor.check_and_notify()

    # 設置定時任務：每小時的第01分鐘執行
    schedule.every().hour.at(":01").do(scheduled_check)

    logger.info("監控服務已啟動，將在每小時的第01分鐘執行檢查")
    
    # 保持程序運行並執行定時任務
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main() 