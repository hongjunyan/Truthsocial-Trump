import json
import logging
import os
import time
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

TRUTH_SOCIAL_URL = "https://truthsocial.com/@realDonaldTrump"
DEBUG_DIR = "debug"  # 調試文件保存目錄
DATA_DIR = "data"    # 數據保存目錄

def create_directories():
    """創建必要的目錄"""
    for directory in [DEBUG_DIR, DATA_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"創建目錄: {directory}")

def calculate_jaccard_similarity(str1, str2):
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

def is_similar_content(new_content, existing_contents, threshold=0.7):
    """檢查新內容是否與現有內容相似"""
    for content in existing_contents:
        similarity = calculate_jaccard_similarity(new_content, content)
        if similarity >= threshold:
            return True
    return False

def truth_social_crawler():
    """收集 Truth Social 貼文的爬蟲"""
    logger.info("啟動 Truth Social 爬蟲...")
    create_directories()
    
    posts = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            
            # 訪問頁面
            logger.info(f"訪問 {TRUTH_SOCIAL_URL}")
            page.goto(TRUTH_SOCIAL_URL, wait_until="networkidle", timeout=60000)
            logger.info("頁面已加載，等待內容顯示...")
            
            # 等待頁面加載
            page.wait_for_timeout(5000)
            
            # 保存初始頁面截圖
            page.screenshot(path=os.path.join(DEBUG_DIR, "initial_page.png"))
            
            # 處理 cookie 接受按鈕
            accept_button = page.query_selector("button:has-text('Accept')")
            if accept_button:
                logger.info("點擊接受 cookie 按鈕")
                accept_button.click()
                page.wait_for_timeout(2000)
            
            # 收集初始頁面的貼文
            initial_posts = extract_posts_from_page(page, "initial")
            logger.info(f"初始頁面找到 {len(initial_posts)} 個貼文")
            
            all_posts = initial_posts.copy()
            
            # 滾動頁面 3 次收集更多貼文
            for i in range(3):
                logger.info(f"第 {i+1} 次滾動")
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(3000)  # 給頁面足夠時間加載新內容
                
                # 截圖當前頁面
                page.screenshot(path=os.path.join(DEBUG_DIR, f"scroll_{i+1}.png"))
                
                # 提取本次滾動後看到的貼文
                scroll_posts = extract_posts_from_page(page, f"scroll_{i+1}")
                logger.info(f"第 {i+1} 次滾動後找到 {len(scroll_posts)} 個貼文")
                
                all_posts.extend(scroll_posts)
            
            # 保存最終頁面源碼，用於進一步分析
            with open(os.path.join(DEBUG_DIR, "final_page.html"), "w", encoding="utf-8") as f:
                f.write(page.content())
            
            browser.close()
            
            # 使用 Jaccard 相似度去重
            if all_posts:
                unique_posts = remove_duplicates_using_jaccard(all_posts)
                
                # 保存去重後的貼文
                with open(os.path.join(DATA_DIR, "truth_social_posts.json"), "w", encoding="utf-8") as f:
                    json.dump(unique_posts, f, ensure_ascii=False, indent=2)
                
                logger.info(f"成功保存 {len(unique_posts)} 個去重後的貼文到文件")
                return unique_posts
            else:
                logger.warning("未找到任何貼文")
                return []
            
    except Exception as e:
        logger.error(f"爬蟲過程中發生嚴重錯誤: {str(e)}")
        return []

def extract_posts_from_page(page, source_identifier):
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

def remove_duplicates_using_jaccard(posts, similarity_threshold=0.7):
    """使用 Jaccard 相似度去除重複貼文"""
    unique_posts = []
    existing_contents = []
    
    for post in posts:
        content = post.get("content", "").lower()
        
        # 跳過太短的內容
        if len(content) < 20:
            continue
            
        # 檢查是否與現有內容相似
        if not is_similar_content(content, existing_contents, similarity_threshold):
            existing_contents.append(content)
            unique_posts.append(post)
            logger.info(f"添加唯一貼文: {content[:50]}...")
        else:
            logger.info(f"發現重複貼文: {content[:50]}...")
    
    logger.info(f"使用 Jaccard 相似度去重: 從 {len(posts)} 個貼文減少到 {len(unique_posts)} 個")
    return unique_posts

def display_posts(posts):
    """顯示提取的貼文"""
    if not posts:
        print("未找到任何貼文")
        return
    
    print(f"\n成功提取 {len(posts)} 個貼文:\n")
    
    for i, post in enumerate(posts):
        print(f"--- 貼文 {i+1} ---")
        print(f"日期: {post.get('date', '未知')}")
        print(f"作者: {post.get('author', '@realDonaldTrump')}")
        print(f"來源: {post.get('source', '未知')}")
        
        content = post.get('content', '')
        print(f"內容: {content}")
        
        print(f"提取方法: {post.get('selector_used', '未知')}")
        print("-" * 80)

if __name__ == "__main__":
    # 運行爬蟲
    posts = truth_social_crawler()
    
    # 顯示提取的貼文
    display_posts(posts) 