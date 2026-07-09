# -*- coding: utf-8 -*-
"""
ETF回测系统 - 工具函数模块
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import Dict, List

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


def format_report(report: Dict) -> str:
    """
    格式化回测报告为文本

    Args:
        report: generate_report()返回的报告字典

    Returns:
        str: 格式化的报告文本
    """
    if 'error' in report:
        return f"错误: {report['error']}"

    lines = []
    lines.append("=" * 60)
    lines.append("ETF投资组合回测报告")
    lines.append("=" * 60)

    # 配置信息
    lines.append("\n【配置信息】")
    lines.append(f"回测期间: {report['config']['start_date']} 至 {report['config']['end_date']}")
    lines.append(f"初始资金: CNY{report['config']['initial_capital']:,.2f}")
    lines.append(f"偏离阈值: {report['config']['rebalance_threshold']:.2%}")

    lines.append("\n【ETF配置】")
    for etf in report['config']['etf_list']:
        lines.append(f"  {etf['code']} ({etf['name']}): {etf['target_ratio']:.2%}")

    # 回测结果
    lines.append("\n【回测结果】")
    lines.append(f"最终资产: CNY{report['results']['final_value']:,.2f}")
    lines.append(f"总收益率: {report['results']['total_return']:.2%}")
    lines.append(f"年化收益: {report['results']['annualized_return']:.2%}")
    lines.append(f"内部收益率(XIRR): {report['results']['xirr']:.2%}")
    lines.append(f"最大回撤: {report['results']['max_drawdown']:.2%}")
    lines.append(f"调仓次数: {report['results']['rebalance_count']}")

    lines.append("=" * 60)

    return "\n".join(lines)


def plot_portfolio_value(
    portfolio_history: List[Dict],
    rebalance_dates: List = None,
    save_path: str = None
):
    """
    绘制组合净值曲线

    Args:
        portfolio_history: 组合历史记录
        rebalance_dates: 调仓日期列表
        save_path: 保存路径，可选
    """
    if not portfolio_history:
        print("无历史数据可绘制")
        return

    # 提取数据
    dates = [status['date'] for status in portfolio_history]
    values = [status['total_value'] for status in portfolio_history]

    # 创建图表
    fig, ax = plt.subplots(figsize=(12, 6))

    # 绘制净值曲线
    ax.plot(dates, values, linewidth=2, label='组合净值', color='#2E86AB')

    # 标记调仓点
    if rebalance_dates:
        rebalance_values = []
        for rd in rebalance_dates:
            # 找到最接近的历史记录
            for status in portfolio_history:
                if status['date'] >= rd:
                    rebalance_values.append(status['total_value'])
                    break
        if rebalance_values:
            ax.scatter(
                rebalance_dates[:len(rebalance_values)],
                rebalance_values,
                color='#A23B72',
                s=100,
                zorder=5,
                label='调仓点'
            )

    ax.set_xlabel('日期', fontsize=12)
    ax.set_ylabel('净值 (元)', fontsize=12)
    ax.set_title('ETF投资组合净值曲线', fontsize=14, fontweight='bold')
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3)

    # 格式化x轴日期
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.xticks(rotation=45)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"图表已保存至: {save_path}")
    else:
        plt.show()

    plt.close()


def plot_allocation_history(
    portfolio_history: List[Dict],
    etf_list: List[Dict],
    save_path: str = None
):
    """
    绘制配置变化历史（堆叠面积图）

    Args:
        portfolio_history: 组合历史记录
        etf_list: ETF配置列表
        save_path: 保存路径，可选
    """
    if not portfolio_history:
        print("无历史数据可绘制")
        return

    # 准备数据
    dates = [status['date'] for status in portfolio_history]

    fig, ax = plt.subplots(figsize=(12, 6))

    # 为每个ETF绘制面积图
    colors = ['#2E86AB', '#A23B72', '#F18D01', '#C73E1D', '#6A994E', '#BC4B51']

    for i, etf in enumerate(etf_list):
        code = etf['code']
        name = etf['name']
        ratios = []

        for status in portfolio_history:
            if code in status:
                ratios.append(status[code]['ratio'])
            else:
                ratios.append(0)

        ax.fill_between(
            dates,
            [sum(ratios[:j]) for j in range(len(dates))],
            [sum(ratios[:j+1]) for j in range(len(dates))],
            label=f"{code} ({name})",
            alpha=0.7,
            color=colors[i % len(colors)]
        )

    ax.set_xlabel('日期', fontsize=12)
    ax.set_ylabel('配置比例', fontsize=12)
    ax.set_title('ETF配置比例变化', fontsize=14, fontweight='bold')
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1)

    # 格式化x轴日期
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"图表已保存至: {save_path}")
    else:
        plt.show()

    plt.close()


def calculate_returns_series(portfolio_history: List[Dict]) -> pd.Series:
    """
    计算收益率序列

    Args:
        portfolio_history: 组合历史记录

    Returns:
        pd.Series: 收益率序列
    """
    if not portfolio_history:
        return pd.Series()

    initial_value = portfolio_history[0]['total_value']
    returns = []

    for status in portfolio_history:
        if initial_value > 0:
            ret = (status['total_value'] - initial_value) / initial_value
            returns.append(ret)

    return pd.Series(returns, index=[status['date'] for status in portfolio_history])


def plot_returns_distribution(
    portfolio_history: List[Dict],
    save_path: str = None
):
    """
    绘制收益率分布直方图

    Args:
        portfolio_history: 组合历史记录
        save_path: 保存路径，可选
    """
    if not portfolio_history:
        print("无历史数据可绘制")
        return

    returns = calculate_returns_series(portfolio_history)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # 收益率曲线
    ax1.plot(returns.index, returns.values * 100, linewidth=2, color='#2E86AB')
    ax1.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax1.set_xlabel('日期', fontsize=12)
    ax1.set_ylabel('累计收益率 (%)', fontsize=12)
    ax1.set_title('累计收益率曲线', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

    # 收益率分布
    daily_returns = returns.diff().dropna() * 100
    ax2.hist(daily_returns.values, bins=50, color='#A23B72', alpha=0.7, edgecolor='black')
    ax2.axvline(x=daily_returns.mean(), color='red', linestyle='--', linewidth=2, label=f'均值: {daily_returns.mean():.2f}%')
    ax2.set_xlabel('日收益率 (%)', fontsize=12)
    ax2.set_ylabel('频数', fontsize=12)
    ax2.set_title('日收益率分布', fontsize=14, fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"图表已保存至: {save_path}")
    else:
        plt.show()

    plt.close()


def compare_strategies(
    reports: List[Dict],
    labels: List[str],
    save_path: str = None
):
    """
    比较多个策略的回测结果

    Args:
        reports: 回测报告列表
        labels: 策略标签列表
        save_path: 保存路径，可选
    """
    if len(reports) != len(labels):
        raise ValueError("报告数量与标签数量不匹配")

    # 提取关键指标
    metrics = ['总收益率', '年化收益', '最大回撤', '调仓次数']
    data = {metric: [] for metric in metrics}

    for report in reports:
        if 'results' in report:
            data['总收益率'].append(f"{report['results']['total_return']:.2%}")
            data['年化收益'].append(f"{report['results']['annualized_return']:.2%}")
            data['最大回撤'].append(f"{report['results']['max_drawdown']:.2%}")
            data['调仓次数'].append(report['results']['rebalance_count'])
        else:
            for metric in metrics:
                data[metric].append('N/A')

    # 创建表格
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.axis('tight')
    ax.axis('off')

    # 构建表格数据
    table_data = [['指标'] + labels]
    for metric in metrics:
        row = [metric] + data[metric]
        table_data.append(row)

    table = ax.table(
        cellText=table_data,
        cellLoc='center',
        loc='center',
        colWidths=[0.2] + [0.2] * len(labels)
    )

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)

    # 设置表头样式
    for i in range(len(labels) + 1):
        table[(0, i)].set_facecolor('#4472C4')
        table[(0, i)].set_text_props(weight='bold', color='white')

    ax.set_title('策略对比', fontsize=14, fontweight='bold', pad=20)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"图表已保存至: {save_path}")
    else:
        plt.show()

    plt.close()
