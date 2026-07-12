# -*- coding: utf-8 -*-
"""
策略算法模块（借鉴 bt.Algo 的模块化思路）。

每个 Algo 封装一步回测逻辑，``ETFPortfolioBacktest.run`` 遍历 ``algo_stack`` 顺序执行。
默认栈 ``[AlgoRebalance, AlgoRecord]`` 包装 ``core.py`` 现有方法，行为与重构前一致；
用户可传自定义 ``algo_stack`` 组合新 Algo（如只记录不调仓 = 买入持有）。
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


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


class AlgoPerHoldingBand(Algo):
    """带状再平衡，每个标的用自己的 ``band_ratio``（混合 band）。

    从 ``bt.config.etf_list`` 读每个标的的 ``band_ratio``（未指定则用
    ``bt.config.band_ratio``）。标的实际权重落到 ``target*(1±band)`` 外即拉回目标，
    差额由 ``reservoir_code`` 吸收，复用 ``bt._swap`` 执行（先卖超配、后买低配）。
    不依赖 core 的 ``_check_band``/``_execute_band``（那些只服务统一 band 的 AlgoRebalance）。
    """

    def run(self, bt, date, summary_df):
        total_row = summary_df[summary_df["基金名称"] == "总计"]
        if total_row.empty:
            return summary_df
        total = total_row["基金现值"].iloc[0]
        if total <= 0:
            return summary_df

        res = bt.config.reservoir_code
        default_band = getattr(bt.config, "band_ratio", 0.5)

        def nav_of(code):
            rows = summary_df[summary_df["基金代码"] == bt.get_code(code)]
            if rows.empty:
                return 1.0
            v = rows.get("当日净值", pd.Series([0])).iloc[0]
            return v if v and v > 0 else 1.0

        triggers = []  # (code, name, delta): delta>0 超配(卖出), delta<0 低配(买入)
        for etf in bt.config.etf_list:
            code = etf["code"]
            if code == res:
                continue  # 资金池不调
            band = etf.get("band_ratio", default_band)
            target = etf["target_ratio"]
            rows = summary_df[summary_df["基金代码"] == bt.get_code(code)]
            if rows.empty:
                continue
            cur = rows["基金现值"].iloc[0]
            ratio = cur / total
            lo, hi = target * (1 - band), target * (1 + band)
            if lo <= ratio <= hi:
                continue  # 带内不动
            delta = cur - total * target
            if abs(delta) < 1:
                continue
            triggers.append((code, etf.get("name", code), delta))

        if not triggers:
            return summary_df

        bt.rebalance_count += 1
        bt.rebalance_dates.append(date)
        # 净额合并：累加每个标的的净流，每标的当天只发一笔（避免资金池同日多笔被
        # xalpha trade 丢弃→组合现值凭空虚增）。
        net = {}
        for code, name, delta in triggers:
            if delta > 0:
                net[code] = net.get(code, 0) - delta
                net[res] = net.get(res, 0) + delta
                bt.fee_cost += delta * bt.config.redeem_fee
            else:
                net[code] = net.get(code, 0) + (-delta)
                net[res] = net.get(res, 0) - (-delta)
                bt.fee_cost += (-delta) * bt.config.buy_fee
        for code, amt in net.items():
            if amt < -0.5:
                try:
                    bt.sell(code, round(-amt / nav_of(code), 2), date)
                    logger.info(f"  卖 {code} 净额 CNY{-amt:,.0f}")
                except Exception as e:
                    logger.error(f"卖出 {code} 失败: {e}")
        for code, amt in net.items():
            if amt > 0.5:
                try:
                    bt.buy(code, round(amt, 2), date)
                    logger.info(f"  买 {code} 净额 CNY{amt:,.0f}")
                except Exception as e:
                    logger.error(f"买入 {code} 失败: {e}")
        return summary_df
