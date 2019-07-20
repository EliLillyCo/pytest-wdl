import codecs
import os
from setuptools import setup, find_packages

setup(
    name="pytest_cromwell",
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
            "pytest_cromwell = pytest_cromwell"
        ],
        "pytest_cromwell": [
            "bam = pytest_cromwell.data_types.bam:BamDataFile",
            "vcf = pytest_cromwell.data_types.vcf:VcfDataFile",
        ]
    },
    py_modules=["pytest_cromwell"],
    packages=find_packages(),
    install_requires=[
        "pytest",
        "pytest-datadir-ng",
        "delegator.py"
    ],
    extras_require={
        "all": ["pysam"],
        "bam": ["pysam"]
    }
)
