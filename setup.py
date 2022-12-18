#!/usr/bin/env python
"""Setup script for ari_backup package."""

from distutils.core import setup

setup(
    name='ari-backup',
    version='2.0.0',
    license='BSD',
    packages=['ari_backup'],
    author='ari-backup team',
    install_requires=[
        'absl-py>=1.3.0',
        'PyYAML>=3.0',
    ],
    tests_require=[
        'flake8',
        'nose'
    ],
    test_suite='nose.collector',
    classifiers=[
        'Intended Audience :: System Administrators',
        'License :: OSI Aprooved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Operating System :: OS Independent',
        'Topic :: System :: Archiving :: Backup',
    ]
)
