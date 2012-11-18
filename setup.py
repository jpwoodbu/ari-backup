#!/usr/bin/env python

from setuptools import setup

setup(
    name='ari_backup',
    version='0.9.1',
    license='ARI',
    packages=['ari_backup'],
    author='American Research Institute',
    install_requires=[
        'PyYAML>=3.0',
    ]
)
