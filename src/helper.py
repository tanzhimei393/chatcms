import math
from datetime import datetime, timedelta
from typing import Union

def calculate_relative_time(published_at: Union[datetime, None], now: datetime = None) -> str:
    """
    计算相对时间字符串
    
    Args:
        published_at: 发布时间，如果为None表示时间未知
        now: 当前时间，默认为当前系统时间
    
    Returns:
        str: 相对时间字符串，如"刚刚"、"5分钟前"等
    """
    
    if published_at is None:
        return "未知时间"
    
    if now is None:
        now = datetime.now()
    
    time_diff = now - published_at
    
    if time_diff < timedelta(minutes=1):
        return "刚刚"
    elif time_diff < timedelta(hours=1):
        minutes = int(time_diff.total_seconds() / 60)
        return f"{minutes}分钟前"
    elif time_diff < timedelta(days=1):
        hours = int(time_diff.total_seconds() / 3600)
        return f"{hours}小时前"
    else:
        days = time_diff.days
        return f"{days}天前"
    
def get_weeks_diff(target_date):
    """
    计算目标日期距离当前时间的周数差
    """
    today = datetime.now().date()
    target_date = target_date.date() if isinstance(target_date, datetime) else target_date
    
    # 计算天数差
    days_diff = (today - target_date).days
    
    # 计算周数（向上取整）
    weeks_diff = math.ceil(days_diff / 7)
    
    return weeks_diff