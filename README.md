# ETF投资组合回测系统

基于xalpha框架的ETF投资组合再平衡策略回测工具。

## 功能特点

- 多只ETF按目标比例配置
- 持仓比例偏离阈值自动触发调仓
- 支持自定义回测时间范围
- 完整的回测报告（收益率、最大回撤、调仓次数等）
- 可视化分析（净值曲线、配置变化、收益分布）

## 安装依赖

```bash
pip install xalpha pandas matplotlib
```

## 快速开始

### 基础使用

```python
import etf_backtest as etfb

# 定义ETF组合配置
config = etfb.ETFPortfolioConfig(
    etf_list=[
        {"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.4},
        {"code": "SH512980", "name": "科创50ETF", "target_ratio": 0.3},
        {"code": "SZ159915", "name": "创业板ETF", "target_ratio": 0.3}
    ],
    start_date="2020-01-01",
    end_date="2023-12-31",
    initial_capital=100000,
    rebalance_threshold=0.02  # 2%偏离触发调仓
)

# 创建回测实例并运行
backtest = etfb.ETFPortfolioBacktest(config)
backtest.backtest()

# 打印回测报告
backtest.print_report()
```

### 运行示例

```bash
cd D:\Codes\etf_backtest
python examples.py
```

## ETF代码格式

- 上交所ETF：`SH` + 6位数字，如 `SH512100`
- 深交所ETF：`SZ` + 6位数字，如 `SZ159915`

## 主要参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `etf_list` | ETF配置列表（code, name, target_ratio） | 必填 |
| `start_date` | 回测开始日期 (YYYY-MM-DD) | 必填 |
| `end_date` | 回测结束日期 (YYYY-MM-DD) | 必填 |
| `initial_capital` | 初始资金 | 100000 |
| `rebalance_threshold` | 偏离阈值（如0.02表示2%） | 0.02 |

## 回测报告指标

- **最终资产**：回测结束时的总资产
- **总收益率**：期间累计收益率
- **年化收益**：年化收益率
- **XIRR**：内部收益率
- **最大回撤**：期间最大回撤幅度
- **调仓次数**：触发调仓的次数

## 可视化功能

```python
# 绘制净值曲线
etfb.plot_portfolio_value(
    backtest.get_portfolio_history(),
    backtest.get_rebalance_dates()
)

# 绘制配置变化
etfb.plot_allocation_history(
    backtest.get_portfolio_history(),
    config.etf_list
)

# 绘制收益率分布
etfb.plot_returns_distribution(
    backtest.get_portfolio_history()
)

# 对比多个策略
etfb.compare_strategies(reports, labels)
```

## 项目结构

```
etf_backtest/
├── __init__.py      # 模块入口
├── config.py        # 配置管理
├── data.py          # 数据获取
├── core.py          # 回测引擎
├── utils.py         # 工具函数
├── examples.py      # 使用示例
└── README.md        # 文档
```

## 注意事项

1. 确保网络连接正常，需要从在线数据源获取ETF历史数据
2. 回测只在A股交易日运行
3. 调仓操作考虑了0.5%的赎回费估算
4. 首次运行会下载数据，可能需要一些时间

## 常见问题

**Q: 为什么某些ETF获取不到数据？**

A: 请检查ETF代码格式是否正确（SH/SZ前缀+6位数字），以及该ETF是否在指定时间范围内存在。

**Q: 如何调整调仓频率？**

A: 通过修改 `rebalance_threshold` 参数，阈值越小调仓越频繁。

**Q: 能否添加交易成本和滑点？**

A: 当前版本已考虑0.5%赎回费，更精细的成本控制可在后续版本添加。

## 许可证

MIT License
