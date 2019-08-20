# User manual

pytest-wdl is a plugin for the [pytest](https://docs.pytest.org/en/latest/) unit testing framework that enables testing of workflows written in [Workflow Description Language](https://github.com/openwdl). Test workflow inputs and expected outputs are [configured](#test_data) in a `test_data.json` file. Workflows are run by one or more [executors](#executors). By default, actual and expected outputs are compared by MD5 hash, but data type-specific comparisons are provided. Data types and executors are pluggable and can be provided via third-party packages. 

## Fixtures

All functionality of pytest-wdl is provided via [fixtures](https://docs.pytest.org/en/latest/fixture.html). As long as pytest-wdl is in your PYTHONPATH, its fixtures will be discovered and made available when you run pytest.

The two most important fixtures are:

* [workflow_data](#test_data): Provides access to data files for use as inputs to a workflow, and for comparing to workflow output.
* [workflow_runner](#executors): Given a WDL workflow, inputs, and expected outputs, runs the workflow using one or more executors and compares actual and expected outputs.

There are also [several additional fixtures](#configuration) used for configuration of the two main fixtures. In most cases, the default values returned by these fixtures "just work." However, if you need to override the defaults, you may do so either directly within your test modules, or in a [conftest.py](https://docs.pytest.org/en/2.7.3/plugins.html) file.

## Test data

Typically, workflows require inputs and generate outputs. Beyond simply ensuring that a workflow runs successfully, we often want to additionally test that it reproducibly generates the same results given the same inputs.

Test inputs and outputs are configured in a `test_data.json` file that is stored in the same directory as the test module. This file has one entry for each input/output. Primitive types map as expected from JSON to Python to WDL. For example, the following `test_data.json` file defines an integer input that is loaded as a Python `int` and then maps to the WDL `Integer` type when passed as an input parameter to a workflow:

```json
{
  "input_int": 42
}
```

### Files

For file inputs and outputs, pytest-wdl offers several different options. Test data files may be located remotely (identified by a URL), located within the test directory (using the folder hierarchy established by the [datadir-ng](https://pypi.org/project/pytest-datadir-ng/) plugin), located at an arbitrary local path, or defined by specifying the file contents directly within the JSON file. Files that do not already exist locally are localized on-demand and stored in the [cache directory](#cache).

Some additional options are available only for expected outputs, in order to specify how they should be compared to the actual outputs.

Below is an example `test_data.json` file that demonstrates different ways to define input and output data files:

```json
{
  "bam": {
    "url": "http://example.com/my.bam",
    "http_headers": {
      "auth_token": "TOKEN"
    }
  },
  "reference": {
    "path": "${REFERENCE_DIR}/chr22.fa"
  },
  "sample": {
    "path": "samples.vcf",
    "contents": "sample1\nsample2"
  },
  "output_vcf": {
    "name": "output.vcf",
    "type": "vcf",
    "allowed_diff_lines": 2
  }
}
```

The available keys for configuring file inputs/outputs are:

* name: Filename to use when localizing the file; when none of {url, path, contents} are defined, `name` is also used to search for the data file within the tests directory, using the same directory structure defined by the [datadir-ng](https://pypi.org/project/pytest-datadir-ng/) fixture.
* path: The local path to the file. If the path does not already exist, the file will be localized to this path. Typically, this is defined as a relative path that will be prefixed with the [cache directory](#cache) path. Environment variables can be used to enable the user to configure an environment-specific path.
* env: The name of an environment variable in which to look up the local path of the file.
* url: A URL that can be resolved by [urllib](https://docs.python.org/3/library/urllib.html).
    * http_headers: Optional dict mapping header names to values. These headers are used for file download requests. Keys are header names and values are either strings (environment variable name) or dict with the following keys:
        * env: The name of an environment variable in which to look up the header value.
        * value: The header value; only used if an environment variable is not specified or is unset.
* contents: The contents of the file, specified as a string.

In addition, 

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



The local cache directory may be specified using the `CACHE_DIR` environment variable; otherwise a temporary directory is used and is deleted at the end of the test session. 


* user_config_file: Provides the path to the user config file. Looks for the file path in the `user_config` environment variable, and falls back to looking for the file in the default location ($HOME/pytest_user_config.json).
* user_config: Provides a session WdlConfig object that is boostrapped from the user_config_file if one is specified.
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
| `PYTEST_user_config`  | yes         | path to user config file; can also be specified to 
| `PYTEST_WDL_CACHE_DIR` | no, use for testing and development | where to store test data, default is temp. If you define this, use an absolute path. |
| `PYTEST_WDL_EXECUTION_DIR` | no, use for testing and development | where cromwell should execute, default is temp. If you define this, use an absolute path. | 
| `LOGLEVEL` | no, use for debug | default is `WARNING`. Can set to `INFO`, `DEBUG`, `ERROR` to enable `pytest-wdl` logger output at various levels. |
| `JAVA_HOME` | yes | path to java executable |
| `CLASSPATH` | only if you do not specify `CROMWELL_JAR` | java classpath |
| `CROMWELL_JAR` | yes         | path to cromwell jar. |
| `CROMWELL_CONFIG` | no, only when needed | define a cromwell configuration file to use for the test run |
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
    "allowed_diff_lines": 2,
    "http_headers": {
      "header1": {
        "env": "HEADER1",
        "value": "FOOBAR"
      }
    }
  }
}
```

* url: Path to the file on a remote server from which it is downloaded if it can't be found locally; ignored if `fixture` is specified, or if the file already exists locally
* path: Relative path to the file within the test data directory; ignored if `fixture` is specified
* name: Name of the file - used when path is not specified, and also used to request the file from a location under the tests/ directory when it is in a directory structure as defined by the [pytest-datadir-ng](https://pypi.org/project/pytest-datadir-ng/) plugin.
* contents: The contents of the file; the file will be written to `path` at runtime
* type: For use with output data files; specifies the file type for special handling by a plugin
* allowed_diff_lines: For use with output data files; specifies the number of lines that can be different between the actual and expected outputs and still have the test pass
* http_headers: Map of http headers to add to the request when fetching contents from `url`. Keys are header names and values are maps consiting of one or both of two keys:
    * env: The name of an environment variable to look in for the value.
    * value: The value to use if `env` is not provided or the environment variable is unset.

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