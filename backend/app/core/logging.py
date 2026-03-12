import logging
import re
import sys
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

from .config import get_settings
from .paths import ensure_directory, resolve_log_dir


SENSITIVE_PATTERNS = [
    (re.compile(r'(cookie[=:]\s*)[^\s&;\n]+', re.IGNORECASE), r'\1***REDACTED***'),
    (re.compile(r'(token[=:]\s*)[^\s&;\n]+', re.IGNORECASE), r'\1***REDACTED***'),
    (re.compile(r'(api_key[=:]\s*)[^\s&;\n]+', re.IGNORECASE), r'\1***REDACTED***'),
    (re.compile(r'(password[=:]\s*)[^\s&;\n]+', re.IGNORECASE), r'\1***REDACTED***'),
    (re.compile(r'(Authorization[=:]\s*Bearer\s+)[^\s&;\n]+', re.IGNORECASE), r'\1***REDACTED***'),
    (re.compile(r'("cookie"\s*:\s*")[^"]*"', re.IGNORECASE), r'\1***REDACTED***"'),
    (re.compile(r'("token"\s*:\s*")[^"]*"', re.IGNORECASE), r'\1***REDACTED***"'),
]


def redact_sensitive_info(message: str) -> str:
    """过滤敏感信息"""
    for pattern, replacement in SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


class SensitiveDataFilter(logging.Filter):
    """敏感信息过滤器"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_info(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_sensitive_info(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_sensitive_info(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


class JsonFormatter(logging.Formatter):
    """JSON 格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        message = redact_sensitive_info(message)
        
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            log_data["exception"] = redact_sensitive_info(exc_text)
        
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging():
    settings = get_settings()
    log_level = settings.log_level.upper()
    
    formatter = JsonFormatter()
    sensitive_filter = SensitiveDataFilter()
    
    # 创建日志目录
    log_dir = ensure_directory(resolve_log_dir(settings.log_dir))
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    
    # 文件处理器 - 日志轮转配置
    log_file = os.path.join(log_dir, "app.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,  # 保留 10 个备份
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.handlers = [console_handler, file_handler]
    root_logger.addFilter(sensitive_filter)
    
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
