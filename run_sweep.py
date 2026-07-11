# -*- coding: utf-8 -*-
"""
配置化多参数回测扫描入口

用法:
    python run_sweep.py [sweep.json] [portfolios_dir]

示例:
    python run_sweep.py
    python run_sweep.py configs/sweep.json configs/portfolios

说明:
    - 读取 configs/sweep.json（扫描网格 + 运行参数）与 configs/portfolios/*.json（组合持仓）。
    - 对每个组合 × (band_ratios + absolute_thresholds) 做笛卡尔积回测。
    - 跨所有回测共享同一份 info_cache：首轮抓取后所有组合复用已缓存的标的数据，
      避免 F 类场外基金在每次回测都重复请求东方财富（xalpha 默认不缓存 fundinfo）。
    - 输出 output/sweep_comparison.csv（每个组合×阈值的完整指标明细）。
    - 输出 output/profit_by_holding.csv（每个策略×每个标的 的盈利/收益率/市值/成本）。
    - 输出 output/report.html（自包含 HTML 报告：策略总览 + 排名 + 品种盈利矩阵可切换
      收益率/盈利 + 利润发动机，替代 PNG）。
"""

import sys
import os
import glob
import time

# 让 `import etf_backtest` 与 `from run_portfolio import ...` 在任意 cwd 下可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etf_backtest.config import load_portfolio_file, load_sweep_file, build_config
from etf_backtest.report import generate_report_html
from run_portfolio import run_config, compute_metrics


CSV_COLUMNS = [
    "portfolio", "mode", "threshold", "final", "total_return",
    "annualized", "max_drawdown", "volatility", "sharpe", "calmar",
    "sortino", "win_rate", "profit_loss_ratio", "var_95", "cvar_95",
    "rebalance_count",
]


def fmt_threshold(mode, thr):
    """阈值的人类可读串：band 用 ±，absolute 用原值。"""
    return f"±{thr:g}" if mode == "band" else f"{thr:g}"


def build_grid(sweep, portfolios):
    """生成 (portfolio_name, mode, thr_value, ETFPortfolioConfig) 列表。"""
    start, end = sweep["start"], sweep["end"]
    capital = sweep["initial_capital"]
    redeem_fee = float(sweep.get("redeem_fee", 0.005))
    buy_fee = float(sweep.get("buy_fee", 0.0))
    grid = []
    for p in portfolios:
        for b in sweep.get("band_ratios", []):
            cfg = build_config(
                etf_list=p["etf_list"], start=start, end=end, capital=capital,
                mode="band", band_ratio=b, reservoir=p.get("reservoir_code"),
                redeem_fee=redeem_fee, buy_fee=buy_fee,
            )
            grid.append((p["name"], "band", b, cfg))
        for t in sweep.get("absolute_thresholds", []):
            cfg = build_config(
                etf_list=p["etf_list"], start=start, end=end, capital=capital,
                mode="absolute", threshold=t,
                redeem_fee=redeem_fee, buy_fee=buy_fee,
            )
            grid.append((p["name"], "absolute", t, cfg))
    return grid


def run_benchmark(sweep, monitor_step, info_cache):
    """单标的 100% 买入持有基准（absolute + 阈值1.0 => 永不触发 => 买入持有）。"""
    bench = sweep["benchmark"]
    cfg = build_config(
        etf_list=[{"code": bench["code"], "name": bench["name"], "target_ratio": 1.0}],
        start=sweep["start"], end=sweep["end"], capital=sweep["initial_capital"],
        mode="absolute", threshold=1.0,
        redeem_fee=float(sweep.get("redeem_fee", 0.005)),
        buy_fee=float(sweep.get("buy_fee", 0.0)),
    )
    return run_config(cfg, verbose=False, monitor_step=monitor_step, info_cache=info_cache)


def metrics_to_row(pname, mode, thr, metrics, rebalance_count):
    return {
        "portfolio": pname, "mode": mode, "threshold": fmt_threshold(mode, thr),
        "final": metrics.get("final"), "total_return": metrics.get("total_return"),
        "annualized": metrics.get("annualized"), "max_drawdown": metrics.get("max_drawdown"),
        "volatility": metrics.get("volatility"), "sharpe": metrics.get("sharpe"),
        "calmar": metrics.get("calmar"),
        "sortino": metrics.get("sortino"), "win_rate": metrics.get("win_rate"),
        "profit_loss_ratio": metrics.get("profit_loss_ratio"),
        "var_95": metrics.get("var_95"), "cvar_95": metrics.get("cvar_95"),
        "rebalance_count": rebalance_count,
    }


