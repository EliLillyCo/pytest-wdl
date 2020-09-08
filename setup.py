import codecs
import os
from setuptools import setup, find_packages


extras_require = {
    "bam": ["pysam>=0.15.4"],
    "dx": ["dxpy>=0.297.1"],
    "http": ["requests"],
    "progress": ["tqdm"],
    "yaml": ["pyyaml"],
}
extras_require["all"] = list(
    set(lib for lib_array in extras_require.values() for lib in lib_array)
)


setup(
    name="pytest-wdl",
    author="The pytest-wdl development team",
    url="https://github.com/EliLillyCo/pytest-wdl",
    project_urls={
        "Documentation": "https://pytest-wdl.readthedocs.io/en/stable/",
        "Source": "https://github.com/EliLillyCo/pytest-wdl",
        "Tracker": "https://github.com/EliLillyCo/pytest-wdl/issues",
    },
    description="Pytest plugin for testing WDL workflows.",
    long_description_content_type="text/markdown",
    long_description=codecs.open(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "README.md"),
        "rb",
        "utf-8",
    ).read(),
    license="Apache License 2.0",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    entry_points={
        "pytest11": ["pytest_wdl = pytest_wdl"],
        "pytest_wdl.data_types": [
            "bam = pytest_wdl.data_types.bam:BamDataFile[bam]",
            "vcf = pytest_wdl.data_types.vcf:VcfDataFile",
            "json = pytest_wdl.data_types.json:JsonDataFile",
        ],
        "pytest_wdl.executors": [
            "miniwdl = pytest_wdl.executors.miniwdl:MiniwdlExecutor",
            "cromwell = pytest_wdl.executors.cromwell_local:CromwellLocalExecutor",
            "cromwell-server = pytest_wdl.executors.cromwell_server:"
            "CromwellServerExecutor[http]",
            "dxwdl = pytest_wdl.providers.dx:DxWdlExecutor[dx]",
        ],
        "pytest_wdl.url_schemes": ["dx = pytest_wdl.providers.dx:DxUrlHandler[dx]"],
    },
    py_modules=["pytest_wdl"],
    packages=find_packages(),
    install_requires=[
        "pytest<=5.3.5",
        "subby>=0.1.6",
        "miniwdl==0.7.0",
        "pytest-subtests",
        "xphyle>=4.1.3",
    ],
    extras_require=extras_require,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Framework :: Pytest",
        "Environment :: Plugins",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
