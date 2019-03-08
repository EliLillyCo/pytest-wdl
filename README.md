# pytest-cromwell

This package provides fixtures to enable writing tests that execute WDL workflows via cromwell and check the generated output against expected values.

## Fixtures

The two main fixtures are:

* test_data: Provides access to data files for use as inputs to a workflow, and for comparing to workflow output. Data files may be stored locally or in Artifactory. The local cache directory may be specified using the `TEST_DATA_DIR` environment variable; otherwise a temporary directory is used and is deleted at the end of the test session. Data are described in a JSON file. File data are described as a hash with the following keys:
    * url: The remote URL.
    * path: The local path to the file.
    * type: The file type. This is optional and only needs to be provided for certain types of files that are handled specially for the sake of comparison. The only supported value is "vcf".
* cromwell_harness: Provides an object with a `run_workflow` method that calls a WDL workflow using Cromwell with given inputs, parses out the results, and compares them against expected values.

There are also fixtures for specifying required inputs to the two main fixtures. These fixtures have sensible defaults, but can be overridden either by redefining them in the test module, or by using the `pytest.mark.param.parametrize` decoration.

* project_root: The root directory of the project. All relative paths are relative to this directory.
* test_data_file: Path to the JSON file that defines the test data files. Defaults to `/tests/test_data.json`.
* test_data_dir: Local directory for caching test data. The `TEST_DATA_DIR` environment varianble takes precedence, otherwise by default this fixture creates a temporary directory that is used to cache test data for the test module.
* default_env: Defines the default environment variable values.
* http_headers: Dict mapping header names to values. These are the headers used in file download requests. The default is `{"X-JFrog-Art-Api": "TOKEN"}`.
* proxies: Dict mapping proxy names to environment variables. The default is `{"http": "HTTP_PROXY", "https": "HTTPS_PROXY"}`.
* import_paths: Path to file that contains a list of WDL import paths (one per line).
* java_bin: Path to the java executable. Defaults to `$JAVA_HOME/bin/java`.
* cromwell_jar_file: By default this fixture first looks for the `CROMWELL_JAR` enironment variable. It then searches the classpath for a JAR file that begins with 'cromwell' (case-insensitive). If the JAR file is not found in either place, it is expected to be located in the same directory as the tests are executed from (i.e. `./cromwell.jar`).


## Example

```python
import pytest

@pytest.fixture(scope="module")
def project_root():
    return "../.."

@pytest.mark.parametrize("test_data_file", ["tests/mytestdata.json"])
def test_variant_caller(test_data, cromwell_harness):
    inputs = {
        "bam": test_data["bam"],
        "bai": test_data["bai"]
    }
    expected = {
        "vcf": test_data["vcf"]
    }
    cromwell_harness.run_workflow(
        "variant_caller/variant_caller.wdl",
        "call_variants",
        inputs,
        expected
    )
```