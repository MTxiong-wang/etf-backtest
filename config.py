# -*- coding: utf-8 -*-
"""
ETF回测系统 - 配置管理模块
"""

import re
from typing import List, Dict, Optional
from datetime import datetime


def validate_etf_code(code: str) -> bool:
    """
    验证ETF代码格式

    Args:
        code: ETF代码，如"SH512100"或"SZ159915"

    Returns:
        bool: 代码格式是否正确
    """
    pattern = r'^(SH|SZ)\d{6}$'
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
        rebalance_threshold: float = 0.02
    ):
        """
        初始化ETF投资组合配置

        Args:
            etf_list: ETF配置列表，格式：
                [{"code": "SH512100", "name": "沪深300ETF", "target_ratio": 0.4}, ...]
            start_date: 回测开始日期，格式"YYYY-MM-DD"
            end_date: 回测结束日期，格式"YYYY-MM-DD"
            initial_capital: 初始资金，默认100000
            rebalance_threshold: 偏离阈值，默认0.02（2%）
        """
        self.etf_list = etf_list
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.rebalance_threshold = rebalance_threshold

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
