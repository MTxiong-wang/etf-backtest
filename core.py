# -*- coding: utf-8 -*-
"""
ETF回测系统 - 核心回测引擎
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

import xalpha as xa
from xalpha.backtest import BTE
from xalpha.universal import vinfo, get_daily
from xalpha.cons import opendate_set

from .config import ETFPortfolioConfig
from .data import ETFDataManager


class ETFPortfolioBacktest(BTE):
    """
    ETF投资组合回测类

    基于xalpha的BTE基类，实现ETF投资组合的再平衡回测。

    策略逻辑：
        1. 初始建仓：按目标比例分配资金买入各ETF
        2. 每日检查：计算每个ETF的实际持仓比例
        3. 偏离检测：当任何ETF比例偏离超过阈值时触发调仓
        4. 调仓执行：卖出超配部分，买入低配部分，恢复目标比例

    Attributes:
        config: ETFPortfolioConfig配置对象
        data_manager: ETFDataManager数据管理器
        trades: ETF交易记录字典 {code: trade对象}
        rebalance_count: 调仓次数统计
    """

    def __init__(
        self,
        config: ETFPortfolioConfig,
        data_manager: Optional[ETFDataManager] = None,
        verbose: bool = True
    ):
        """
        初始化回测引擎

        Args:
            config: ETF投资组合配置
            data_manager: 数据管理器，可选，默认创建新的
            verbose: 是否打印详细信息
        """
        self.config = config
        self.verbose = verbose

        # 创建数据管理器
        if data_manager is None:
            self.data_manager = ETFDataManager()
        else:
            self.data_manager = data_manager

        # 初始化父类
        super().__init__(
            start=config.start_date,
            end=config.end_date,
            totmoney=config.initial_capital,
            verbose=verbose
        )

        # 统计变量
        self.rebalance_count = 0
        self.rebalance_dates = []
        self.portfolio_history = []

    def prepare(self):
        """初始化回测环境，建仓买入"""
        # 获取所有ETF数据
        for etf_config in self.config.etf_list:
            code = etf_config['code']
            try:
                data = self.data_manager.fetch_etf_data(
                    code,
                    self.config.start_date,
                    self.config.end_date
                )

                if data.empty:
                    print(f"警告: {code} 数据为空，请检查代码是否正确")

                # 使用vinfo创建info对象（用于股票/ETF）
                self.infos[code] = vinfo(
                    code,
                    start=self.config.start_date,
                    end=self.config.end_date
                )

            except Exception as e:
                print(f"警告: 获取 {code} 数据失败: {e}")

        # 标记是否已建仓
        self.is_initialized = False

    def run(self, date: pd.Timestamp):
        """
        单日回测逻辑

        Args:
            date: 交易日期
        """
        # 首次运行时建仓
        if not self.is_initialized:
            self._initial_purchase(date)
            self.is_initialized = True
            return

        # 检查是否需要调仓
        if self._check_rebalance_needed(date):
            self._execute_rebalance(date)

        # 记录当前组合状态
        self._record_portfolio_status(date)

    def _initial_purchase(self, date: pd.Timestamp):
        """
        初始建仓，按目标比例买入各ETF

        Args:
            date: 建仓日期
        """
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"初始建仓: {date.strftime('%Y-%m-%d')}")
            print(f"Initial capital: CNY {self.config.initial_capital:,.2f}")
            print(f"{'='*60}")

        for etf_config in self.config.etf_list:
            code = etf_config['code']
            name = etf_config['name']
            target_ratio = etf_config['target_ratio']
            invest_amount = self.config.initial_capital * target_ratio

            try:
                self.buy(code, invest_amount, date)
                if self.verbose:
                    print(f"  买入 {code} ({name}): CNY{invest_amount:,.2f} ({target_ratio:.2%})")
            except Exception as e:
                print(f"  错误: 买入 {code} 失败: {e}")

    def _check_rebalance_needed(self, date: pd.Timestamp) -> bool:
        """
        检查是否需要调仓

        计算当前组合中各ETF的实际比例，与目标比例对比。
        如果任何ETF的偏离度超过阈值，则返回True。

        Args:
            date: 检查日期

        Returns:
            bool: 是否需要调仓
        """
        # 获取当前组合
        sys = self.get_current_mul()
        if sys is None:
            return False

        # 获取组合摘要
        try:
            summary_df = sys.summary(date.strftime("%Y-%m-%d"))
        except:
            return False

        # 获取总资产
        total_row = summary_df[summary_df["基金名称"] == "总计"]
        if total_row.empty:
            return False

        total_value = total_row["基金现值"].iloc[0]

        if total_value <= 0:
            return False

        # 检查每个ETF的偏离度
        for etf_config in self.config.etf_list:
            code = etf_config['code']
            target_ratio = etf_config['target_ratio']

            # 获取该ETF的当前市值
            etf_rows = summary_df[summary_df["基金代码"] == code[1:]]  # 去掉前缀
            if etf_rows.empty:
                continue

            current_value = etf_rows["基金现值"].iloc[0]
            current_ratio = current_value / total_value

            # 计算偏离度
            deviation = abs(current_ratio - target_ratio)

            if deviation > self.config.rebalance_threshold:
                if self.verbose:
                    print(f"\n检测到偏离: {code}")
                    print(f"  目标比例: {target_ratio:.2%}")
                    print(f"  当前比例: {current_ratio:.2%}")
                    print(f"  偏离度: {deviation:.2%} (阈值: {self.config.rebalance_threshold:.2%})")
                return True

        return False

    def _execute_rebalance(self, date: pd.Timestamp):
        """
        执行调仓操作

        计算每个ETF的目标金额，与当前持仓对比，
        卖出超配部分，买入低配部分。

        Args:
            date: 调仓日期
        """
        self.rebalance_count += 1
        self.rebalance_dates.append(date)

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"执行调仓 #{self.rebalance_count}: {date.strftime('%Y-%m-%d')}")
            print(f"{'='*60}")

        # 获取当前组合
        sys = self.get_current_mul()
        summary_df = sys.summary(date.strftime("%Y-%m-%d"))

        # 获取总资产
        total_value = summary_df[summary_df["基金名称"] == "总计"]["基金现值"].iloc[0]

        # 对每个ETF进行调仓
        for etf_config in self.config.etf_list:
            code = etf_config['code']
            name = etf_config['name']
            target_ratio = etf_config['target_ratio']
            target_value = total_value * target_ratio

            # 获取当前持仓
            etf_rows = summary_df[summary_df["基金代码"] == code[1:]]
            if etf_rows.empty:
                current_value = 0
                current_nav = 0
            else:
                current_value = etf_rows["基金现值"].iloc[0]
                current_nav = etf_rows.get("当日净值", pd.Series([0])).iloc[0]

            delta = current_value - target_value

            # 忽略微小差异
            if abs(delta) < 1:
                continue

            try:
                if delta > 0:
                    # 卖出超配部分
                    # 计算需要卖出的份额（考虑赎回费，估算为0.5%）
                    sell_nav = current_nav if current_nav > 0 else 1
                    sell_share = round(delta / (1 - 0.005) / sell_nav, 2)
                    self.sell(code, sell_share, date)

                    if self.verbose:
                        print(f"  卖出 {code} ({name}): {sell_share} 份, 约 CNY{delta:,.2f}")
                else:
                    # 买入低配部分
                    buy_amount = abs(delta)
                    self.buy(code, buy_amount, date)

                    if self.verbose:
                        print(f"  买入 {code} ({name}): CNY{buy_amount:,.2f}")
            except Exception as e:
                print(f"  错误: 调仓 {code} 失败: {e}")

    def _record_portfolio_status(self, date: pd.Timestamp):
        """
        记录当前组合状态

        Args:
            date: 记录日期
        """
        sys = self.get_current_mul()
        if sys is None:
            return

        try:
            summary_df = sys.summary(date.strftime("%Y-%m-%d"))
            total_value = summary_df[summary_df["基金名称"] == "总计"]["基金现值"].iloc[0]

            status = {
                'date': date,
                'total_value': total_value
            }

            for etf_config in self.config.etf_list:
                code = etf_config['code']
                etf_rows = summary_df[summary_df["基金代码"] == code[1:]]
                if not etf_rows.empty:
                    current_value = etf_rows["基金现值"].iloc[0]
                    status[code] = {
                        'value': current_value,
                        'ratio': current_value / total_value if total_value > 0 else 0
                    }

            self.portfolio_history.append(status)
        except:
            pass

    def generate_report(self) -> Dict:
        """
        生成回测报告

        Returns:
            Dict: 包含各项指标的回测报告
        """
        # 获取最终组合状态
        sys = self.get_current_mulfix()
        if sys is None:
            return {
                'error': '无交易记录'
            }

        # 获取回测期间的最后一个交易日
        if isinstance(self.end, str):
            end_date_str = self.end
        else:
            end_date_str = self.end.strftime("%Y-%m-%d")

        try:
            # 计算XIRR收益率
            xirr = sys.xirrrate(date=end_date_str)
        except:
            xirr = 0

        # 获取最终资产
        try:
            summary_df = sys.summary(end_date_str)
            final_value = summary_df[summary_df["基金名称"] == "总计"]["基金现值"].iloc[0]
        except:
            final_value = 0

        # 计算总收益
        total_return = (final_value - self.config.initial_capital) / self.config.initial_capital

        # 计算年化收益
        end_dt = pd.to_datetime(self.end) if isinstance(self.end, str) else self.end
        start_dt = pd.to_datetime(self.start) if isinstance(self.start, str) else self.start
        days = (end_dt - start_dt).days
        years = days / 365.25
        annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        # 计算最大回撤（简化版本）
        max_drawdown = self._calculate_max_drawdown()

        report = {
            'config': {
                'start_date': self.config.start_date,
                'end_date': self.config.end_date,
                'initial_capital': self.config.initial_capital,
                'rebalance_threshold': self.config.rebalance_threshold,
                'etf_list': self.config.etf_list
            },
            'results': {
                'final_value': final_value,
                'total_return': total_return,
                'annualized_return': annualized_return,
                'xirr': xirr,
                'max_drawdown': max_drawdown,
                'rebalance_count': self.rebalance_count
            },
            'portfolio_history': self.portfolio_history
        }

        return report

    def _calculate_max_drawdown(self) -> float:
        """
        计算最大回撤

        Returns:
            float: 最大回撤比例
        """
        if not self.portfolio_history:
            return 0

        values = [status['total_value'] for status in self.portfolio_history]
        if not values:
            return 0

        peak = values[0]
        max_dd = 0

        for value in values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        return max_dd

    def print_report(self):
        """打印格式化的回测报告"""
        report = self.generate_report()

        if 'error' in report:
            print(f"错误: {report['error']}")
            return

        print("\n" + "=" * 60)
        print("ETF投资组合回测报告")
        print("=" * 60)

        # 配置信息
        print("\n【配置信息】")
        print(f"回测期间: {report['config']['start_date']} 至 {report['config']['end_date']}")
        print(f"初始资金: CNY{report['config']['initial_capital']:,.2f}")
        print(f"偏离阈值: {report['config']['rebalance_threshold']:.2%}")

        print("\n【ETF配置】")
        for etf in report['config']['etf_list']:
            print(f"  {etf['code']} ({etf['name']}): {etf['target_ratio']:.2%}")

        # 回测结果
        print("\n【回测结果】")
        print(f"最终资产: CNY{report['results']['final_value']:,.2f}")
        print(f"总收益率: {report['results']['total_return']:.2%}")
        print(f"年化收益: {report['results']['annualized_return']:.2%}")
        print(f"内部收益率(XIRR): {report['results']['xirr']:.2%}")
        print(f"最大回撤: {report['results']['max_drawdown']:.2%}")
        print(f"调仓次数: {report['results']['rebalance_count']}")

        print("=" * 60 + "\n")

        return report

    def get_rebalance_dates(self) -> List[pd.Timestamp]:
        """获取所有调仓日期"""
        return self.rebalance_dates

    def get_portfolio_history(self) -> List[Dict]:
        """获取组合历史记录"""
        return self.portfolio_history
