# -*- coding: utf-8 -*-
"""
ETF回测系统 - 使用示例
"""

import etf_backtest as etfb


def example_basic_backtest():
    """
    基础回测示例

    配置3只ETF，按40%-30%-30%比例配置，
    偏离2%时触发调仓。
    """
    print("=" * 60)
    print("示例1: 基础ETF组合回测")
    print("=" * 60)

    # 定义ETF组合配置
    config = etfb.ETFPortfolioConfig(
        etf_list=[
            {"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.4},
            {"code": "SH512980", "name": "科创50ETF", "target_ratio": 0.3},
            {"code": "SZ159915", "name": "创业板ETF", "target_ratio": 0.3}
        ],
        start_date="2020-01-01",
        end_date="2023-12-31",
        initial_capital=100000,
        rebalance_threshold=0.02  # 2%偏离触发调仓
    )

    # 创建回测实例
    backtest = etfb.ETFPortfolioBacktest(config)

    # 运行回测
    backtest.backtest()

    # 打印报告
    backtest.print_report()

    return backtest


def example_different_thresholds():
    """
    对比不同偏离阈值的效果

    比较1%、2%、5%三种阈值的回测结果。
    """
    print("\n" + "=" * 60)
    print("示例2: 对比不同偏离阈值")
    print("=" * 60)

    # ETF配置
    etf_list = [
        {"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.5},
        {"code": "SZ159915", "name": "创业板ETF", "target_ratio": 0.5}
    ]

    thresholds = [0.01, 0.02, 0.05]
    reports = []
    labels = []

    for threshold in thresholds:
        print(f"\n--- 偏离阈值: {threshold:.1%} ---")

        config = etfb.ETFPortfolioConfig(
            etf_list=etf_list,
            start_date="2020-01-01",
            end_date="2023-12-31",
            initial_capital=100000,
            rebalance_threshold=threshold
        )

        backtest = etfb.ETFPortfolioBacktest(config, verbose=False)
        backtest.backtest()
        report = backtest.generate_report()

        reports.append(report)
        labels.append(f"{threshold:.1%}")

        print(f"调仓次数: {report['results']['rebalance_count']}")
        print(f"总收益率: {report['results']['total_return']:.2%}")

    # 绘制对比图
    etfb.compare_strategies(reports, labels)


def example_four_etf_portfolio():
    """
    四ETF平衡组合

    配置沪深300、中证500、创业板、科创50四只ETF。
    """
    print("\n" + "=" * 60)
    print("示例3: 四ETF平衡组合")
    print("=" * 60)

    config = etfb.ETFPortfolioConfig(
        etf_list=[
            {"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.25},
            {"code": "SH510500", "name": "中证500ETF", "target_ratio": 0.25},
            {"code": "SZ159915", "name": "创业板ETF", "target_ratio": 0.25},
            {"code": "SH512980", "name": "科创50ETF", "target_ratio": 0.25}
        ],
        start_date="2021-01-01",
        end_date="2023-12-31",
        initial_capital=100000,
        rebalance_threshold=0.03
    )

    backtest = etfb.ETFPortfolioBacktest(config)
    backtest.backtest()

    # 打印报告
    report = backtest.print_report()

    # 绘制净值曲线
    etfb.plot_portfolio_value(
        backtest.get_portfolio_history(),
        backtest.get_rebalance_dates()
    )

    # 绘制配置变化
    etfb.plot_allocation_history(
        backtest.get_portfolio_history(),
        config.etf_list
    )

    return backtest


def example_aggressive_portfolio():
    """
    进取型组合

    配置更高比例的科创和创业板ETF。
    """
    print("\n" + "=" * 60)
    print("示例4: 进取型组合")
    print("=" * 60)

    config = etfb.ETFPortfolioConfig(
        etf_list=[
            {"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.2},
            {"code": "SZ159915", "name": "创业板ETF", "target_ratio": 0.4},
            {"code": "SH512980", "name": "科创50ETF", "target_ratio": 0.4}
        ],
        start_date="2020-01-01",
        end_date="2023-12-31",
        initial_capital=100000,
        rebalance_threshold=0.02
    )

    backtest = etfb.ETFPortfolioBacktest(config)
    backtest.backtest()
    backtest.print_report()

    return backtest


def example_with_custom_dates():
    """
    自定义日期范围的回测
    """
    print("\n" + "=" * 60)
    print("示例5: 自定义日期范围")
    print("=" * 60)

    # 可以根据需要修改日期范围
    config = etfb.ETFPortfolioConfig(
        etf_list=[
            {"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.6},
            {"code": "SH510500", "name": "中证500ETF", "target_ratio": 0.4}
        ],
        start_date="2022-01-01",  # 自定义开始日期
        end_date="2024-12-31",    # 自定义结束日期
        initial_capital=50000,    # 自定义初始资金
        rebalance_threshold=0.025  # 2.5%阈值
    )

    backtest = etfb.ETFPortfolioBacktest(config)
    backtest.backtest()
    backtest.print_report()

    return backtest


if __name__ == "__main__":
    # 运行示例
    print("ETF回测系统示例\n")

    # 示例1: 基础回测
    bt1 = example_basic_backtest()

    # 示例2: 对比不同阈值
    # example_different_thresholds()

    # 示例3: 四ETF组合
    # bt3 = example_four_etf_portfolio()

    # 示例4: 进取型组合
    # bt4 = example_aggressive_portfolio()

    # 示例5: 自定义日期
    # bt5 = example_with_custom_dates()

    print("\n所有示例运行完成！")
