from setuptools import setup, find_packages

setup(
    name='vhdl-diagramer',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[],
    entry_points={
        'console_scripts': [
            'vhdl-diagramer=vhdl_diagramer.__main__:main',
        ],
    },
)