def capture_holding_profit(bt, end, summary_to_canon):
    """从回测期末 summary 提取每个标的的盈利/市值/成本/收益率。

    xalpha 的 summary 列：基金收益总额(=现值-持有成本，已含分红)、基金现值、
    基金持有成本、投资收益率。F 类基金在 summary 里是 6 位代码（无 F 前缀），
    用 summary_to_canon 映射回配置里的规范代码。失败（如 summary 不可用）返回 {}。
    """
    try:
        sdf = bt.get_current_mul().summary(end)
    except Exception:
        return {}
    out = {}
    for _, r in sdf[sdf["基金名称"] != "总计"].iterrows():
        ccode = summary_to_canon.get(r["基金代码"], r["基金代码"])
        out[ccode] = {
            "profit": float(r["基金收益总额"]),
            "value": float(r["基金现值"]),
            "cost": float(r["基金持有成本"]),
            "return_pct": float(r["投资收益率"]),
        }
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sweep_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "configs", "sweep.json")
    portfolios_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "configs", "portfolios")

    sweep = load_sweep_file(sweep_path)
    rf = float(sweep.get("rf", 0.02))
    monitor_step = int(sweep.get("monitor_step", 5))
    capital = sweep["initial_capital"]

    # 加载所有组合（按文件名排序，保证行列顺序稳定）
    portfolio_files = sorted(glob.glob(os.path.join(portfolios_dir, "*.json")))
    if not portfolio_files:
        print(f"未在 {portfolios_dir} 找到组合配置 (*.json)")
        sys.exit(1)
    portfolios = [load_portfolio_file(p) for p in portfolio_files]

    # 标的代码/名称规范化（所有组合共用同一标的池）
    name_by_code = {}
    summary_to_canon = {}
    for p in portfolios:
        for e in p["etf_list"]:
            c = e["code"]
            name_by_code.setdefault(c, e["name"])
            # xalpha summary 里 F/M 基金代码是 6 位数字（无前缀），需映射回规范代码
            summary_to_canon[c[1:] if c[:1] in "FM" else c] = c
    holdings_order = list(name_by_code.keys())

    grid = build_grid(sweep, portfolios)
    n_band = len(sweep.get("band_ratios", []))
    n_abs = len(sweep.get("absolute_thresholds", []))
    print(f"扫描网格: {len(portfolios)} 组合 × ({n_band} band + {n_abs} absolute) "
          f"= {len(grid)} 回测 + 1 基准")
    print(f"区间 {sweep['start']} ~ {sweep['end']} | monitor_step={monitor_step} | "
          f"rf={rf} | 初始资金 {capital:,.0f}")
    print("正在抓取数据并回测，首轮较慢（之后命中缓存）...\n")

    info_cache = {}  # 跨所有回测共享的标的数据缓存
    rows = []
    per_strategy = {}  # (portfolio, mode, thr) -> {canonical_code: 标的级盈利指标}
    t0 = time.time()

    for i, (pname, mode, thr, cfg) in enumerate(grid, 1):
        ts = time.time()
        bt = run_config(cfg, verbose=False, monitor_step=monitor_step, info_cache=info_cache)
        m = compute_metrics(bt.portfolio_history, capital, rf=rf)
        rows.append(metrics_to_row(pname, mode, thr, m, bt.rebalance_count))
        per_strategy[(pname, mode, thr)] = capture_holding_profit(bt, sweep["end"], summary_to_canon)
        print(f"  [{i}/{len(grid)}] {pname:<13}{mode}{fmt_threshold(mode, thr):>6}  "
              f"年化={m.get('annualized', 0):.2%}  夏普={m.get('sharpe', 0):.2f}  "
              f"回撤={m.get('max_drawdown', 0):.2%}  调仓={bt.rebalance_count}  "
              f"({time.time() - ts:.0f}s)")

    # 基准：单标的买入持有
    bt_b = run_benchmark(sweep, monitor_step, info_cache)
    mb = compute_metrics(bt_b.portfolio_history, capital, rf=rf)
    bench_label = f"基准({sweep['benchmark']['name']})"
    rows.append(metrics_to_row(bench_label, "buy_hold", 0.0, mb, bt_b.rebalance_count))
    rows[-1]["threshold"] = "-"
    print(f"\n{bench_label}: 年化={mb.get('annualized', 0):.2%}  夏普={mb.get('sharpe', 0):.2f}")
    print(f"扫描完成，用时 {time.time() - t0:.0f}s（含基准）\n")

    # 输出
    out_dir = os.path.join(here, "output")
    os.makedirs(out_dir, exist_ok=True)

    import pandas as pd
    csv_path = os.path.join(out_dir, "sweep_comparison.csv")
    pd.DataFrame(rows, columns=CSV_COLUMNS).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"明细已保存至: {csv_path}")

    band_thrs = sweep.get("band_ratios", [])
    abs_thrs = sweep.get("absolute_thresholds", [])

    # —— 品种盈利拆解 CSV ——
    holding_rows = []
    for (pname, mode, thr), ph in per_strategy.items():
        total_profit = sum(h["profit"] for h in ph.values())
        for ccode, h in ph.items():
            holding_rows.append({
                "portfolio": pname, "mode": mode, "threshold": fmt_threshold(mode, thr),
                "holding": ccode, "holding_name": name_by_code.get(ccode, ccode),
                "profit": h["profit"],
                "profit_share_pct": (h["profit"] / total_profit * 100) if total_profit > 0 else None,
                "return_pct": h["return_pct"],
                "final_value": h["value"], "cost": h["cost"],
            })
    holding_csv = os.path.join(out_dir, "profit_by_holding.csv")
    pd.DataFrame(holding_rows, columns=[
        "portfolio", "mode", "threshold", "holding", "holding_name",
        "profit", "profit_share_pct", "return_pct", "final_value", "cost",
    ]).to_csv(holding_csv, index=False, encoding="utf-8-sig")
    print(f"品种盈利明细已保存至: {holding_csv}")

    # —— HTML 报告（自包含，替代 PNG；品种矩阵可切换 收益率/盈利 视图）——
    report_path = os.path.join(out_dir, "report.html")
    generate_report_html(
        params={
            "start": sweep["start"], "end": sweep["end"],
            "initial_capital": capital, "rf": rf, "monitor_step": monitor_step,
            "benchmark_name": sweep["benchmark"]["name"],
            "band_ratios": band_thrs, "absolute_thresholds": abs_thrs,
        },
        strategies=rows,
        per_strategy=per_strategy,
        name_by_code=name_by_code,
        holdings_order=holdings_order,
        save_path=report_path,
    )

    print(f"\n所有结果已保存到: {out_dir}")


if __name__ == "__main__":
    main()
