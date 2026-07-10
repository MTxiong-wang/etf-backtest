# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 [xalpha](https://github.com/refraction-ray/xalpha) 框架的 A 股 ETF 投资组合**再平衡**回测工具。核心是把 `xalpha.backtest.BTE` 子类化，在每日回测循环里检测持仓偏离并自动调仓。包以扁平模块布局组织，通过 `import etf_backtest` 导入（需先 editable 安装）。

## 常用命令

依赖：`xalpha>=0.12.0`、`pandas`、`matplotlib`，Python ≥ 3.7。

```bash
# 安装（在项目根目录下，editable 模式让 examples/test 脚本能 import etf_backtest）
pip install -e .

# 生产入口：跑 run_portfolio.py 里的真实 17 标的组合（带状再平衡 + 债券资金池）
# 参数顺序: start end band capital step
python run_portfolio.py                       # 默认 2021-07-01 2026-07-09 0.5 100000 5
python run_portfolio.py 2021-07-01 2026-07-09 0.25 100000 5

# 配置化多参数扫描：读 configs/，对 组合×阈值 笛卡尔积回测，出 CSV + HTML 报告
python run_sweep.py                            # 用 configs/sweep.json + configs/portfolios/*.json
python run_sweep.py configs/sweep.json configs/portfolios   # 可指定路径

# 玩具示例（3 只 ETF，绝对阈值再平衡）
python examples.py
```

### 关于“测试”

**本仓库没有 pytest 套件**，也没有正式测试框架。`test_basic.py` / `test_backtest.py` / `run_test.py` 是带 `print` 的冒烟脚本，且：

- 脚本里硬编码了 `sys.path.insert(0, 'D:/Codes')`，换机器/路径需手改；
- 依赖联网拉取真实行情数据，离线跑不动；
- `test_*.py` 被 `.gitignore` 忽略（见下）。

直接当脚本运行即可：`python test_basic.py`、`python test_backtest.py`、`python run_test.py`。不要假设 `pytest` 能收集它们。

## 架构要点

### 模块分工

- `config.py` — `ETFPortfolioConfig`：校验 + 归一化比例，持有 `portfolio_dict`（code→target_ratio）。`validate_etf_code` 限定代码格式为 `^(SH|SZ|F|M)\d{6}$`。另有 JSON 加载器 `load_portfolio_file` / `load_sweep_file` / `build_config`（不改类，仅把 JSON 映射成 `ETFPortfolioConfig`）。
- `data.py` — `ETFDataManager`：仅负责 **SH/SZ 场内标的** 的行情获取与缓存（`xalpha.universal.get_daily`）。F/M 场外基金不走这里。
- `core.py` — `ETFPortfolioBacktest(BTE)`：回测引擎，子类化 `xalpha.backtest.BTE`。`__init__` 支持传入共享 `info_cache`（见下文“F 类基金不缓存”）。
- `utils.py` — 绘图（`plot_portfolio_value` 等净值/配置图、`compare_strategies`）与 `format_report`；顶部设中文字体。另有 `plot_sweep_heatmap` / `plot_holding_heatmap`（旧版 PNG 热力图，已被 HTML 报告取代，保留备用）。
- `run_portfolio.py` — 真实组合的 CLI 入口与指标计算（见下文“两套报告路径”）。通用回测入口 `run_config(config, ...)` 也在这里。
- `run_sweep.py` — 配置化多参数扫描入口（见下文“配置化多参数扫描”）。
- `report.py` — `generate_report_html`：把扫描结果渲染成自包含 HTML 报告（替代 PNG）。

### 回测循环（`core.py`）

`backtest()` 遍历 `pd.bdate_range(start, end)`，仅对落在 `xalpha.cons.opendate_set` 里的 A 股交易日调用 `run(date)`。`run()` 首日建仓，之后每隔 `monitor_step` 个交易日做一次“检查+记录”。`sys.summary()` 很慢，长区间用 `monitor_step=5`（周度）可大幅提速且对阈值再平衡结果影响很小；`backtest()` 末尾有兜底逻辑保证末日净值被记录。

