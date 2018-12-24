#!/usr/bin/env python

import imp
import os.path

try:
    from setuptools import find_packages, setup
except ImportError:
    raise ImportError(
        "'setuptools' is required, but not installed. "
        "See https://packaging.python.org/installing/")


version_mod = imp.load_source(
    'version',
    os.path.join(os.path.dirname(__file__), 'nengonized_server', 'version.py'))

setup(
    name="nengonized-server",
    version=version_mod.version_string,
    author="Jan Gosmann",
    author_email="jan@hyper-world.de",
    url='https://github.com/jgosmann/nengonized-server',
    license="proprietary",
    description="TODO",
    long_description="TODO",

    packages=find_packages(),
    provides=['nengonized_server'],

    install_requires=['graphene', 'nengonized-kernel', 'tornado', 'websockets'],
    extras_require={
        'tests': ['pytest', 'pytest-asyncio'],
    },

    entry_points={
    },

    classifiers=[
    ],
)
