# -*- coding: utf-8 -*-
"""
持仓计划回测入口

用法:
    python run_portfolio.py [start] [end] [threshold] [initial_capital]

示例:
    python run_portfolio.py 2021-07-01 2026-07-09 0.05 100000

说明:
    - 场内 ETF (SH/SZ) 走雪球前复权行情；场外基金 (F) 走真实净值（含分红）。
    - 红利 SH563020 (2023-12 才上市) 用 SH512890 中证红利低波ETF 替代；
      中证A500 指数 932224 免费接口取不到，其 2.4% 已并入沪深300 (SH510300 -> 7.2%)。
    - 成本：沿用引擎内置的 0.5% 赎回费估算（粗略，买入无费）。
"""

import sys
import os

# 无显示环境，强制非交互后端
import matplotlib
matplotlib.use("Agg")

# 让 `import etf_backtest` 在任意 cwd 下可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from etf_backtest.config import ETFPortfolioConfig, load_portfolio_file, load_sweep_file, _DEFAULT_RESERVOIR
from etf_backtest.core import ETFPortfolioBacktest
from etf_backtest.utils import (
    plot_portfolio_value,
    plot_allocation_history,
    plot_returns_distribution,
    compare_strategies,
)

logger = logging.getLogger(__name__)


# 默认组合/扫描配置路径（持仓不再硬编码，改读 configs/portfolios/balanced.json）
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PORTFOLIO_FILE = os.path.join(_HERE, "configs", "portfolios", "balanced.json")
_DEFAULT_SWEEP_FILE = os.path.join(_HERE, "configs", "sweep.json")


def _load_default_portfolio():
    """读取默认组合（balanced.json），返回 (etf_list, reservoir_code)。"""
    p = load_portfolio_file(_DEFAULT_PORTFOLIO_FILE)
    return p["etf_list"], p.get("reservoir_code") or _DEFAULT_RESERVOIR


def _load_default_sweep():
    """读取默认扫描配置（sweep.json）作 main 的参数默认来源。"""
    return load_sweep_file(_DEFAULT_SWEEP_FILE)


def run_config(config, verbose=False, monitor_step=5, info_cache=None):
    """通用回测入口：接收已构造的 ETFPortfolioConfig，运行 prepare()+backtest()，返回引擎实例。

    模式无关（band/absolute 由 config 携带）。info_cache 可在多次回测间共享
    已抓取的标的数据（尤其 F 类场外基金），显著减少网格扫描时的网络请求。
    """
    bt = ETFPortfolioBacktest(config, verbose=verbose, monitor_step=monitor_step,
                              info_cache=info_cache)
    bt.prepare()
    bt.backtest()
    return bt


def run_one(start, end, band_ratio, initial_capital, etf_list, reservoir,
            verbose=False, monitor_step=5, info_cache=None,
            redeem_fee=0.005, buy_fee=0.0):
    """带状相对再平衡：band_ratio=0.5 表示±50%带宽；资金池 reservoir 吸收差额。
    band_ratio=10 等极大值 => 永不触发 => 买入持有。持仓 etf_list/reservoir 由调用方
    传入（main 从 configs/portfolios/*.json 读，不再用模块级 PORTFOLIO）。"""
    cfg = ETFPortfolioConfig(
        etf_list=[dict(x) for x in etf_list],
        start_date=start,
        end_date=end,
        initial_capital=initial_capital,
        rebalance_mode="band",
        band_ratio=band_ratio,
        reservoir_code=reservoir,
        redeem_fee=redeem_fee,
        buy_fee=buy_fee,
    )
    return run_config(cfg, verbose=verbose, monitor_step=monitor_step, info_cache=info_cache)


def save_history_csv(bt, path):
    import pandas as pd
    # 代码列取自 bt 自身配置，而非模块级 PORTFOLIO（否则换组合时列会错）
    codes = [e["code"] for e in bt.config.etf_list]
    rows = []
    for st in bt.portfolio_history:
        r = {"date": st["date"], "total_value": st["total_value"]}
        for c in codes:
            r[c] = st.get(c, {}).get("value", None) if isinstance(st.get(c), dict) else None
        rows.append(r)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def cfg_codes():
    etf_list, _ = _load_default_portfolio()
    return [x["code"] for x in etf_list]


