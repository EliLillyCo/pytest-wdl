# pytest-cromwell

This package provides fixtures to enable writing tests that execute WDL workflows via cromwell and check the generated output against expected values.

## Fixtures

The two main fixtures are:

* test_data: Provides access to data files for use as inputs to a workflow, and for comparing to workflow output. Data files may be stored locally or in Artifactory. Data are described in a JSON file. File data are described as a hash with the following keys:
    * url: The remote URL.
    * path: The local path to the file.
    * type: The file type. This is optional and only needs to be provided for certain types of files that are handled specially for the sake of comparison. The only supported value is "vcf".
* cromwell_harness: Provides an object with a `run_workflow` method that calls a WDL workflow using Cromwell with given inputs, parses out the results, and compares them against expected values.

## Example

```python
import pytest
@pytest.mark.parameterize("test_data_file", ["tests/test_data.json"])
@pytest.mark.parameterize("import_paths", ["tests/import_paths.txt"])
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
