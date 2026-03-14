"""
Setup script for DevFlow AI Prototype
Run: pip install -e .
"""
from setuptools import setup, find_packages

setup(
    name="devflow-ai-prototype",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        'torch>=2.0.0',
        'transformers>=4.30.0',
        'requests>=2.31.0',
        'numpy>=1.24.0',
        'pandas>=2.0.0',
        'scikit-learn>=1.3.0',
        'pytest>=7.4.0',
    ],
    python_requires='>=3.9',
)