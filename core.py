# -*- coding: utf-8 -*-
"""
ETF回测系统 - 核心回测引擎
"""

import logging
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

import xalpha as xa
from xalpha.backtest import BTE
from xalpha.universal import vinfo, get_daily
from xalpha.cons import opendate_set

from .config import ETFPortfolioConfig

logger = logging.getLogger(__name__)


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
        trades: ETF交易记录字典 {code: trade对象}
        rebalance_count: 调仓次数统计
    """

    def __init__(
        self,
        config: ETFPortfolioConfig,
        verbose: bool = True,
        monitor_step: int = 1,
        info_cache: Optional[Dict] = None,
        algo_stack: Optional[List] = None
    ):
        """
        初始化回测引擎

        Args:
            config: ETF投资组合配置
            verbose: 是否打印详细信息
            monitor_step: 每隔多少个交易日做一次再平衡检查与净值记录（1=每日）。
                因 summary() 较慢，长区间可用 5（周度）显著提速，对阈值再平衡结果影响很小。
            info_cache: 跨回测实例共享的 info 对象缓存 {code: info}，可选。
                传入同一字典可在多次回测间复用已抓取的标的数据（尤其 F 类场外基金，
                xalpha 默认不缓存、每次构造都重新请求网络）。首轮抓取后写入，后续实例直接复用。
        """
        self.config = config
        self.verbose = verbose
        self.monitor_step = max(1, int(monitor_step))
        self._info_cache = info_cache
        self._algo_stack = algo_stack

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
        self._day_idx = 0
        self._last_date = None
        self.fee_cost = 0.0  # 累积交易成本（赎回费+申购费）。xalpha sell/buy 不扣费，core 自己扣

    def prepare(self):
        """初始化回测环境，建仓买入"""
        # 获取所有标的数据
        for etf_config in self.config.etf_list:
            code = etf_config['code']
            try:
                # 通过 BTE.get_info 按代码前缀自动分发：
                #   SH/SZ -> vinfo（ETF/股票，雪球前复权行情）
                #   F     -> fundinfo（场外基金真实净值，含分红）
                #   M     -> mfundinfo（货币基金）
                # 若共享缓存命中则直接复用，避免重复抓取（尤其 F 类基金）
                if self._info_cache is not None and code in self._info_cache:
                    self.infos[code] = self._info_cache[code]
                else:
                    info = self.get_info(code)
                    self.infos[code] = info
                    if self._info_cache is not None:
                        self._info_cache[code] = info
                # 注：xalpha 的 sell/buy 不扣手续费（shuhui 默认 zero rate，feelabel
                # 只支持固定编码、不支持任意 fee）。赎回/申购费由 core 在 fee_cost 累积，
                # _record_portfolio_status 时从 total 扣除（见 _swap/_execute_rebalance）。

            except Exception as e:
                logger.warning(f"获取 {code} 数据失败: {e}")

        # 标记是否已建仓
        self.is_initialized = False

    def _daily_summary(self, date: pd.Timestamp):
        """构建当日组合快照（mul.summary）。每天只调用一次以避免重复计算。"""
        sys = self.get_current_mul()
        if sys is None:
            return None
        try:
            return sys.summary(date.strftime("%Y-%m-%d"))
        except Exception:
            return None

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

        self._day_idx += 1
        self._last_date = date
        # 每 monitor_step 个交易日做一次检查+记录（提速；对阈值再平衡影响很小）
        if self._day_idx % self.monitor_step != 0:
            return

        # 当日只构建一次组合快照，检查与记录共用
        summary_df = self._daily_summary(date)
        if summary_df is None:
            return

        # 遍历 algo_stack（默认：检查调仓 + 记录），等价原 check→execute→record 流程
        for algo in self._get_algo_stack():
            summary_df = algo.run(self, date, summary_df)
            if summary_df is None:
                return

    def _get_algo_stack(self):
        """返回 algo_stack：用户传入的优先，否则默认 [AlgoRebalance, AlgoRecord]
        （包装现有 _check/_execute/_record，行为与重构前一致）。"""
        if self._algo_stack is not None:
            return self._algo_stack
        from .algos import AlgoRebalance, AlgoRecord
        return [AlgoRebalance(), AlgoRecord()]

    def backtest(self):
        """运行回测；循环结束后补记最后一个交易日，保证末日净值存在。"""
        self.prepare()
        dates = pd.bdate_range(self.start, self.end)
        last = None
        for d in dates:
            if d.strftime("%Y-%m-%d") in opendate_set:
                last = d
                self.run(d)
        # 末日兜底记录（monitor_step>1 时最后一个监控日未必是末日）
        if last is not None and (
            not self.portfolio_history or self.portfolio_history[-1]["date"] != last
        ):
            summary_df = self._daily_summary(last)
            if summary_df is not None:
                self._record_portfolio_status(last, summary_df)

    def _initial_purchase(self, date: pd.Timestamp):
        """
        初始建仓，按目标比例买入各ETF

        Args:
            date: 建仓日期
        """
        if self.verbose:
            logger.info(f"初始建仓: {date.strftime('%Y-%m-%d')} | Initial capital: CNY {self.config.initial_capital:,.2f}")

        for etf_config in self.config.etf_list:
            code = etf_config['code']
            name = etf_config['name']
            target_ratio = etf_config['target_ratio']
            # round 到分：xalpha 会把买入金额小数部分当作“自定义申购费”二进制编码
            # (trade.py: feelabel = frac(100*value))，金额非整时可能触发
            # “自定义申购费必须为正值”断言。规整到分可避免该坑，精度损失可忽略。
            invest_amount = round(self.config.initial_capital * target_ratio, 2)

            try:
                self.buy(code, round(invest_amount, 2), date)
                self.fee_cost += invest_amount * self.config.buy_fee
                if self.verbose:
                    logger.info(f"  买入 {code} ({name}): CNY{invest_amount:,.2f} ({target_ratio:.2%})")
            except Exception as e:
                logger.error(f"买入 {code} 失败: {e}")

    def _check_rebalance_needed(self, date: pd.Timestamp, summary_df) -> bool:
        """
        检查是否需要调仓

        计算当前组合中各ETF的实际比例，与目标比例对比。
        如果任何ETF的偏离度超过阈值，则返回True。

        Args:
            date: 检查日期
            summary_df: 由 _daily_summary 预先构建的当日组合快照

        Returns:
            bool: 是否需要调仓
        """
        if summary_df is None:
            return False

        # 获取总资产
        total_row = summary_df[summary_df["基金名称"] == "总计"]
        if total_row.empty:
            return False

        total_value = total_row["基金现值"].iloc[0]

        if total_value <= 0:
            return False

        # 带状相对再平衡模式
        if getattr(self.config, "rebalance_mode", "absolute") == "band":
            return self._check_band(summary_df, total_value)

        # 检查每个ETF的偏离度
        for etf_config in self.config.etf_list:
            code = etf_config['code']
            target_ratio = etf_config['target_ratio']

            # 获取该ETF的当前市值（get_code 返回 summary 里“基金代码”列的格式）
            etf_rows = summary_df[summary_df["基金代码"] == self.get_code(code)]
            if etf_rows.empty:
                continue

            current_value = etf_rows["基金现值"].iloc[0]
            current_ratio = current_value / total_value

            # 计算偏离度
            deviation = abs(current_ratio - target_ratio)

            if deviation > self.config.rebalance_threshold:
                if self.verbose:
                    logger.info(f"检测到偏离: {code} 目标 {target_ratio:.2%} 当前 {current_ratio:.2%} 偏离 {deviation:.2%} (阈值 {self.config.rebalance_threshold:.2%})")
                return True

        return False

    def _check_band(self, summary_df, total_value: float) -> bool:
        """带状相对再平衡：任一非资金池标的的实际权重落到 target*(1±band) 之外即触发。"""
        band = self.config.band_ratio
        res = self.config.reservoir_code
        for etf_config in self.config.etf_list:
            code = etf_config["code"]
            target = etf_config["target_ratio"]
            if code == res:
                continue  # 资金池本身不设带
            rows = summary_df[summary_df["基金代码"] == self.get_code(code)]
            if rows.empty:
                continue
            ratio = rows["基金现值"].iloc[0] / total_value
            lo, hi = target * (1 - band), target * (1 + band)
            if ratio < lo or ratio > hi:
                if self.verbose:
                    logger.info(f"触发带状调仓: {code} 目标 {target:.2%} 当前 {ratio:.2%} (带宽 [{lo:.2%}, {hi:.2%}])")
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
            logger.info(f"执行调仓 #{self.rebalance_count}: {date.strftime('%Y-%m-%d')}")

        # 获取当前组合
        sys = self.get_current_mul()
        summary_df = sys.summary(date.strftime("%Y-%m-%d"))

        # 获取总资产
        total_value = summary_df[summary_df["基金名称"] == "总计"]["基金现值"].iloc[0]

        # 带状相对再平衡模式
        if getattr(self.config, "rebalance_mode", "absolute") == "band":
            self._execute_band(date, summary_df, total_value)
            return

        # 对每个ETF进行调仓
        for etf_config in self.config.etf_list:
            code = etf_config['code']
            name = etf_config['name']
            target_ratio = etf_config['target_ratio']
            target_value = total_value * target_ratio

            # 获取当前持仓
            etf_rows = summary_df[summary_df["基金代码"] == self.get_code(code)]
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
                    # 卖出超配部分（净额，赎回费在 fee_cost 累积）
                    sell_nav = current_nav if current_nav > 0 else 1
                    sell_share = round(delta / sell_nav, 2)
                    self.sell(code, sell_share, date)
                    self.fee_cost += delta * self.config.redeem_fee

                    if self.verbose:
                        logger.info(f"  卖出 {code} ({name}): {sell_share} 份, 约 CNY{delta:,.2f}")
                else:
                    # 买入低配部分（净额，申购费在 fee_cost 累积）
                    buy_amount = round(abs(delta), 2)
                    self.buy(code, buy_amount, date)
                    self.fee_cost += buy_amount * self.config.buy_fee

                    if self.verbose:
                        logger.info(f"  买入 {code} ({name}): CNY{buy_amount:,.2f}")
            except Exception as e:
                logger.error(f"调仓 {code} 失败: {e}")

    def _execute_band(self, date, summary_df, total_value):
        """带状再平衡：把落到带外的标的拉回目标权重，差额与资金池(reservoir_code)互兑。"""
        band = self.config.band_ratio
        res = self.config.reservoir_code

        def nav_of(code):
            rows = summary_df[summary_df["基金代码"] == self.get_code(code)]
            if rows.empty:
                return 1.0
            v = rows.get("当日净值", pd.Series([0])).iloc[0]
            return v if v and v > 0 else 1.0

        triggers = []  # (code, name, delta): delta>0 超配(卖出), delta<0 低配(买入)
        for etf_config in self.config.etf_list:
            code = etf_config["code"]
            if code == res:
                continue  # 资金池不调
            target = etf_config["target_ratio"]
            rows = summary_df[summary_df["基金代码"] == self.get_code(code)]
            if rows.empty:
                continue
            cur = rows["基金现值"].iloc[0]
            ratio = cur / total_value
            lo, hi = target * (1 - band), target * (1 + band)
            if lo <= ratio <= hi:
                continue  # 带内不动
            delta = cur - total_value * target
            if abs(delta) < 1:
                continue
            triggers.append((code, etf_config["name"], delta))

        # 净额合并：累加每个标的的净流，每标的当天只发一笔（避免资金池同日多笔被
        # xalpha trade 丢弃→低配买入已入账但资金池卖出没记账→组合现值凭空虚增）。
        net = {}  # code -> 净流（正=买入金额，负=卖出金额）
        for code, name, delta in triggers:
            if delta > 0:  # 超配：卖 code、资金池买
                net[code] = net.get(code, 0) - delta
                net[res] = net.get(res, 0) + delta
                self.fee_cost += delta * self.config.redeem_fee
            else:  # 低配：买 code、资金池卖
                net[code] = net.get(code, 0) + (-delta)
                net[res] = net.get(res, 0) - (-delta)
                self.fee_cost += (-delta) * self.config.buy_fee
        # 每个标的只发一笔净额（先卖 net<0 再买 net>0，降低资金池瞬时缺口）
        for code, amt in net.items():
            if amt < -0.5:
                try:
                    self.sell(code, round(-amt / nav_of(code), 2), date)
                    if self.verbose:
                        logger.info(f"  卖 {code} 净额 CNY{-amt:,.0f}")
                except Exception as e:
                    logger.error(f"卖出 {code} 失败: {e}")
        for code, amt in net.items():
            if amt > 0.5:
                try:
                    self.buy(code, round(amt, 2), date)
                    if self.verbose:
                        logger.info(f"  买 {code} 净额 CNY{amt:,.0f}")
                except Exception as e:
                    logger.error(f"买入 {code} 失败: {e}")

    def _swap(self, from_code, to_code, value, date, from_nav):
        """卖出 value(净额) 的 from_code，买入 value 的 to_code；赎回费/申购费在 fee_cost 累积。"""
        # xalpha 不扣手续费，core 在 fee_cost 累积、_record 时从 total 扣
        sell_share = round(value / from_nav, 2)
        self.sell(from_code, sell_share, date)
        self.fee_cost += value * self.config.redeem_fee
        self.buy(to_code, round(value, 2), date)
        self.fee_cost += value * self.config.buy_fee

    def _record_portfolio_status(self, date: pd.Timestamp, summary_df):
        """
        记录当前组合状态

        Args:
            date: 记录日期
            summary_df: 由 _daily_summary 预先构建的当日组合快照
        """
        if summary_df is None:
            return

        try:
            total_value = summary_df[summary_df["基金名称"] == "总计"]["基金现值"].iloc[0]
            # 扣除累积交易成本（xalpha 不扣费，core 在 fee_cost 累积后这里扣除）
            total_value = total_value - self.fee_cost

            status = {
                'date': date,
                'total_value': total_value
            }

            for etf_config in self.config.etf_list:
                code = etf_config['code']
                etf_rows = summary_df[summary_df["基金代码"] == self.get_code(code)]
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
