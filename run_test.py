# -*- coding: utf-8 -*-
"""
完整回测测试脚本
"""
import sys
sys.path.insert(0, 'D:/Codes')

import xalpha as xa
from etf_backtest.config import ETFPortfolioConfig
from etf_backtest.core import ETFPortfolioBacktest

print("=" * 60)
print("ETF回测系统测试")
print("=" * 60)

print("\n1. 创建配置...")
config = ETFPortfolioConfig(
    etf_list=[
        {"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.6},
        {"code": "SZ159915", "name": "创业板ETF", "target_ratio": 0.4}
    ],
    start_date="2023-01-01",
    end_date="2023-12-31",
    initial_capital=10000,
    rebalance_threshold=0.02
)
print(f"   配置完成: {len(config.etf_list)} 只ETF")

print("\n2. 测试数据获取...")
data = xa.get_daily("SH512100", start="2023-01-01", end="2023-12-31")
print(f"   SH512100 数据点: {len(data)}")

print("\n3. 创建回测引擎...")
backtest = ETFPortfolioBacktest(config, verbose=True)
print("   回测引擎创建成功")

print("\n4. 运行回测...")
backtest.backtest()
print("   回测完成")

print("\n5. 生成报告...")
backtest.print_report()

print("\n测试完成！")
