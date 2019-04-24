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

To add this repo to your environment for all future installs, edit your `~/.pip/pip.conf`
file like below, adding your username and password for Artifactory which is 
your email and the Artifactory API token:

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

If you just want to do this one-time, you can embed the extra-index-url into 
the pip command. You can also leave out the auth details and it will interactively prompt for them:

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

Data Types for expected output comparison are plugins. They are loaded on-demand
and if they require external dependencies, you must install those.

data types that require an extras installation:
- bam

To install the dependencies for a data type that has extra dependencies:

`pip install pytest-cromwell[<data_type>]`

To do this locally, you can clone the repo and run:

`pip install -e .[<data_type>]`


## Fixtures

The main fixtures are:

* test_data: Provides access to data files for use as inputs to a workflow, and for comparing to workflow output. Data files may be stored locally or remotely. The local cache directory may be specified using the `TEST_DATA_DIR` environment variable; otherwise a temporary directory is used and is deleted at the end of the test session. Data are described in a JSON file. File data are described as a hash with the following keys. At least one of {url, path, contents} is required.
    * url: Optional; the remote URL.
    * path: Optional; the local path to the file.
    * contents: Optional; the contents of the file, specified as a string.
    * type: The file type. This is optional and only needs to be provided for certain types of files that are handled specially for the sake of comparison. Currently, the only supported value is "vcf".
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

## Example

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
