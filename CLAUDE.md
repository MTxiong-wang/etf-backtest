# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 [xalpha](https://github.com/refraction-ray/xalpha) 框架的 A 股 ETF 投资组合**再平衡**回测工具。核心是把 `xalpha.backtest.BTE` 子类化，在每日回测循环里检测持仓偏离并自动调仓。包以扁平模块布局组织，通过 `import etf_backtest` 导入（需先 editable 安装）。

## 常用命令

依赖：`xalpha>=0.12.0`、`pandas`、`matplotlib`，Python ≥ 3.7。

```bash
# 安装（在项目根目录下，editable 模式让 examples/test 脚本能 import etf_backtest）
pip install -e .

# 生产入口：跑 run_portfolio.py（持仓读 configs/portfolios/balanced.json，默认参数读 configs/sweep.json）
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
- 首次需联网拉取行情并落盘到 `data/market_cache/`（见下文“行情缓存（csv 落盘）”），之后离线可跑；
- `test_*.py` 被 `.gitignore` 忽略（见下）。

直接当脚本运行即可：`python test_basic.py`、`python test_backtest.py`、`python run_test.py`。不要假设 `pytest` 能收集它们。

## 架构要点

### 模块分工

- `config.py` — `ETFPortfolioConfig`：校验 + 归一化比例，持有 `portfolio_dict`（code→target_ratio）。`validate_etf_code` 限定代码格式为 `^(SH|SZ|F|M)\d{6}$`。另有 JSON 加载器 `load_portfolio_file` / `load_sweep_file` / `build_config`（不改类，仅把 JSON 映射成 `ETFPortfolioConfig`）。
- `core.py` — `ETFPortfolioBacktest(BTE)`：回测引擎，子类化 `xalpha.backtest.BTE`。`__init__` 支持传入共享 `info_cache`（见下文“进程内 info 复用”）。
- `utils.py` — 绘图（`plot_portfolio_value` 等净值/配置图、`compare_strategies`）与 `format_report`；顶部设中文字体。另有 `plot_sweep_heatmap` / `plot_holding_heatmap`（旧版 PNG 热力图，已被 HTML 报告取代，保留备用）。
- `run_portfolio.py` — 真实组合的 CLI 入口与指标计算（见下文“两套报告路径”）。通用回测入口 `run_config(config, ...)` 也在这里。
- `run_sweep.py` — 配置化多参数扫描入口（见下文“配置化多参数扫描”）。
- `report.py` — `generate_report_html`：把扫描结果渲染成自包含 HTML 报告（替代 PNG）。
- `__init__.py` — 包入口：`import etf_backtest` 即调用 `configure_cache()`（行情 csv 落盘，见下文）+ `setup_logging()`（**日志规范化**：UTF-8 stdout + 时间戳格式 `%(asctime)s [%(levelname)s] %(message)s`，解决 Windows GBK 中文乱码）。所有入口都 `import etf_backtest`，故自动生效。
- `algos.py` — 策略算法模块（借鉴 bt.Algo）：`Algo` 基类 + `AlgoRebalance` / `AlgoRecord`，包装 `core.py` 的 `_check` / `_execute` / `_record`。`ETFPortfolioBacktest(algo_stack=...)` 可传自定义 Algo 栈；默认 `[AlgoRebalance, AlgoRecord]` = 重构前行为（详见下文“Algo 模块化”）。

### 回测循环（`core.py`）

`backtest()` 遍历 `pd.bdate_range(start, end)`，仅对落在 `xalpha.cons.opendate_set` 里的 A 股交易日调用 `run(date)`。`run()` 首日建仓，之后每隔 `monitor_step` 个交易日做一次“检查+记录”。`sys.summary()` 很慢，长区间用 `monitor_step=5`（周度）可大幅提速且对阈值再平衡结果影响很小；`backtest()` 末尾有兜底逻辑保证末日净值被记录。

`ETFPortfolioBacktest` 复用了 BTE 的 `buy/sell/get_info/get_current_mul/get_current_mulfix/get_code` 等方法，不要重写这些底层接口。

### 两种再平衡模式（`rebalance_mode`）

1. **`"absolute"`**（默认）：任一标的实际权重偏离目标超过 `rebalance_threshold`（绝对百分点）即触发**全仓再平衡**，把所有标的拉回目标权重（`_execute_rebalance`）。
2. **`"band"`**：带状相对再平衡。只有落到 `target*(1±band_ratio)` 带外的标的被拉回目标，**差额由 `reservoir_code`（资金池，通常是债券基金）吸收**，资金池自身不设带（`_execute_band` + `_swap`）。`band_ratio` 取极大值（如 `run_portfolio.py` 里用 `10.0`）等价于永不触发 = 买入持有。

成本模型：卖出含赎回费（`config.redeem_fee`，默认 0.005=0.5%）、买入可配费率（`config.buy_fee`，默认 0=免佣）；`core.py` 的 `_execute_rebalance` / `_swap` / `_initial_purchase` 均读 `self.config.redeem_fee`/`buy_fee`（原硬编码 0.005 已移除）。`_swap` 先卖超配、后买低配以降低资金池瞬时缺口。

### Algo 模块化（`algos.py`）

`run()` 不再直接调 `_check_*`/`_execute_*`/`_record_*`，而是遍历 `self._get_algo_stack()` 返回的 Algo 栈，每个 `Algo.run(bt, date, summary_df)` 执行一步、返回更新后的 `summary_df`（返回 `None` 中断栈）。

- 默认栈 `[AlgoRebalance, AlgoRecord]`：`AlgoRebalance` 包装 `_check_rebalance_needed` + `_execute_rebalance`（内部按 mode 分发 band/absolute），`AlgoRecord` 包装 `_record_portfolio_status`。**默认行为与重构前完全一致**（`diff` 验证 IDENTICAL）。
- 自定义：`ETFPortfolioBacktest(cfg, algo_stack=[AlgoRecord()])` = 只记录不调仓 = 买入持有；可组合新 Algo 插入栈。
- 现有 `_check_*`/`_execute_*`/`_record_*` 方法保留，Algo 内部调用，向后兼容。

### 代码前缀决定数据来源

`BTE.get_info` 按代码前缀自动分发（行情统一来自 `data/market_cache/` 的 csv 落盘）：

- `SH/SZ` → `vinfo`（雪球前复权行情）
- `F` → `fundinfo`（场外基金真实净值，含分红）
- `M` → `mfundinfo`（货币基金）

`prepare()` 对每个标的调 `get_info`（按前缀分发到 `vinfo`/`fundinfo`/`mfundinfo`），行情统一来自 `data/market_cache/` 的 csv 落盘。

### 两套报告路径（最关键的非显然点）

`core.generate_report()` / `print_report()` 依赖 xalpha 的 `get_current_mulfix()` + `xirrrate()` + `summary()`。**发生赎回后这些接口可能抛 `initial total cash too low`**，不可靠。

因此 `run_portfolio.py` **刻意绕开** `generate_report()`，改用自带 `compute_metrics(history, initial_capital, rf=0.02)` 直接从 `portfolio_history` 净值序列算指标：总收益、年化、最大回撤、年化波动率、夏普（无风险利率 `rf`，默认 0.02）、卡玛，以及扩展风险指标 **sortino / VaR_95 / CVaR_95（日，95%）/ 胜率 / 盈亏比**。`make_report()` 把结果包装成 `compare_strategies` 能吃的精简字典——**但它只留 4 个字段、丢掉 sharpe/calmar/volatility**，所以需要完整指标时直接用 `compute_metrics` 的返回值。

> 新增/修改指标计算时，**优先扩展 `run_portfolio.py` 的 `compute_metrics`，不要依赖 `core.generate_report`**。`examples.py` 仍用 `print_report()` 仅因其场景简单、未必触发赎回。

### 配置化多参数扫描（`run_sweep.py`）

把「持仓占比 × 调仓阈值」做成配置驱动的网格对比。配置全部是 JSON（`.gitignore` 已加 `!configs/` 例外使其入库）：

- `configs/portfolios/*.json` — 每个文件一个组合：`{name, etf_list:[{code,name,target_ratio}], reservoir_code}`（权重会被自动归一化，不必和为 1）。内置 `conservative` / `balanced` / `aggressive` 三档，同用 17 标的池。
- `configs/sweep.json` — 扫描网格 + 运行参数：`start/end/initial_capital/monitor_step/rf/redeem_fee/buy_fee/benchmark`，以及 `band_ratios` 与 `absolute_thresholds` 两个待扫阈值列表。`run_portfolio.py` 的默认参数（区间/资金/步长/rf/成本）也从此文件读，sys.argv 可覆盖。

`run_sweep.py` 做 `组合 × (band_ratios + absolute_thresholds)` 笛卡尔积回测，逐个 `run_config`（共享同一个 `info_cache`），每个跑 `compute_metrics`。输出（**CSV 数据 + 自包含 HTML 报告，不再出 PNG**）：

- `output/sweep_comparison.csv`（每行一个 组合×阈值，含 sharpe/calmar 等）。
- `output/profit_by_holding.csv`（每行一个 策略×标的：盈利/盈利占比/收益率/期末市值/成本）。
- `output/report.html`（由 `etf_backtest/report.py` 的 `generate_report_html` 生成）：策略总览表（年化/夏普红色渐变、回撤蓝色渐变）+ 排名 + 品种盈利矩阵（行=标的、列=策略，按钮可在「收益率%」与「盈利万元」间切换，红=盈利/蓝=亏损）+ 各组合利润发动机。

聚合指标用 `compute_metrics`（含 sharpe）；**标的级盈利用 `bt.get_current_mul().summary(end)` 的 `基金收益总额` 列**（= 现值−持有成本，已含分红；F 类基金在 summary 里是 6 位代码无前缀，需映射回规范代码，见 `capture_holding_profit`）。**不要用 `make_report`**（丢 sharpe）。配色用 A 股红涨惯例（红=盈利/上涨，蓝=亏损/下跌，不用绿色）。

> 短区间扫描时若阈值都没触发再平衡（`rebalance_count=0`），同一组合各行结果会完全相同——这是带宽/阈值太宽 + 区间太短的正常现象，跑完整区间才会分化。

## 注意事项与陷阱

- **进程内 info 复用（`info_cache`）**：F/M 类的 csv 落盘已由 `configure_cache()` 自动覆盖——`basicinfo` 在 `info.py:333-342` 对接 `set_backend`，与 SH/SZ 一起落盘（文件名 `INFO-<6位码>.csv`，实测见下条）。即便落盘，`fundinfo` 每次构造仍要读盘反序列化 + `update()` 增量联网核对最新净值，单进程内多次构造同一 F 码仍是浪费。多个回测实例复用同一批标的的解法：`ETFPortfolioBacktest(..., info_cache={})` 传共享字典，`prepare()` 首轮构造后跨实例复用同一 info 对象（回测中只读，共享安全）。`run_sweep.py` 已这么用，第 2 个组合起大幅提速。
- **买入金额必须 round 到分**：xalpha 在 `trade.py` 把买入金额的小数部分当作“自定义申购费”二进制编码（`feelabel = frac(100*value)`），当 `100×金额` 的小数部分落在 ~0.45–0.5 时会算出负费用并断言 `自定义申购费必须为正值` 而崩溃。`core.py` 所有 `buy` 调用（`_initial_purchase` / `_execute_rebalance` / `_swap`）都已 `round(amount, 2)`。**新增任何 buy 调用务必先 round 到分**，否则特定权重×资金组合会随机崩。原 `PORTFOLIO` 权重恰好在 100000 资金下产生整元金额才没踩坑。
- **行情缓存（csv 落盘，全标的覆盖）**：`etf_backtest/__init__.py` 的 `configure_cache()` 在 `import etf_backtest` 时调 `xa.set_backend(backend="csv", path="data/market_cache")`，**同时**覆盖所有标的：场内 `<前缀码>.csv`（如 `SH510300.csv`，`vinfo`→`get_daily`）、场外基金 `INFO-<6位码>.csv`（如 `INFO-006484.csv`，`fundinfo`/`mfundinfo`→`basicinfo` fetch/save，`info.py:333-342` 自动对接 `set_backend`）。首次抓某标的即写盘其全部可获取历史，之后请求纯读盘过滤（场内，实测跨进程 0.016s 不联网）或读盘+增量核对（场外，实测二次构造 0.02s），不再全量联网。**这套才是回测真正读取的行情来源**（早期 `ETFDataManager` + `data/cache/` 那套死缓存已整体移除，`core.prepare()` 不再有 `data_manager` 空值告警）。`.gitignore` 已忽略 `output/`、`*.csv`、`*.json`（`!configs/` 例外）、`*.log`、`test_*.py`。
- **区间起点受标的上市日约束（关键陷阱）**：sweep/run 区间起点必须 ≥ 组合里最晚上市的标的。雪球对未上市标的返回 EMPTY，但 csv 落盘 + `BTE.get_info` 的 `vinfo(start=self.start-180d)` 会返回标的上市后的数据，导致**建仓日用了上市后净值（数据穿越）**、持仓比例失真（如某标的在 0.08%~15% 间跳变）、band 规则每周误触发爆炸调仓（单回测数百次调仓 + 内存累积 OOM，且块缓冲让崩溃 output 0 字节无日志）。实测组合里最晚的是恒生科技 SH513180（雪球最早 2021-05-25）、科创50 SH588080（2020-11-16），故 `sweep.json` 的 `start` 固定为 2021-05-25。换组合时按最晚上市标的调整起点；要跑更长历史只能替换为更早的近似标的。
- **matplotlib 后端**：`run_portfolio.py` 顶部 `matplotlib.use("Agg")`（无界面，存图）；`run_sweep.py` 已不依赖 matplotlib（只出 CSV + HTML）。但 `examples.py` 和 `utils.py` 默认走交互式 `plt.show()`，在无显示环境（服务器/SSH）会卡住或报错，跑这类脚本前需自行设 `Agg`。
- **中文字体**：`utils.py` 设了 `SimHei / Microsoft YaHei / Arial Unicode MS`，图表中文标签依赖系统装了这些字体，否则中文会变方块。
- **`run_portfolio.py` 的 `PORTFOLIO`** 是该入口的默认持仓（现已被 `configs/portfolios/balanced.json` 镜像），docstring 记录了若干替代/合并决策（如红利 SH563020 上市晚用 SH512890 替代、中证 A500 指数取不到故权重并入沪深300）。
- **输出目录**：`run_portfolio.py` / `run_sweep.py` 把图表/CSV/HTML 报告写到 `output/`（产物，已 gitignore，不入库）。
