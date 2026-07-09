# -*- coding: utf-8 -*-
"""
ETF回测系统安装配置
"""
from setuptools import setup, find_packages

setup(
    name="etf_backtest",
    version="0.1.0",
    description="ETF投资组合回测系统",
    packages=find_packages(),
    install_requires=[
        "xalpha>=0.12.0",
        "pandas",
        "matplotlib",
    ],
    python_requires=">=3.7",
)
