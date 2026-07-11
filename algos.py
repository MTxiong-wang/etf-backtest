# -*- coding: utf-8 -*-
"""
策略算法模块（借鉴 bt.Algo 的模块化思路）。

每个 Algo 封装一步回测逻辑，``ETFPortfolioBacktest.run`` 遍历 ``algo_stack`` 顺序执行。
默认栈 ``[AlgoRebalance, AlgoRecord]`` 包装 ``core.py`` 现有方法，行为与重构前一致；
用户可传自定义 ``algo_stack`` 组合新 Algo（如只记录不调仓 = 买入持有）。
"""

from typing import Optional


class Algo:
    """策略算法基类。

    ``run`` 在每个监控日被 ``ETFPortfolioBacktest.run`` 调用，可读写 bt 状态、
    返回更新后的 ``summary_df``（或 ``None`` 中断栈，后续 Algo 不执行）。
    """

    def run(self, bt, date, summary_df):
        return summary_df


class AlgoRebalance(Algo):
    """检查持仓偏离并按需调仓。

    包装 ``bt._check_rebalance_needed`` + ``_execute_rebalance``（内部按
    ``rebalance_mode`` 分发 band/absolute）。触发调仓后重新取当日快照返回。
    """

    def run(self, bt, date, summary_df):
        if bt._check_rebalance_needed(date, summary_df):
            bt._execute_rebalance(date)
            summary_df = bt._daily_summary(date)
        return summary_df


class AlgoRecord(Algo):
    """记录当日组合状态（包装 ``bt._record_portfolio_status``）。"""

    def run(self, bt, date, summary_df):
        bt._record_portfolio_status(date, summary_df)
        return summary_df
