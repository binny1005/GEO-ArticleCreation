"""统一日志"""

import logging
import sys

# 格式: [时间] [级别] [模块] 消息
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """获取命名 logger，自动配置 handler"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        # Windows GBK 终端兼容：设置 UTF-8 编码
        handler.setStream(sys.stdout)
        try:
            handler.stream.reconfigure(encoding='utf-8')
        except Exception:
            pass
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
