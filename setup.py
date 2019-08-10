import codecs
import os
from setuptools import setup, find_packages

setup(
    name="pytest-wdl",
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    description="Fixtures for pytest for running WDL workflows using Cromwell.",
    long_description=codecs.open(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "README.md"
        ),
        "rb",
        "utf-8"
    ).read(),
    entry_points={
        "pytest11": [
            "pytest_wdl = pytest_wdl"
        ],
        "pytest_wdl": [
            "bam = pytest_wdl.data_types.bam:BamDataFile",
            "vcf = pytest_wdl.data_types.vcf:VcfDataFile",
        ]
    },
    py_modules=["pytest_wdl"],
    packages=find_packages(),
    install_requires=[
        "pytest",
        "delegator.py"
    ],
    extras_require={
        "all": ["pysam"],
        "bam": ["pysam"]
    }
)
