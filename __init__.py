# -*- coding: utf-8 -*-
"""
ETF回测系统

基于xalpha框架的ETF投资组合回测工具，支持：
- 多只ETF按比例配置
- 偏离阈值触发的再平衡
- 完整的回测报告和可视化
"""

from .config import ETFPortfolioConfig, validate_etf_code, normalize_ratios
from .data import ETFDataManager
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
    'ETFDataManager',
    'ETFPortfolioBacktest',
    'format_report',
    'plot_portfolio_value',
    'plot_allocation_history',
    'plot_returns_distribution',
    'compare_strategies'
]
