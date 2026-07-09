# -*- coding: utf-8 -*-
"""
ETF回测系统测试脚本
"""
import sys
sys.path.insert(0, 'D:/Codes')

import pandas as pd
import xalpha as xa
from xalpha.universal import get_daily, vinfo
from xalpha.backtest import BTE
from xalpha.cons import convert_date, opendate_set

print("=" * 60)
print("ETF回测系统测试")
print("=" * 60)

# 导入我们的模块（需要先安装etf_backtest）
try:
    from etf_backtest.config import ETFPortfolioConfig
    from etf_backtest.data import ETFDataManager
    from etf_backtest.core import ETFPortfolioBacktest
    print("\n模块导入成功")
except ImportError as e:
    print(f"\n模块导入失败: {e}")
    print("请先运行: pip install -e D:/Codes/etf_backtest")
    sys.exit(1)

# 创建配置
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

# 测试数据获取
print("\n2. 测试数据获取...")
dm = ETFDataManager()
data = dm.fetch_etf_data("SH512100", "2023-01-01", "2023-12-31")
print(f"   SH512100: {len(data)} 个数据点")

# 创建回测引擎
print("\n3. 创建回测引擎...")
backtest = ETFPortfolioBacktest(config, verbose=True)
print("   回测引擎创建成功")

# 运行回测
print("\n4. 运行回测...")
backtest.backtest()
print("   回测完成")

# 生成报告
print("\n5. 生成报告...")
report = backtest.generate_report()
print(f"   最终资产: CNY{report['results']['final_value']:,.2f}")
print(f"   总收益率: {report['results']['total_return']:.2%}")
print(f"   调仓次数: {report['results']['rebalance_count']}")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