def compute_metrics(history, initial_capital, rf=0.02):
    """基于净值序列直接计算核心指标（不依赖 xalpha 的 mulfix/xirr）。

    rf 为夏普比率的无风险年化利率，默认 2%。
    """
    import pandas as pd
    import numpy as np

    if not history:
        return {}
    df = pd.DataFrame([{"date": h["date"], "value": h["total_value"]} for h in history])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    final = float(df["value"].iloc[-1])
    total_return = final / initial_capital - 1
    years = (df["date"].iloc[-1] - df["date"].iloc[0]).days / 365.25
    annualized = (final / initial_capital) ** (1 / years) - 1 if years > 0 else 0.0

    cummax = df["value"].cummax()
    dd = (df["value"] - cummax) / cummax
    max_dd = float(dd.min())  # 负值

    rets = df["value"].pct_change().dropna()
    periods_per_year = len(df) / years if years > 0 else 252
    vol = float(rets.std() * np.sqrt(periods_per_year)) if len(rets) > 1 else 0.0
    sharpe = (annualized - rf) / vol if vol > 0 else 0.0
    calmar = annualized / abs(max_dd) if max_dd < 0 else 0.0

    # 扩展风险/收益指标（借鉴主流框架）
    downside = rets[rets < 0]
    downside_vol = float(downside.std() * np.sqrt(periods_per_year)) if len(downside) > 1 else 0.0
    sortino = (annualized - rf) / downside_vol if downside_vol > 0 else 0.0
    var_95 = float(rets.quantile(0.05)) if len(rets) > 0 else 0.0
    tail = rets[rets <= var_95]
    cvar_95 = float(tail.mean()) if len(tail) > 0 else var_95
    win_rate = float((rets > 0).sum() / len(rets)) if len(rets) > 0 else 0.0
    gains = rets[rets > 0]
    losses = rets[rets < 0]
    profit_loss_ratio = float(gains.mean() / abs(losses.mean())) if len(losses) > 0 and losses.mean() != 0 else 0.0

    return {
        "final": final,
        "total_return": total_return,
        "annualized": annualized,
        "max_drawdown": max_dd,
        "volatility": vol,
        "sharpe": sharpe,
        "calmar": calmar,
        "years": years,
        "sortino": sortino,
        "var_95": var_95,
        "cvar_95": cvar_95,
        "win_rate": win_rate,
        "profit_loss_ratio": profit_loss_ratio,
    }


def make_report(metrics, rebalance_count):
    """从 compute_metrics 的结果构造 compare_strategies 所需的精简报告字典，
    避开 xalpha mulfix 在发生赎回后可能抛 'initial total cash too low' 的问题。"""
    return {"results": {
        "total_return": metrics["total_return"],
        "annualized_return": metrics["annualized"],
        "max_drawdown": metrics["max_drawdown"],
        "rebalance_count": rebalance_count,
    }}


def print_report_block(title, metrics, rebalance_count, initial_capital):
    """打印单个策略的核心指标。"""
    print("=" * 56)
    print(title)
    print("-" * 56)
    print(f"  期末资产     CNY {metrics['final']:>12,.2f}")
    print(f"  累计收益率        {metrics['total_return']:>11.2%}")
    print(f"  年化收益率        {metrics['annualized']:>11.2%}   (区间 {metrics['years']:.2f} 年)")
    print(f"  年化波动率        {metrics['volatility']:>11.2%}")
    print(f"  最大回撤          {metrics['max_drawdown']:>11.2%}")
    print(f"  夏普比率(无风险2%) {metrics['sharpe']:>10.2f}")
    print(f"  卡玛比率          {metrics['calmar']:>11.2f}")
    print(f"  索提诺比率        {metrics['sortino']:>11.2f}")
    print(f"  胜率              {metrics['win_rate']:>11.2%}")
    print(f"  盈亏比            {metrics['profit_loss_ratio']:>11.2f}")
    print(f"  VaR(95%,日)       {metrics['var_95']:>11.2%}")
    print(f"  CVaR(95%,日)      {metrics['cvar_95']:>11.2%}")
    print(f"  再平衡次数        {rebalance_count:>11d}")
    print("=" * 56)


def print_comparison_table(rows):
    """rows: list of (label, metrics, rebalance_count)"""
    print("\n" + "=" * 86)
    print("策略对比")
    print("-" * 86)
    print(f"{'策略':<16}{'年化收益':>10}{'年化波动':>10}{'最大回撤':>10}{'夏普':>8}{'卡玛':>8}{'调仓':>6}")
    print("-" * 86)
    for label, m, n in rows:
        print(f"{label:<16}{m['annualized']:>10.2%}{m['volatility']:>10.2%}"
              f"{m['max_drawdown']:>10.2%}{m['sharpe']:>8.2f}{m['calmar']:>8.2f}{n:>6d}")
    print("=" * 86)


