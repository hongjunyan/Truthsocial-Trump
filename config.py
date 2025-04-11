import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Truth Social 设置
TRUTH_SOCIAL_URL = "https://truthsocial.com/@realDonaldTrump"

# Gmail 设置
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# 监控设置
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
DATA_FILE = "seen_posts.json" 