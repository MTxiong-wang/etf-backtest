# -*- coding: utf-8 -*-
"""
ETF回测系统 - 配置管理模块
"""

import re
import json
import os
from typing import List, Dict, Optional
from datetime import datetime


# band 模式必需的资金池代码；配置未指定时用此默认值
_DEFAULT_RESERVOIR = "F006484"


def validate_etf_code(code: str) -> bool:
    """
    验证标的代码格式

    支持以下前缀（与 xalpha.BTE.get_info 的分发一致）：
        SH/SZ + 6位：场内 ETF（如 SH512100、SZ159915）
        F    + 6位：场外开放式基金，走 fundinfo 取真实净值（如 F006484）
        M    + 6位：货币基金，走 mfundinfo（如 M003171）

    Args:
        code: 标的代码，如"SH512100"、"SZ159915"、"F006484"

    Returns:
        bool: 代码格式是否正确
    """
    pattern = r'^(SH|SZ|F|M)\d{6}$'
    return bool(re.match(pattern, code))


def normalize_ratios(ratios: List[float]) -> List[float]:
    """
    归一化比例，确保总和为1

    Args:
        ratios: 比例列表

    Returns:
        List[float]: 归一化后的比例列表
    """
    total = sum(ratios)
    if total == 0:
        raise ValueError("比例总和不能为0")
    return [r / total for r in ratios]


class ETFPortfolioConfig:
    """
    ETF投资组合配置类

    用于存储和验证回测所需的所有配置参数。

    Attributes:
        etf_list: ETF配置列表，每个元素包含code, name, target_ratio
        start_date: 回测开始日期
        end_date: 回测结束日期
        initial_capital: 初始资金
        rebalance_threshold: 偏离阈值（默认0.02，即2%）
        portfolio_dict: ETF代码到目标比例的映射字典
    """

    def __init__(
        self,
        etf_list: List[Dict[str, any]],
        start_date: str,
        end_date: str,
        initial_capital: float = 100000,
        rebalance_threshold: float = 0.02,
        rebalance_mode: str = "absolute",
        band_ratio: float = 0.5,
        reservoir_code: Optional[str] = None
    ):
        """
        初始化ETF投资组合配置

        Args:
            etf_list: 标的配置列表，格式：
                [{"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.4}, ...]
            start_date: 回测开始日期，格式"YYYY-MM-DD"
            end_date: 回测结束日期，格式"YYYY-MM-DD"
            initial_capital: 初始资金，默认100000
            rebalance_threshold: 绝对偏离阈值(模式absolute用)，默认0.02(2个百分点)
            rebalance_mode: 再平衡模式：
                "absolute" - 任一标的实际权重偏离目标超过 rebalance_threshold(绝对) 即全仓再平衡
                "band"     - 带状相对再平衡：标的实际权重落到 target*(1±band_ratio) 之外即触发，
                             仅把触发的那只拉回目标，差额由 reservoir_code(资金池) 吸收
            band_ratio: 带状模式的相对带宽，默认0.5(即±50%)。如目标7.2%则带为[3.6%,10.8%]
            reservoir_code: 带状模式的资金池代码(如 "F006484" 短期国开债)，吸收再平衡差额、自身不设带
        """
        self.etf_list = etf_list
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.rebalance_threshold = rebalance_threshold
        self.rebalance_mode = rebalance_mode
        self.band_ratio = band_ratio
        self.reservoir_code = reservoir_code

        # 验证并处理配置
        self._validate_and_normalize()

    def _validate_and_normalize(self):
        """验证并归一化配置"""

        # 验证日期格式
        try:
            self.start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
            self.end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"日期格式错误，应为YYYY-MM-DD: {e}")

        if self.start_dt >= self.end_dt:
            raise ValueError("开始日期必须早于结束日期")

        # 验证ETF配置
        if not self.etf_list:
            raise ValueError("ETF列表不能为空")

        # 验证每个ETF的配置
        for etf in self.etf_list:
            if 'code' not in etf or 'name' not in etf or 'target_ratio' not in etf:
                raise ValueError("每个ETF配置必须包含code, name, target_ratio")

            if not validate_etf_code(etf['code']):
                raise ValueError(f"ETF代码格式错误: {etf['code']}")

            if etf['target_ratio'] < 0:
                raise ValueError(f"目标比例不能为负: {etf['code']}")

        # 归一化比例
        ratios = [etf['target_ratio'] for etf in self.etf_list]
        normalized_ratios = normalize_ratios(ratios)

        # 更新归一化后的比例
        for i, etf in enumerate(self.etf_list):
            etf['target_ratio'] = normalized_ratios[i]

        # 创建代码到比例的映射
        self.portfolio_dict = {
            etf['code']: etf['target_ratio']
            for etf in self.etf_list
        }

    def get_etf_codes(self) -> List[str]:
        """获取所有ETF代码列表"""
        return list(self.portfolio_dict.keys())

    def get_target_ratio(self, code: str) -> float:
        """获取指定ETF的目标比例"""
        return self.portfolio_dict.get(code, 0)

    def __repr__(self):
        """打印配置信息"""
        etf_info = "\n".join([
            f"  {etf['code']} ({etf['name']}): {etf['target_ratio']:.2%}"
            for etf in self.etf_list
        ])
        return f"""ETFPortfolioConfig:
日期范围: {self.start_date} 至 {self.end_date}
初始资金: CNY{self.initial_capital:,.2f}
偏离阈值: {self.rebalance_threshold:.2%}

ETF配置:
{etf_info}"""


