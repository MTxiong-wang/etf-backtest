# -*- coding: utf-8 -*-
"""
ETF回测系统

基于xalpha框架的ETF投资组合回测工具，支持：
- 多只ETF按比例配置
- 偏离阈值触发的再平衡
- 完整的回测报告和可视化
"""

import os

from xalpha.universal import set_backend as _set_xa_backend

# 行情缓存目录（csv 落盘，回测唯一行情来源）。场内 <前缀码>.csv、场外 INFO-<6位码>.csv。
_DEFAULT_CACHE_DIR = os.path.join(
    os.path.dirname(__file__), "data", "market_cache"
)


def configure_cache(path=_DEFAULT_CACHE_DIR, backend="csv"):
    """
    配置 xalpha ``get_daily`` 的缓存后端。

    默认 ``csv`` 落盘到 ``data/market_cache/``，**全标的覆盖**：场内（``vinfo``→
    ``get_daily``）落盘 ``<前缀码>.csv``，场外基金（``fundinfo``/``mfundinfo``→
    ``basicinfo`` fetch/save，``info.py`` 自动对接 ``set_backend``）落盘
    ``INFO-<6位码>.csv``。首次抓某标的即写盘其全部可获取历史；后续请求纯读盘过滤
    （场内）或读盘+增量核对（场外），不再全量联网。

    Args:
        path: 缓存目录；传 None 则退回 xalpha 默认的内存后端（不落盘）。
        backend: ``"csv"`` / ``"sql"`` / ``"memory"``，详见 ``xa.set_backend``。

    Returns:
        None.
    """
    ioconf = {"backend": backend}
    if path:
        os.makedirs(path, exist_ok=True)
        ioconf["path"] = path
    _set_xa_backend(**ioconf)


# 导入即默认启用 CSV 落盘。须在任何 get_daily 调用前完成；
# 下方子模块的顶层代码不会触发 get_daily，故在此处配置即可。
configure_cache()


import logging
import sys


def setup_logging():
    """配置日志：UTF-8 stdout/stderr + 时间戳格式 + 落盘到 output/run.log。

    解决 Windows 控制台默认 GBK 中文乱码，给日志加时间戳，并追加写入
    ``output/run.log``（多次运行的日志累积，UTF-8 编码）。在 ``import etf_backtest``
    时自动调用一次。
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    handlers = [logging.StreamHandler(sys.stdout)]
    log_dir = os.path.join(os.path.dirname(__file__), "output")
    try:
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(
            os.path.join(log_dir, "run.log"), mode="a", encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


# 导入即配置日志（UTF-8 + 时间戳）
setup_logging()

from .config import ETFPortfolioConfig, validate_etf_code, normalize_ratios
from .core import ETFPortfolioBacktest
from .utils import (
    format_report,
    plot_portfolio_value,
    plot_allocation_history,
    plot_returns_distribution,
    compare_strategies
)

__version__ = "0.1.0"
__all__ = [
    'ETFPortfolioConfig',
    'validate_etf_code',
    'normalize_ratios',
    'ETFPortfolioBacktest',
    'format_report',
    'plot_portfolio_value',
    'plot_allocation_history',
    'plot_returns_distribution',
    'compare_strategies'
]
