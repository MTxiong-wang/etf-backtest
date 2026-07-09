# -*- coding: utf-8 -*-
"""
ETF回测系统 - 数据获取模块
"""

import os
import pandas as pd
from typing import Optional, Dict
from datetime import datetime

import xalpha as xa
from xalpha.universal import get_daily


class ETFDataManager:
    """
    ETF数据管理器

    负责获取、缓存和管理ETF历史数据。

    Attributes:
        cache_dir: 缓存目录路径
        use_cache: 是否使用缓存
    """

    def __init__(self, cache_dir: Optional[str] = None, use_cache: bool = True):
        """
        初始化数据管理器

        Args:
            cache_dir: 缓存目录路径，默认为项目下的data/cache
            use_cache: 是否使用缓存，默认True
        """
        if cache_dir is None:
            # 默认缓存目录
            self.cache_dir = os.path.join(
                os.path.dirname(__file__), 'data', 'cache'
            )
        else:
            self.cache_dir = cache_dir

        self.use_cache = use_cache

        # 创建缓存目录
        if self.use_cache and not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        # 数据缓存 {code: DataFrame}
        self._data_cache = {}

    def fetch_etf_data(
        self,
        code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        获取单个ETF的历史数据

        Args:
            code: ETF代码，如"SH512100"
            start_date: 开始日期，格式"YYYY-MM-DD"
            end_date: 结束日期，格式"YYYY-MM-DD"

        Returns:
            DataFrame: 包含date, open, close, high, low, volume, percent列
        """
        # 检查内存缓存
        cache_key = f"{code}_{start_date}_{end_date}"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]

        # 尝试从磁盘缓存加载
        if self.use_cache:
            cached_data = self._load_from_cache(code, start_date, end_date)
            if cached_data is not None and not cached_data.empty:
                self._data_cache[cache_key] = cached_data
                return cached_data

        # 从网络获取数据
        try:
            data = get_daily(code, start=start_date, end=end_date)

            if data is None or data.empty:
                raise ValueError(f"无法获取ETF数据: {code}")

            # 确保数据按日期排序
            data = data.sort_values('date').reset_index(drop=True)

            # 保存到缓存
            if self.use_cache:
                self._save_to_cache(code, data)

            # 保存到内存缓存
            self._data_cache[cache_key] = data

            return data

        except Exception as e:
            raise Exception(f"获取{code}数据失败: {e}")

    def fetch_batch_etf_data(
        self,
        codes: list,
        start_date: str,
        end_date: str
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取多个ETF的历史数据

        Args:
            codes: ETF代码列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Dict[str, DataFrame]: 代码到数据的映射
        """
        result = {}
        for code in codes:
            try:
                data = self.fetch_etf_data(code, start_date, end_date)
                result[code] = data
            except Exception as e:
                print(f"警告: 获取{code}数据失败: {e}")
                result[code] = pd.DataFrame()
        return result

    def get_etf_info(self, code: str) -> Dict:
        """
        获取ETF基本信息

        Args:
            code: ETF代码

        Returns:
            Dict: 包含代码、名称等信息
        """
        data = self.fetch_etf_data(code, "2020-01-01", "2024-12-31")
        if data.empty:
            return {}

        return {
            'code': code,
            'latest_price': float(data['close'].iloc[-1]),
            'data_points': len(data),
            'date_range': f"{data['date'].iloc[0]} 至 {data['date'].iloc[-1]}"
        }

    def _get_cache_path(self, code: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, f"{code}.csv")

    def _save_to_cache(self, code: str, data: pd.DataFrame):
        """保存数据到磁盘缓存"""
        try:
            cache_path = self._get_cache_path(code)
            data.to_csv(cache_path, index=False, encoding='utf-8')
        except Exception as e:
            print(f"警告: 保存缓存失败 {code}: {e}")

    def _load_from_cache(
        self,
        code: str,
        start_date: str,
        end_date: str
    ) -> Optional[pd.DataFrame]:
        """从磁盘缓存加载数据"""
        cache_path = self._get_cache_path(code)

        if not os.path.exists(cache_path):
            return None

        try:
            # 读取缓存数据
            data = pd.read_csv(cache_path)

            if data.empty:
                return None

            # 过滤日期范围
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            data['date'] = pd.to_datetime(data['date'])

            filtered = data[
                (data['date'] >= start_dt) &
                (data['date'] <= end_dt)
            ]

            return filtered

        except Exception as e:
            print(f"警告: 读取缓存失败 {code}: {e}")
            return None

    def validate_data_coverage(
        self,
        data: pd.DataFrame,
        start_date: str,
        end_date: str
    ) -> bool:
        """
        验证数据是否覆盖指定时间范围

        Args:
            data: ETF数据
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            bool: 数据是否完整覆盖
        """
        if data.empty:
            return False

        actual_start = pd.to_datetime(data['date'].iloc[0])
        actual_end = pd.to_datetime(data['date'].iloc[-1])
        required_start = pd.to_datetime(start_date)
        required_end = pd.to_datetime(end_date)

        return actual_start <= required_start and actual_end >= required_end

    def clear_cache(self):
        """清空所有缓存"""
        self._data_cache.clear()
        if os.path.exists(self.cache_dir):
            for file in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