# ------------------------------------------------------------------
# JSON 配置加载（供 run_sweep.py / run_portfolio.py 使用）
# ------------------------------------------------------------------

def load_portfolio_file(path: str) -> Dict:
    """
    从 JSON 文件加载单个组合持仓配置。

    JSON 格式::

        {
            "name": "balanced",
            "etf_list": [{"code": "SH510300", "name": "沪深300ETF", "target_ratio": 0.4}, ...],
            "reservoir_code": "F006484"   # 可选，band 模式用
        }

    Args:
        path: JSON 文件路径

    Returns:
        Dict: ``{name, etf_list, reservoir_code}``（reservoir_code 可能为 None）
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data.get("etf_list"):
        raise ValueError(f"组合配置 {path} 缺少 etf_list 或为空")

    return {
        "name": data.get("name", os.path.splitext(os.path.basename(path))[0]),
        "etf_list": data["etf_list"],
        "reservoir_code": data.get("reservoir_code"),
    }


def load_sweep_file(path: str) -> Dict:
    """
    加载扫描网格配置 sweep.json。

    Returns:
        Dict: 包含 start / end / initial_capital / monitor_step / rf /
        benchmark / band_ratios / absolute_thresholds 等字段。
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_config(
    etf_list: List[Dict],
    start: str,
    end: str,
    capital: float,
    mode: str = "band",
    threshold: Optional[float] = None,
    band_ratio: Optional[float] = None,
    reservoir: Optional[str] = None,
) -> "ETFPortfolioConfig":
    """
    根据参数构造并校验一个 ``ETFPortfolioConfig``（复用其归一化逻辑）。

    Args:
        etf_list: 标的配置列表，会被深拷贝以免归一化污染原始数据
        start / end: 回测起止日期 "YYYY-MM-DD"
        capital: 初始资金
        mode: "band" 或 "absolute"
        threshold: absolute 模式的 ``rebalance_threshold``
        band_ratio: band 模式的相对带宽
        reservoir: band 模式的资金池代码；未给则用默认 ``_DEFAULT_RESERVOIR``

    Returns:
        ETFPortfolioConfig
    """
    # 深拷贝：归一化会就地改 target_ratio，多次 build 共用同一份 list 时需隔离
    etf_list = [dict(e) for e in etf_list]

    kwargs = dict(
        etf_list=etf_list,
        start_date=start,
        end_date=end,
        initial_capital=capital,
        rebalance_mode=mode,
    )

    if mode == "band":
        kwargs["band_ratio"] = band_ratio if band_ratio is not None else 0.5
        kwargs["reservoir_code"] = reservoir or _DEFAULT_RESERVOIR
    elif mode == "absolute":
        kwargs["rebalance_threshold"] = threshold if threshold is not None else 0.02
    else:
        raise ValueError(f"不支持的 rebalance_mode: {mode}（应为 band 或 absolute）")

    return ETFPortfolioConfig(**kwargs)
