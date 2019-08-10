# pytest-wdl

This package provides fixtures to enable writing tests that execute WDL workflows via Cromwell and check the generated output against expected values.

## Dependencies

* Python 3.6+
* Java 1.8+
* [Cromwell](https://github.com/broadinstitute/cromwell/releases/tag/38) JAR file
* [Docker](https://www.docker.com/get-started) daemon (if your WDL tasks depend on Docker images)

Other python dependencies are installed when you install the library.

## Installation

### Install from PyPI

```commandline
pip install pytest-wdl
```

### Install from source

You can to clone the repository and install:

```
make install
```

Or use pip to install from github:

```commandline
pip install git+https://github.com/elilillyco/pytest-wdl.git
```

### Installing Data Type Plugins

Data Types for expected output comparison are plugins. They are loaded on-demand and if they require external dependencies, you must install those.

The following data types require an extras installation:

- bam

To install the dependencies for a data type that has extra dependencies:

`pip install pytest-wdl[<data_type>]`

To do this locally, you can clone the repo and run:

`pip install -e .[<data_type>]`

To install pytest-wdl and **all** extras dependencies:

`pip install pytest-wdl[all]`

## Usage

The pytest-wdl plugin provides a set of fixtures for use with pytest. Here is a quick example:

```python
def test_variant_caller(workflow_data, workflow_runner):
    inputs = {
        "bam": workflow_data["bam"],
        "bai": workflow_data["bai"]
    }
    expected = {
        "vcf": workflow_data["vcf"]
    }
    workflow_runner(
        "variant_caller/variant_caller.wdl",
        "call_variants",
        inputs,
        expected
    )
```

For details, [read the docs](docs/index.html).

### Fixtures

The main fixtures are:

* workflow_data: Provides access to data files for use as inputs to a workflow, and for comparing to workflow output. Data files may be stored locally or remotely. The local cache directory may be specified using the `CACHE_DIR` environment variable; otherwise a temporary directory is used and is deleted at the end of the test session. Data are described in a JSON file. File data are described as a hash with the following keys.
    * url: Optional; the remote URL.
    * path: Optional; the local path to the file.
    * contents: Optional; the contents of the file, specified as a string.
    * name: Filename to use when localizing the file; also used when none of [url,path,contents] are defined to find the data file within the tests directory, using the same directory structure defined by the [pytest-datadir-ng](https://pypi.org/project/pytest-datadir-ng/) fixture.
    * type: The file type. This is optional and only needs to be provided for certain types of files that are handled specially for the sake of comparison.
    * allowed\_diff\_lines: Optional and only used for outputs comparison. If '0' or not specified, it is assumed that the expected and actual outputs are identical.
* cromwell_harness: Provides a CromwellHarness object that runs a WDL workflow using Cromwell with given inputs, parses out the results, and compares them against expected values. The `run_workflow` method has the following parameters:
    * wdl_script: The WDL script to execute. The path should be relative to the project root.
    * workflow_name: The name of the workflow in the WDL script.
    * inputs: Object that will be serialized to JSON and provided to Cromwell as the workflow inputs.
    * expected: Dict mapping output parameter names to expected values. For file outputs, the expected value can be specified as above (i.e. a URL, path, or contents). Any outputs that are not specified are ignored. This is an optional parameter and can be omitted if, for example, you only want to test that the workflow completes successfully.
    * Additional keyword arguments:
        * execution_dir: Directory in which to execute the workflow. Defaults to cwd. Ignored if `run_in_tempdir is True`. *Deprecated: will be removed in v1.0*
        * inputs_file: Specify the inputs.json file to use, or the path to the inputs.json file to write, instead of a temp file.
        * imports_file: Specify the imports file to use, or the path to the imports zip file to write, instead of a temp file.
        * java_args: Override the default Java arguments.
        * cromwell_args: Override the default Cromwell arguments.
* workflow_runner: This is an alternative to cromwell_harness. It provides a callable and automatically determines the execution_dir based on the execution_dir fixture.

There are also fixtures for specifying required inputs to the two main fixtures.

* project_root: The root directory of the project. All relative paths are relative to this directory.
* workflow_data_descriptor_file: Path to the JSON file that describes the test data. Defaults to `tests/test_data.json`.
* workflow_data_descriptors: Mapping of test data names to values. Each value may be a primitive, a map describing a data file, or a DataFile object.
* cache_dir: Local directory for caching test data. The `CACHE_DIR` environment variable takes precedence, otherwise by default this fixture creates a temporary directory that is used to cache test data for the test module.
* execution_dir: Local directory in which tests are executed. The `EXECUTION_DIR` environment variable takes precedence, otherwise by default this fixture creates a temporary directory that is used to run the test function and is cleaned up afterwards.
* http_headers: Dict mapping header names to environment variable names. These are the headers used in file download requests, and the environment variables can be used to specify the defaults.
* proxies: Dict mapping proxy names to environment variables.
* import_paths: Path to file that contains a list of WDL import paths (one per line). Defaults to `None`.
* import_dirs: List of WDL import paths. Loads these from the file specified by `import_paths` if any, otherwise uses the parent directory of the test module.
* java_bin: Path to the java executable. Defaults to `$JAVA_HOME/bin/java`.
* java_args: String containing arguments to pass to Java.
* cromwell_jar_file: By default this fixture first looks for the `$CROMWELL_JAR` enironment variable. It then searches the classpath for a JAR file that begins with 'cromwell' (case-insensitive). If the JAR file is not found in either place, it is expected to be located in the same directory as the tests are executed from (i.e. `./cromwell.jar`).
* cromwell_args: String containing arguments to pass to Cromwell.

These fixtures have sensible defaults, but can be overridden in two different ways:

* Define them in the test module
* Define them in a conftest.py module at or above the level of the test modules

### Environment Variables

The fixtures above can utilize environment variables. Technically, none are required and this can be run without them if your environment is setup to meet the needs of each fixture. Many can be set in other ways, like overriding a fixture. Below is a table of possible variables you can set though and which are recommended:

| variable name | recommended | description |
| ------------- | ----------- | ----------- |
| `CROMWELL_JAR` | yes         | path to cromwell jar. |
| `JAVA_HOME` | yes | path to java executable |
| `CACHE_DIR` | no, use for testing and development | where to store test data, default is temp. If you define this, use an absolute path. |
| `EXECUTION_DIR` | no, use for testing and development | where cromwell should execute, default is temp. If you define this, use an absolute path. | 
| `CROMWELL_CONFIG` | no, only when needed | define a cromwell configuration file to use for the test run |
| `LOGLEVEL` | no, use for debug | default is `WARNING`. Can set to `INFO`, `DEBUG`, `ERROR` to enable `pytest-wdl` logger output at various levels. |
| `CLASSPATH` | only if you do not specify `CROMWELL_JAR` | java classpath |
| `CROMWELL_ARGS` | no, only when needed | add additional arguments into the cromwell run command |

Remember that environment variables can be set multiple ways, including inline before running the command, such as `EXECUTION_DIR=$(pwd) python -m pytest -s tests/`

### Workflow test data

Workflow test data files can be provided by the `workflow_data` fixture, and are defined in the `test_data.json` file.

#### test_data.json

Test data is specified in a JSON file of the format:

```json
{
  "name": {
    "url": "http://foo.com/path/to/file",
    "path": "localized/path",
    "name": "filename",
    "contents": "test",
    "type": "vcf|bam",
    "allowed_diff_lines": 2
  }
}
```

* url: Path to the file on a remote server from which it is downloaded if it can't be found locally; ignored if `fixture` is specified, or if the file already exists locally
* path: Relative path to the file within the test data directory; ignored if `fixture` is specified
* name: Name of the file - used when path is not specified, and also used to request the file from a location under the tests/ directory when it is in a directory structure as defined by the [pytest-datadir-ng](https://pypi.org/project/pytest-datadir-ng/) plugin.
* contents: The contents of the file; the file will be written to `path` at runtime
* type: For use with output data files; specifies the file type for special handling by a plugin
* allowed_diff_lines: For use with output data files; specifies the number of lines that can be different between the actual and expected outputs and still have the test pass

#### Data Types

Available types:

- default
  - this is the default type if one is not specified. It can handle raw text files, as well as gzip compressed files.
- vcf
  - this considers only the first 5 columns in a VCF since the qual scores can vary slightly on different hardware.
- bam*
  - This converts BAM to SAM for diff comparison, enabling `allowed_diff_lines` usage since most BAM creation adds a command header or other comments that are expected to be different.
  - This also replaces random UNSET-\w*\b type IDs that samtools often adds

\* requires extra dependencies to be installed, see 
[Installing Data Type Plugins](#installing-data-type-plugins)

When comparing outputs of a test execution against an expected output file, that comparison is defined in the `expected` argument of the `workflow_runner`, where the key should be the output variable of the WDL workflow and the value is the expected value. This can be an accession into the workflow_data fixture, which resolves by looking at the test_data.json file. If the file is a binary format that requires special handling (not gzip, this is supported by default), such as BAM, =then we can specify that as the type (`"type": "bam"`) so that our comparison knows to convert that file into a temporary SAM file so we can do a diff. This enables specifying `allowed_diff_lines` attribute since BAM/SAM files often capture the command run as a header which will typically be different.

The `type` attribute is ignored for input data files defined in workflow_data.

##### Creating New Data Types

To create a new data type plugin, add a module in the data_types directory.

This should subclass the `pytest_wdl.core.DataFile` class and override its methods for _assert_contents_equal() and _diff to define the behavior for this file type.

Next, add an entry point in setup.py. If the data type requires more dependencies be installed, make sure to use a Try/Except ImportError to warn about this and add the extra dependencies under the setup.py's `extras_require`. For example:

```python
setup(
    ...,
    entry_points={
        "pytest_wdl": [
            "bam = pytest_wdl.data_types.bam:BamDataFile"
        ]
    },
    extras_require={
        "bam": ["pysam"]
    }
)
```

In this example, the extra dependencies can be installed with `pip install pytest-wdl[bam]`.

## Development

To develop pytest-wdl, clone the repository and install all the dependencies:

```
$ git clone https://github.com/EliLillyCo/pytest-wdl.git
$ pip install -r requirements.txt
```

To run the full build and unit tests, run:

`make`
