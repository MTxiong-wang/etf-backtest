# ETF投资组合回测系统

基于 [xalpha](https://github.com/refraction-ray/xalpha) 框架的 ETF 投资组合**再平衡**回测工具。支持多标的按目标比例配置、偏离阈值自动调仓，并提供**配置化多参数扫描**（组合占比 × 调仓阈值 笛卡尔积）与**自包含 HTML 报告**。

## 功能特点

- 多只 ETF 按目标比例配置，持仓偏离阈值自动触发调仓
- 两种再平衡模式：`band`（带状相对，差额由资金池吸收）/ `absolute`（绝对偏离全仓再平衡）
- **配置化扫描**：组合占比 × 调仓阈值 笛卡尔积回测，对比年化 / 夏普 / 最大回撤 / 卡玛等
- **品种级盈利拆解**：每个策略里每个标的的盈利 / 收益率 / 占比 / 市值 / 成本
- **自包含 HTML 报告**（替代图片）：策略总览 + 排名 + 品种盈利矩阵（一键切换「收益率%」↔「盈利万元」）+ 各组合利润发动机
- 场内 ETF（SH/SZ）+ 场外基金（F，真实净值含分红）+ 货币基金（M）混合回测
- 多次回测共享行情缓存，网格扫描时第 2 个组合起大幅提速

## 安装

```bash
pip install xalpha pandas matplotlib
pip install -e .          # 让 examples / run_sweep 等脚本能 import etf_backtest
```

Python ≥ 3.7。

## 快速开始

### 方式一：配置化扫描（推荐）

把持仓和阈值写成 JSON，跑 `run_sweep.py` 一键出对比报告。

**组合配置** `configs/portfolios/balanced.json`（权重会自动归一化，不必和为 1）：
```json
{
  "name": "balanced",
  "reservoir_code": "F006484",
  "etf_list": [
    {"code": "SH510300", "name": "沪深300ETF", "target_ratio": 0.4},
    {"code": "SZ159915", "name": "创业板ETF",  "target_ratio": 0.3},
    {"code": "F006484",  "name": "国开债",     "target_ratio": 0.3}
  ]
}
```

**扫描网格** `configs/sweep.json`：
```json
{
  "start": "2021-07-01", "end": "2026-07-09",
  "initial_capital": 1000000, "monitor_step": 5, "rf": 0.02,
  "benchmark": {"code": "SH510300", "name": "沪深300ETF"},
  "band_ratios": [0.25, 0.5, 0.75],
  "absolute_thresholds": [0.02, 0.05, 0.10]
}
```

**运行**：
```bash
python run_sweep.py
# 输出（写到 output/）：
#   sweep_comparison.csv    策略级指标明细（年化/夏普/回撤/波动/卡玛/调仓）
#   profit_by_holding.csv   策略×标的 盈利明细（盈利/占比/收益率/市值/成本）
#   report.html             自包含 HTML 报告（浏览器直接打开）
```

内置 3 档示例组合：`conservative`（保守）/ `balanced`（平衡）/ `aggressive`（进取），同用 17 标的池。改组合 / 阈值 / 区间直接编辑 `configs/` 下的 JSON 即可，无需改代码。

### 方式二：单组合编程式

```python
import etf_backtest as etfb

config = etfb.ETFPortfolioConfig(
    etf_list=[
        {"code": "SH512100", "name": "中证1000ETF", "target_ratio": 0.4},
        {"code": "SZ159915", "name": "创业板ETF",  "target_ratio": 0.3},
        {"code": "F006484",  "name": "国开债",     "target_ratio": 0.3}
    ],
    start_date="2020-01-01", end_date="2023-12-31",
    initial_capital=100000,
    rebalance_mode="band", band_ratio=0.5, reservoir_code="F006484",
)

backtest = etfb.ETFPortfolioBacktest(config)
backtest.backtest()
backtest.print_report()
```

或跑生产入口（带状再平衡 + 债券资金池，含多策略对比与图表）：
```bash
python run_portfolio.py 2021-07-01 2026-07-09 0.5 100000 5
```

编程式可视化（净值曲线 / 配置变化 / 收益分布 / 策略对比）见 `utils.py` 的 `plot_portfolio_value` / `plot_allocation_history` / `plot_returns_distribution` / `compare_strategies`；玩具示例 `python examples.py`。

## ETF代码格式

- 上交所 ETF：`SH` + 6 位，如 `SH512100`
- 深交所 ETF：`SZ` + 6 位，如 `SZ159915`
- 场外基金：`F` + 6 位，如 `F006484`（走真实净值，含分红）
- 货币基金：`M` + 6 位，如 `M003171`

## 主要参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `etf_list` | 标的配置（code / name / target_ratio） | 必填 |
| `start_date` / `end_date` | 回测区间 (YYYY-MM-DD) | 必填 |
| `initial_capital` | 初始资金 | 100000 |
| `rebalance_mode` | `band` / `absolute` | absolute |
| `rebalance_threshold` | absolute 模式偏离阈值 | 0.02 |
| `band_ratio` | band 模式相对带宽（如 0.5 = ±50%） | 0.5 |
| `reservoir_code` | band 模式资金池代码 | F006484 |
| `monitor_step` | 每隔 N 个交易日检查 / 记录（长区间用 5 提速） | 1 |
| `rf` | 夏普比率的无风险年化利率 | 0.02 |

## 回测指标

期末资产、总收益率、年化收益、最大回撤、年化波动率、夏普比率（无风险利率 `rf`）、卡玛比率、调仓次数。品种级另有：盈利（= 期末市值 − 持有成本，已含分红）、盈利占比、收益率。

## 项目结构

```
etf_backtest/
├── config.py          # 配置类 + JSON 加载器（load_portfolio_file / load_sweep_file / build_config）
├── core.py            # 回测引擎（ETFPortfolioBacktest，子类化 xalpha BTE）
├── data.py            # 场内标的行情获取 / 缓存
├── utils.py           # 净值 / 配置绘图、策略对比
├── report.py          # HTML 报告生成器（generate_report_html）
├── run_portfolio.py   # 单组合生产入口 + 指标计算（compute_metrics）
├── run_sweep.py       # 配置化多参数扫描入口
├── examples.py        # 编程式示例
├── configs/
│   ├── sweep.json              # 扫描网格 + 运行参数
│   └── portfolios/             # 组合持仓（conservative / balanced / aggressive）
└── output/            # 回测产物（CSV + HTML 报告，已 gitignore，不入库）
```

## 注意事项

1. 首次运行需联网，从雪球（SH/SZ）/ 东方财富（F）下载行情。
2. 回测只在 A 股交易日运行；调仓估算 0.5% 赎回费（买入无费）。
3. `monitor_step` 越大越快但对阈值再平衡结果影响很小，长区间建议 5。
4. 输出产物在 `output/`（不入库）；`configs/` 配置入库。
5. 短区间 + 宽阈值时可能不触发再平衡，同一组合各阈值结果会相同——属正常，跑完整区间才会分化。

## 许可证

MIT License