`ETFPortfolioBacktest` 复用了 BTE 的 `buy/sell/get_info/get_current_mul/get_current_mulfix/get_code` 等方法，不要重写这些底层接口。

### 两种再平衡模式（`rebalance_mode`）

1. **`"absolute"`**（默认）：任一标的实际权重偏离目标超过 `rebalance_threshold`（绝对百分点）即触发**全仓再平衡**，把所有标的拉回目标权重（`_execute_rebalance`）。
2. **`"band"`**：带状相对再平衡。只有落到 `target*(1±band_ratio)` 带外的标的被拉回目标，**差额由 `reservoir_code`（资金池，通常是债券基金）吸收**，资金池自身不设带（`_execute_band` + `_swap`）。`band_ratio` 取极大值（如 `run_portfolio.py` 里用 `10.0`）等价于永不触发 = 买入持有。

成本模型：卖出含 **0.5% 赎回费**估算（`fee = 0.005` 硬编码在 `_execute_rebalance` / `_swap`），买入无费。`_swap` 先卖超配、后买低配以降低资金池瞬时缺口。

### 代码前缀决定数据来源

`BTE.get_info` 按代码前缀自动分发，这是 F/M 标的不走 `data.py` 的原因：

- `SH/SZ` → `vinfo`（雪球前复权行情）
- `F` → `fundinfo`（场外基金真实净值，含分红）
- `M` → `mfundinfo`（货币基金）

`prepare()` 对 SH/SZ 会先用 `data_manager` 取数据并做空值检查，F/M 直接交给 `get_info`。

### 两套报告路径（最关键的非显然点）

`core.generate_report()` / `print_report()` 依赖 xalpha 的 `get_current_mulfix()` + `xirrrate()` + `summary()`。**发生赎回后这些接口可能抛 `initial total cash too low`**，不可靠。

因此 `run_portfolio.py` **刻意绕开** `generate_report()`，改用自带 `compute_metrics(history, initial_capital, rf=0.02)` 直接从 `portfolio_history` 净值序列算指标：总收益、年化、最大回撤、年化波动率、夏普（无风险利率 `rf`，默认 0.02）、卡玛。`make_report()` 把结果包装成 `compare_strategies` 能吃的精简字典——**但它只留 4 个字段、丢掉 sharpe/calmar/volatility**，所以需要完整指标时直接用 `compute_metrics` 的返回值。

> 新增/修改指标计算时，**优先扩展 `run_portfolio.py` 的 `compute_metrics`，不要依赖 `core.generate_report`**。`examples.py` 仍用 `print_report()` 仅因其场景简单、未必触发赎回。

### 配置化多参数扫描（`run_sweep.py`）

把「持仓占比 × 调仓阈值」做成配置驱动的网格对比。配置全部是 JSON（`.gitignore` 已加 `!configs/` 例外使其入库）：

- `configs/portfolios/*.json` — 每个文件一个组合：`{name, etf_list:[{code,name,target_ratio}], reservoir_code}`（权重会被自动归一化，不必和为 1）。内置 `conservative` / `balanced` / `aggressive` 三档，同用 17 标的池。
- `configs/sweep.json` — 扫描网格 + 运行参数：`start/end/initial_capital/monitor_step/rf/benchmark`，以及 `band_ratios` 与 `absolute_thresholds` 两个待扫阈值列表。

`run_sweep.py` 做 `组合 × (band_ratios + absolute_thresholds)` 笛卡尔积回测，逐个 `run_config`（共享同一个 `info_cache`），每个跑 `compute_metrics`。输出（**CSV 数据 + 自包含 HTML 报告，不再出 PNG**）：

