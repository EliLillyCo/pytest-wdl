[![Travis CI](https://travis-ci.com/EliLillyCo/pytest-wdl.svg?branch=master)](https://travis-ci.com/EliLillyCo/pytest-wdl)
[![Code Coverage](https://codecov.io/gh/elilillyco/pytest-wdl/branch/master/graph/badge.svg)](https://codecov.io/gh/elilillyco/pytest-wdl)
[![Documentation Status](https://readthedocs.org/projects/pytest-wdl/badge/?version=latest)](https://pytest-wdl.readthedocs.io/en/latest/?badge=latest)

<img width="200" alt="logo" src="docs/source/logo.png"/>

This package is a plugin for the [pytest](https://docs.pytest.org/en/latest/) unit testing framework that enables testing of workflows written in [Workflow Description Language](https://github.com/openwdl).

## Dependencies

* Python 3.6 or 3.7 (3.8 is not yet fully supported)
* Java 1.8+
* [Cromwell](https://github.com/broadinstitute/cromwell/releases/tag/38) JAR file
* [Docker](https://www.docker.com/get-started) daemon (if your WDL tasks depend on Docker images)

Other python dependencies are installed when you install the library.

## Installation

### Install from PyPI

```commandline
$ pip install pytest-wdl
```

### Install from source

You can to clone the repository and install:

```
$ make install
```

Or use pip to install from github:

```commandline
$ pip install git+https://github.com/elilillyco/pytest-wdl.git
```

### Install optional dependencies

Some optional features of pytest-wdl have additional dependencies that are loaded on-demand. For example, to enable comparison of expected and actual BAM file outputs of a workflow, the [pysam](https://pysam.readthedocs.io/) library is required.

The following plugins require an "extras" installation:

- Data types
    - bam
- URL schemes
    - dx (DNAnexus)
- Other
    - progress (show progress bars when downloading files)

To install the dependencies for a data type that has extra dependencies:

```
$ pip install pytest-wdl[<data_type>]
```

To do this locally, you can clone the repo and run:

```commandline
$ pip install -e .[<data_type>]
```

To install pytest-wdl and **all** extras dependencies:

```
$ pip install pytest-wdl[all]
```

## Usage

The pytest-wdl plugin provides a set of fixtures for use with pytest. Here is a quick example:

```python
# test_variant_caller.py
def test_variant_caller(workflow_data, workflow_runner):
    inputs = workflow_data.get_dict("bam", "bai")
    inputs["index"] = {
        "fasta": workflow_data["index_fa"],
        "organism": "human"
    }
    expected = workflow_data.get_dict("vcf")
    workflow_runner(
        "variant_caller.wdl",
        inputs,
        expected
    )
```

This test will execute a workflow (such as the following one) with the specified inputs, and will compare the outputs to the specified expected outputs.

```wdl
# variant_caller.wdl
version 1.0

struct Index {
  File fasta
  String organism
}

workflow call_variants {
  input {
    File bam
    File bai
    Index index
  }
  ...
  output {
    File vcf = variant_caller.vcf
  }
}
```

Input and output data are defined in a `test_data.json` file in the same directory as your test script:

```json
{
  "bam": {
    "url": "http://example.com/my.bam"
  },
  "bai": {
    "url": "http://example.com/my.bam.bai"
  },
  "index_fa": {
    "name": "chr22.fasta"
  },
  "vcf": {
    "url": "http://example.com/expected.vcf.gz",
    "type": "vcf",
    "allowed_diff_lines": 2
  }
}
```

For details, [read the docs](https://pytest-wdl.readthedocs.io).

## Contributing

To develop pytest-wdl, clone the repository and install all the dependencies:

```commandline
$ git clone https://github.com/EliLillyCo/pytest-wdl.git
$ pip install -r requirements.txt
```

To run the full build and unit tests, run:

```commandline
$ make
```

## Support

pytest-wdl is *not* an official product of Eli Lilly or DNAnexus. Please do *not* contact these companies (or any employees thereof) for support. To report a bug or feature request, please open an issue in the [issue tracker](https://github.com/EliLillyCo/pytest-wdl/issues).