def main():
    # 默认参数从 configs/sweep.json + configs/portfolios/balanced.json 读，sys.argv 可覆盖
    sweep = _load_default_sweep()
    etf_list, reservoir = _load_default_portfolio()
    start = sys.argv[1] if len(sys.argv) > 1 else sweep["start"]
    end = sys.argv[2] if len(sys.argv) > 2 else sweep["end"]
    band = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5    # 相对带宽，0.5=±50%
    capital = float(sys.argv[4]) if len(sys.argv) > 4 else sweep["initial_capital"]
    step = int(sys.argv[5]) if len(sys.argv) > 5 else int(sweep.get("monitor_step", 5))
    rf = float(sweep.get("rf", 0.02))
    redeem_fee = float(sweep.get("redeem_fee", 0.005))
    buy_fee = float(sweep.get("buy_fee", 0.0))

    out_dir = os.path.join(_HERE, "output")
    os.makedirs(out_dir, exist_ok=True)

    import time
    logger.info(f"回测区间 {start} ~ {end} | 带状再平衡 带宽±{band:.0%} | 资金池 {reservoir} | 初始资金 {capital:,.0f}")
    logger.info("正在获取数据并回测，请稍候 ...")

    # 主回测：带状相对再平衡
    t0 = time.time()
    bt = run_one(start, end, band, capital, etf_list, reservoir,
                 monitor_step=step, redeem_fee=redeem_fee, buy_fee=buy_fee)
    logger.info(f"主回测完成，用时 {time.time()-t0:.0f}s")
    main_metrics = compute_metrics(bt.portfolio_history, capital, rf=rf)
    print_report_block(f"主策略：带状±{band:.0%}再平衡（资金池{reservoir}）",
                       main_metrics, bt.rebalance_count, capital)

    # 保存净值历史与图表
    save_history_csv(bt, os.path.join(out_dir, "portfolio_history.csv"))
    plot_portfolio_value(bt.portfolio_history, bt.rebalance_dates,
                         save_path=os.path.join(out_dir, "01_portfolio_value.png"))
    plot_allocation_history(bt.portfolio_history, bt.config.etf_list,
                            save_path=os.path.join(out_dir, "02_allocation_history.png"))
    plot_returns_distribution(bt.portfolio_history,
                              save_path=os.path.join(out_dir, "03_returns_distribution.png"))

    # 策略对比：带宽±50% / 带宽±25% / 买入持有 / 基准
    logger.info("正在生成策略对比 ...")
    reports, labels, rows = [], [], []
    reports.append(make_report(main_metrics, bt.rebalance_count)); labels.append(f"带宽±{band:.0%}")
    rows.append((f"带宽±{band:.0%}", main_metrics, bt.rebalance_count))
    if abs(band - 0.25) > 1e-6:
        bt2 = run_one(start, end, 0.25, capital, etf_list, reservoir,
                      monitor_step=step, redeem_fee=redeem_fee, buy_fee=buy_fee)
        m2 = compute_metrics(bt2.portfolio_history, capital, rf=rf)
        reports.append(make_report(m2, bt2.rebalance_count)); labels.append("带宽±25%")
        rows.append(("带宽±25%", m2, bt2.rebalance_count))
    bt3 = run_one(start, end, 10.0, capital, etf_list, reservoir,
                  monitor_step=step, redeem_fee=redeem_fee, buy_fee=buy_fee)  # 极宽带 => 买入持有
    m3 = compute_metrics(bt3.portfolio_history, capital, rf=rf)
    reports.append(make_report(m3, bt3.rebalance_count)); labels.append("买入持有")
    rows.append(("买入持有", m3, bt3.rebalance_count))
    # 基准：单标的 100%（从 sweep.json 的 benchmark 读）
    bench = sweep["benchmark"]
    bench_cfg = ETFPortfolioConfig(
        etf_list=[{"code": bench["code"], "name": bench["name"], "target_ratio": 1.0}],
        start_date=start, end_date=end, initial_capital=capital, rebalance_threshold=1.0,
        redeem_fee=redeem_fee, buy_fee=buy_fee,
    )
    btb = ETFPortfolioBacktest(bench_cfg, verbose=False, monitor_step=step)
    btb.prepare(); btb.backtest()
    mb = compute_metrics(btb.portfolio_history, capital, rf=rf)
    reports.append(make_report(mb, btb.rebalance_count)); labels.append(bench["name"] + "基准")
    rows.append((bench["name"] + "基准", mb, btb.rebalance_count))

    compare_strategies(reports, labels, save_path=os.path.join(out_dir, "04_compare_strategies.png"))
    print_comparison_table(rows)

    # 资金池期末实际权重（观察其作为缓冲的漂移）
    final_status = bt.portfolio_history[-1] if bt.portfolio_history else {}
    res_val = final_status.get(reservoir, {})
    if isinstance(res_val, dict):
        target = bt.config.portfolio_dict.get(reservoir, 0)
        logger.info(f"资金池 {reservoir} 期末实际权重: {res_val.get('ratio', 0):.2%} (目标 {target:.2%})")

    logger.info(f"所有结果已保存到: {out_dir}")


if __name__ == "__main__":
    main()