- `output/sweep_comparison.csv`（每行一个 组合×阈值，含 sharpe/calmar 等）。
- `output/profit_by_holding.csv`（每行一个 策略×标的：盈利/盈利占比/收益率/期末市值/成本）。
- `output/report.html`（由 `etf_backtest/report.py` 的 `generate_report_html` 生成）：策略总览表（年化/夏普红色渐变、回撤蓝色渐变）+ 排名 + 品种盈利矩阵（行=标的、列=策略，按钮可在「收益率%」与「盈利万元」间切换，红=盈利/蓝=亏损）+ 各组合利润发动机。

聚合指标用 `compute_metrics`（含 sharpe）；**标的级盈利用 `bt.get_current_mul().summary(end)` 的 `基金收益总额` 列**（= 现值−持有成本，已含分红；F 类基金在 summary 里是 6 位代码无前缀，需映射回规范代码，见 `capture_holding_profit`）。**不要用 `make_report`**（丢 sharpe）。配色用 A 股红涨惯例（红=盈利/上涨，蓝=亏损/下跌，不用绿色）。

> 短区间扫描时若阈值都没触发再平衡（`rebalance_count=0`），同一组合各行结果会完全相同——这是带宽/阈值太宽 + 区间太短的正常现象，跑完整区间才会分化。

## 注意事项与陷阱

- **F 类场外基金不缓存（性能关键）**：xalpha 默认 memory 后端只缓存 `vinfo`（SH/SZ），**`fundinfo`（F 码）每次构造都重新请求东方财富（每码 2 次 HTTP）**。多次回测同一些 F 码会重复抓取。解法：`ETFPortfolioBacktest(..., info_cache={})` 传入共享字典，`prepare()` 会首轮抓取后复用 info 对象（跨实例共享安全——info 在回测中只读）。`run_sweep.py` 已这么用，所以第 2 个组合起大幅提速。
- **买入金额必须 round 到分**：xalpha 在 `trade.py` 把买入金额的小数部分当作“自定义申购费”二进制编码（`feelabel = frac(100*value)`），当 `100×金额` 的小数部分落在 ~0.45–0.5 时会算出负费用并断言 `自定义申购费必须为正值` 而崩溃。`core.py` 所有 `buy` 调用（`_initial_purchase` / `_execute_rebalance` / `_swap`）都已 `round(amount, 2)`。**新增任何 buy 调用务必先 round 到分**，否则特定权重×资金组合会随机崩。原 `PORTFOLIO` 权重恰好在 100000 资金下产生整元金额才没踩坑。
- **联网与缓存**：首次运行从在线数据源（雪球/东方财富）下载行情，`data/cache/<code>.csv`（磁盘，仅 SH/SZ）+ 进程内 dict。`.gitignore` 忽略 `data/cache/`、`output/`、`*.csv`、`*.json`（已加 `!configs/` 例外）、`*.log`、`test_*.py`。
- **matplotlib 后端**：`run_portfolio.py` 顶部 `matplotlib.use("Agg")`（无界面，存图）；`run_sweep.py` 已不依赖 matplotlib（只出 CSV + HTML）。但 `examples.py` 和 `utils.py` 默认走交互式 `plt.show()`，在无显示环境（服务器/SSH）会卡住或报错，跑这类脚本前需自行设 `Agg`。
- **中文字体**：`utils.py` 设了 `SimHei / Microsoft YaHei / Arial Unicode MS`，图表中文标签依赖系统装了这些字体，否则中文会变方块。
- **`run_portfolio.py` 的 `PORTFOLIO`** 是该入口的默认持仓（现已被 `configs/portfolios/balanced.json` 镜像），docstring 记录了若干替代/合并决策（如红利 SH563020 上市晚用 SH512890 替代、中证 A500 指数取不到故权重并入沪深300）。
- **输出目录**：`run_portfolio.py` / `run_sweep.py` 把图表/CSV/HTML 报告写到 `output/`（产物，已 gitignore，不入库）。
