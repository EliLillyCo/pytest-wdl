# pytest-cromwell

This package provides fixtures to enable writing tests that execute WDL workflows via Cromwell and check the generated output against expected values.

## Dependencies

* Java 1.8+
* [Cromwell](https://github.com/broadinstitute/cromwell/releases/tag/38) JAR file
* [Docker](https://www.docker.com/get-started) daemon (if your WDL tasks depend on Docker images)

Other python dependencies are installed when you install the library.

## Installation

### Install from Artifactory PyPi

The module is stored in the private PyPi repository `elilillyco.jfrog.io/elilillyco/api/pypi/omics-pypi-lc/simple`

#### Preferred Artifactory Install Method

To add this repo to your environment for all future installs, edit your `~/.pip/pip.conf` file like below, adding your username and password for Artifactory which is your email and the Artifactory API token:

```
[global]
index-url = https://pypi.org/simple
extra-index-url =
    https://<email>:<artifactory_token>@elilillyco.jfrog.io/elilillyco/api/pypi/omics-pypi-lc/simple
```

Then you can pip install the module:

```commandline
pip install pytest_cromwell
```

#### One-Time Artifactory Install

If you just want to do this one-time, you can embed the extra-index-url into the pip command. You can also leave out the auth details and it will interactively prompt for them:

```commandline
pip install --extra-index-url https://elilillyco.jfrog.io/elilillyco/api/pypi/omics-pypi-lc/simple pytest_cromwell
```
Which will then prompt for your username and password, the Artifactory email and token.

### Install from source

You can to clone the repository and install:

```
python setup.py install
```

Or use pip to install from github:

```commandline
pip install git+https://github.com/elilillyco/lrl_cromwell_test_runner.git
```

## Installing Data Type Plugins

Data Types for expected output comparison are plugins. They are loaded on-demand and if they require external dependencies, you must install those.

data types that require an extras installation:
- bam

To install the dependencies for a data type that has extra dependencies:

`pip install pytest-cromwell[<data_type>]`

To do this locally, you can clone the repo and run:

`pip install -e .[<data_type>]`

To install pytest-cromwell and **all** extras dependencies:

`pip install pytest-cromwell[all]`

## Usage

```python
import pytest

@pytest.fixture(scope="module")
def project_root():
    return "../.."

@pytest.fixture(scope="module")
def test_data_file():
    return "tests/mytestdata.json"

def test_variant_caller(test_data, workflow_runner):
    inputs = {
        "bam": test_data["bam"],
        "bai": test_data["bai"]
    }
    expected = {
        "vcf": test_data["vcf"]
    }
    workflow_runner(
        "variant_caller/variant_caller.wdl",
        "call_variants",
        inputs,
        expected
    )
```

## Fixtures

The main fixtures are:

* test_data: Provides access to data files for use as inputs to a workflow, and for comparing to workflow output. Data files may be stored locally or remotely. The local cache directory may be specified using the `TEST_DATA_DIR` environment variable; otherwise a temporary directory is used and is deleted at the end of the test session. Data are described in a JSON file. File data are described as a hash with the following keys. At least one of {url, path, contents} is required.
    * url: Optional; the remote URL.
    * path: Optional; the local path to the file.
    * contents: Optional; the contents of the file, specified as a string.
    * type: The file type. This is optional and only needs to be provided for certain types of files that are handled specially for the sake of comparison.
    * allowed_diff_lines: optional and only used for outputs comparison.
* cromwell_harness: Provides a CromwellHarness object that runs a WDL workflow using Cromwell with given inputs, parses out the results, and compares them against expected values. The `run_workflow` method has the following parameters:
    * wdl_script: The WDL script to execute. The path should be relative to the project root.
    * workflow_name: The name of the workflow in the WDL script.
    * inputs: Object that will be serialized to JSON and provided to Cromwell as the workflow inputs.
    * expected: Dict mapping output parameter names to expected values. For file outputs, the expected value can be specified as above (i.e. a URL, path, or contents). Any outputs that are not specified are ignored.
    * Additional keyword arguments:
        * execution_dir: Directory in which to execute the workflow. Defaults to cwd. Ignored if `run_in_tempdir is True`. *Deprecated: will be removed in v1.0*
        * inputs_file: Specify the inputs.json file to use, or the path to the inputs.json file to write, instead of a temp file.
        * imports_file: Specify the imports file to use, or the path to the imports zip file to write, instead of a temp file.
        * java_args: Override the default Java arguments.
        * cromwell_args: Override the default Cromwell arguments.
* workflow_runner: This is an alternative to cromwell_harness. It provides a callable and automatically determines the execution_dir based on the test_execution_dir fixture.

There are also fixtures for specifying required inputs to the two main fixtures. These fixtures have sensible defaults, but can be overridden  by redefining them in the test module.

* project_root: The root directory of the project. All relative paths are relative to this directory.
* test_data_file: Path to the JSON file that defines the test data files. Defaults to `tests/test_data.json`.
* test_data_dir: Local directory for caching test data. The `TEST_DATA_DIR` environment variable takes precedence, otherwise by default this fixture creates a temporary directory that is used to cache test data for the test module.
* test_execution_dir: Local directory in which tests are executed. The `TEST_EXECUTION_DIR` environment variable takes precedence, otherwise by default this fixture creates a temporary directory that is used to run the test function and is cleaned up afterwards.
* http_headers: Dict mapping header names to environment variable names. These are the headers used in file download requests, and the environment variables can be used to specify the defaults. The default is `{"X-JFrog-Art-Api": "TOKEN"}`.
* proxies: Dict mapping proxy names to environment variables. The default is `{"http": "HTTP_PROXY", "https": "HTTPS_PROXY"}`.
* import_paths: Path to file that contains a list of WDL import paths (one per line). Defaults to `None`.
* import_dirs: List of WDL import paths. Loads these from the file specified by `import_paths` if any, otherwise uses the parent directory of the test module.
* java_bin: Path to the java executable. Defaults to `$JAVA_HOME/bin/java`.
* java_args: String containing arguments to pass to Java.
* cromwell_jar_file: By default this fixture first looks for the `$CROMWELL_JAR` enironment variable. It then searches the classpath for a JAR file that begins with 'cromwell' (case-insensitive). If the JAR file is not found in either place, it is expected to be located in the same directory as the tests are executed from (i.e. `./cromwell.jar`).
* cromwell_args: String containing arguments to pass to Cromwell.

### Environment Variables

The fixtures above can utilize environment variables. Technically, none are required and this can be run without them if your environment is setup to meet the needs of each fixture. Many can be set in other ways, like overriding a fixture. Below is a table of possible variables you can set though and which are recommended:

| variable name | recommended | description |
| ------------- | ----------- | ----------- |
| `CROMWELL_JAR` | yes         | path to cromwell jar. |
| `HTTPS_PROXY` | required if behind proxy | |
| `HTTP_PROXY`  | required if behind proxy | |
| `TOKEN`       | yes         | currently this is an Artifactory token which is needed to fetch test data from the generic repo |
| `JAVA_HOME` | yes | path to java executable |
| `TEST_DATA_DIR` | no, use for testing and development | where to store test data, default is temp. If you define this, use an absolute path. |
| `TEST_EXECUTION_DIR` | no, use for testing and development | where cromwell should execute, default is temp. If you define this, use an absolute path. | 
| `CROMWELL_CONFIG` | no, only when needed | define a cromwell configuration file to use for the test run |
| `LOGLEVEL` | no, use for debug | default is `WARNING`. Can set to `INFO`, `DEBUG`, `ERROR` to enable `pytest-cromwell` logger output at various levels. |
| `CLASSPATH` | only if you do not specify `CROMWELL_JAR` | java classpath |
| `CROMWELL_ARGS` | no, only when needed | add additional arguments into the cromwell run command |

Remember that environment variables can be set multiple ways, including inline before running the command, such as `TEST_EXECUTION_DIR=$(pwd) python -m pytest -s tests/`

### test_data Data Types

available types:
- default
  - this is the default type if one is not specified. It can handle raw text files, as 
  well as gzip compressed files.
- vcf
  - this considers only the first 5 columns in a VCF since the qual scores can 
  vary slightly on different hardware.
- bam*
  - This converts BAM to SAM for diff comparison, enabling `allowed_diff_lines`
  usage since most BAM creation adds a command header or other comments that are 
  expected to be different.

\* requires extra dependencies to be installed, see 
[Installing Data Type Plugins](#installing-data-type-plugins)

When comparing outputs of a test execution against an expected output file, 
that comparison is defined in the `expected` argument of the `workflow_runner`, 
where the key should be the output variable of the WDL workflow and the value 
is the expected value. This can be an accession into the test_data fixture, which 
resolves by looking at the test_data file. If the file is a binary format that 
requires special handling (not gzip, this is supported by default), such as BAM, 
then we can specify that as the type (`"type": "bam"`) so that our comparison knows
to convert that file into a temporary SAM file so we can do a diff. This enables 
specifying `allowed_diff_lines` attribute since BAM/SAM files often capture 
the command run as a header which will typically be different.

**Do not** use the `type` attribute for inputs in the test_data.

## Creating New Data Types

To create a new data type plugin, add a module in the data_types directory.

This should subclass the `pytest_cromwell_core.utils.DataFile` class and override its methods for _assert_contents_equal() and _diff to define the behavior for this file type. Additionally a class attribute should be set to override `name` which is used as the key.

The `name` and the module file name should ideally be the same and the module name is what is used when defining the type in the test_data.json file.

If the data type requires more dependencies be installed, make sure to use a Try/Except ImportError to warn about this and add the extra dependencies under the setup.py's `extras_require` like:

```python
extras_require={
    'data_type': ['module']
}
```

which enables installing these extra dependencies with `pip install pytest-cromwell[$data_type]`

See the `bam` type for an example that fully exercises these changes for adding a new type.
