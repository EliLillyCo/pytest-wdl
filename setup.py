import codecs
import os
from setuptools import setup, find_packages


extras_require = {
    "bam": ["pysam"],
    "progress": ["tqdm"]
}
extras_require["all"] = [
    lib
    for lib_array in extras_require.values()
    for lib in lib_array
]


setup(
    name="pytest-wdl",
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    description="Fixtures for pytest for running WDL workflows using Cromwell.",
    long_description_content_type="text/markdown",
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
        "pytest_wdl.data_types": [
            "bam = pytest_wdl.data_types.bam:BamDataFile",
            "vcf = pytest_wdl.data_types.vcf:VcfDataFile",
        ],
        "pytest_wdl.executors": [
            "cromwell = pytest_wdl.executors.cromwell:CromwellExecutor"
        ]
    },
    py_modules=["pytest_wdl"],
    packages=find_packages(),
    install_requires=[
        "pytest",
        "delegator.py"
    ],
    extras_require=extras_require
)
