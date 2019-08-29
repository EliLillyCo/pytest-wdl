# Changes

## Development

## v1.0.1 (2019.08.28)

* Workflow files are first searched in the current test context directory, so it is no longer necessary to pass a relative path from the project root to workflow_runner
* Defined the concept of a module root, which is the first directory (starting from the test context directory) up that contains a "tests" folder
    * WDL files under the current module root are imported by default if an import_paths.txt file is not specified
    * The workflow_data_descriptor_file fixture is updated to correctly look for test_data.json in the tests/ directory of the current module
* Complex workflow inputs are now serialized properly, which ensures that data files in arrays or dicts are localized

## v1.0.0 (2019.08.23)

* First public release of pytest-wdl
