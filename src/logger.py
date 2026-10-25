import logging
import os
from datetime import datetime

def setup_logger(name="review_scraper"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # ログが重複しないようにクリア
    if logger.hasHandlers():
        logger.handlers.clear()

    # ログのフォーマット
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # コンソール出力ハンドラ
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # ファイル出力ハンドラ
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"scrape_{timestamp}.log")
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
