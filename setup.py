import codecs
import os
from setuptools import setup

setup(
    name="pytest-cromwell",
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
        ]
    },
    py_modules=["pytest_cromwell"],
    install_requires=[
        "pytest",
        "delegator.py"
    ]
)
