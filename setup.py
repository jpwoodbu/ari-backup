#!/usr/bin/env python

from setuptools import setup

setup(
    name='ari-backup',
    version='1.0.1',
    license='BSD',
    packages=['ari_backup'],
    author='ari-backup team',
    install_requires=[
        'PyYAML>=3.0',
        'python-gflags>=1.5.1',
    ],
    classifiers=(
        'Intended Audience :: System Administrators',
        'License :: OSI Aprooved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Operating System :: OS Independent',
        'Topic :: System :: Archiving :: Backup',
    )
)
