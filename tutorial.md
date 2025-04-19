# 手把手教你打造一個 Truth Social 監控爬蟲

有時候，市場大跌不是因為經濟數據，也不是聯準會放鷹，而是因為川普凌晨三點發了一篇貼文。最近，他隨口提到「關稅」，結果股市瞬間翻綠——我投資五年多，還真沒看過這麼慘的畫面。

這幾天，我被推坑了一個叫 Truth Social 的社群平台，原本沒聽過，一查才發現這竟然是川普自己創的。想想也合理，既然是他親手打造的媒體平台，那最新的風向、最即時的發言，應該都會第一時間出現在上面。

剛好最近在玩爬蟲，索性就做了一個小專案，24 小時盯著川普又說了什麼，也順便寫下這篇文章記錄一下所用到的技術。

---

## 第一步：用 Playwright 控制瀏覽器

Truth Social 是個 JavaScript-heavy 的網站，傳統的 `requests` + `BeautifulSoup` 是搞不定的。我們需要讓瀏覽器「打開」頁面、等待內容載入，然後從 DOM 中抓資料。

### 安裝必要套件

```bash
pip install playwright
playwright install chromium
```

### 初始化瀏覽器

然後，我們需要撰寫基本程式碼來開啟頁面並模擬真實用戶行為：

```python
from playwright.sync_api import sync_playwright
from loguru import logger


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    TRUTH_SOCIAL_URL = "https://truthsocial.com/@realDonaldTrump"
    page = context.new_page()
    page.goto(TRUTH_SOCIAL_URL, wait_until="networkidle", timeout=60000)
    logger.info("頁面已加載，等待內容顯示...")

    # 等待頁面加載
    page.wait_for_timeout(1000)
```

## 第二步：動態選擇器策略應對 DOM 變動

Truth Social 網站的 DOM 結構經常變動，我們不能只靠單一 selector。例如下面這段策略，我們會輪流嘗試各種可能的選擇器：

```python
selectors = [
    "[role='article']", "article", "div.timeline-item",
    "div.status-wrapper", "div.status", ".truth-item",
    ".truth-card", ".post-card", ".entry-content"
]

posts = []
for selector in selectors:
    elements = page.query_selector_all(selector)
    if len(elements) > len(posts):
        posts = elements

# 將每一篇貼文顯示出來
for i, element in enumerate(posts):
    try:
        # 提取元素內容
        text_content = element.inner_text().strip()
        logger.info(f"貼文 {i} 的內容: {text_content}")
    except Exception as e:
        logger.error(f"爬取貼文 {i} 發生錯誤: {str(e)}")
```

## 第三步：模擬滾動，擷取更多貼文

Truth Social 會在使用者滾動時載入更多貼文。所以我們必須模擬這個動作：

```python
for i in range(3):  # 視需求滾動次數
    page.evaluate("window.scrollBy(0, 800)")
    page.wait_for_timeout(3000)  # 給時間載入內容
```

## 第四步：完整程式碼

我們將上面提到的功能整裡一下，下面是完整程式碼:

```python
from playwright.sync_api import sync_playwright
from loguru import logger


def parser_posts(page):
    selectors = [
        "[role='article']", "article", "div.timeline-item",
        "div.status-wrapper", "div.status", ".truth-item",
        ".truth-card", ".post-card", ".entry-content"
    ]

    posts = []
    for selector in selectors:
        elements = page.query_selector_all(selector)
        if len(elements) > len(posts):
            print("Use selector: ", selector)
            posts = elements
    return posts

def show_posts(posts):
    """將爬取的貼文顯示出來"""
    for i, element in enumerate(posts):
        try:
            # 提取元素內容
            text_content = element.inner_text().strip()
            readable_content = " ".join(text_content.split())
            logger.info(f"貼文 {i} 的內容: {readable_content}")
        except Exception as e:
            logger.error(f"爬取貼文 {i} 發生錯誤: {str(e)}")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    TRUTH_SOCIAL_URL = "https://truthsocial.com/@realDonaldTrump"
    page = context.new_page()
    page.goto(TRUTH_SOCIAL_URL, wait_until="networkidle", timeout=60000)
    logger.info("頁面已加載，等待內容顯示...")

    # 等待頁面加載
    page.wait_for_timeout(1000)

    posts = parser_posts(page)
    show_posts(posts)

    for i in range(3):  # 視需求滾動次數
        page.evaluate("window.scrollBy(0, 800)")
        page.wait_for_timeout(3000)  # 給時間載入內容

        posts = parser_posts(page)
        show_posts(posts)
```