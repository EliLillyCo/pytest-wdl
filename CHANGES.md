# Changes

## Development


## v1.4.1 (2020.11.17)
* Replaces remote file localization method for adding HTTP headers to only add headers on initial request and not redirects.
* Updated `dxpy` minimum to `0.297.1` to be able to use `cryptography` version `2.3` ([#106](https://github.com/EliLillyCo/pytest-wdl/pull/106))
* Upgraded `bleach` to `3.1.5` ([#138](https://github.com/EliLillyCo/pytest-wdl/pull/138))
* Constrains `pytest` version `<=5.3.5` to avoid breaking changes in `pytest` ([#139](https://github.com/EliLillyCo/pytest-wdl/pull/139))
* Upgrades `Cromwell` to version `53.1` in test setup and documentation.

## v1.4.0 (2020.02.26)

* Added support for YAML data and configuration files (#116)
* Added a Cromwell Server executor (thanks @pamagee!)
* Added ability to specify tests in JSON/YAML (#117)
* Updated docs and testing to latest version of Cromwell (v48)
* Added an optional `callback` parameter to `workflow_runner`
* Fix miniwdl executor when there are no inputs (thanks @mlin!)

## v1.3.0 (2020.02.14)

* Added support for testing workflows on DNAnexus using [dxWDL](https://github.com/dnanexus/dxWDL)
* Using DNAnexus-related features will cause the user to be automatically logged in to their account if not already logged in (log-in is interactive unless account credentials or a token are specified in the config file)
* Enhanced support for [miniwdl]() and made it the default executor (to configure different default executor(s), see the [manual](https://pytest-wdl.readthedocs.io/en/stable/manual.html#configuration))
* Generate requirements.txt using `pip freeze`. Note that miniwdl is pegged to a specific version (0.6.4) because we depend on internal functionality; this limitation will be fixed in a future release
* Many improvements to the manual (thanks @mlin for suggestions), including a new "quickstart" example project
* Bugfix: within-project local data file resolution was implemented incorrectly for the case where there are packages (i.e. `__init__.py` files) in the `tests/` folder - it is now fixed.
    
## v1.2.1 (2019.12.12)

* Fixes #93 - ensures parent directories exist when localizing a file

## v1.2.0 (2019.12.04)

* Fix #86 - enable test_data.json file to be located in the same directory as the WDL file
* When comparing BAM files, by default only compare HD, SQ, and RG headers
* Enhance the error message that is displayed when a workflow fails
* Add ability to validate data file digests
* Optionally show progress bar when downloading data file
* Update miniwdl minimum version to 0.5.2, and update the miniwdl executor to use `docker swarm`
* Update xphyle minimum version to 4.1.3
* Other bugfixes

## v1.1.1 (2019.09.27)

* Fixes `license` entry in `setup.py` for proper rendering to release to PyPI.

## v1.1 (2019.09.26)

* Add ability to create executor plugins
* Add ability to specify which executor (including multiple executors) to use by default and on a test-specific basis
* Add experimental support for [Miniwdl](https://github.com/chanzuckerberg/miniwdl) executor
* Swtich from delegator.py to [subby](https://github.com/jdidion/subby) for executing subprocesses
* Fixes for path finding - test data and imports are now resolved correctly in the cases of "standard" project setups
* Tests are isolated from any local configuration
* Added ability to specify custom URL scheme handlers, and added a handler for files hosted on DNAnexus
* Fixed the makefile to correctly run all the intended targets
* Lots of fixes and improvements to VCF and BAM comparison (see updated docs)
* Add ability to modify comparison options on DataFiles (set_compare_opts method)
* Add support for arbitrary objects in test_data.json
* Improve comparison of expected to actual values, including support for None, dict, and list values
* Add support for comparing gzipped files, using [xphyle](https://github.com/jdidion/xphyle) to detect file format
* Improve assertion error messages
* Add json data type and add ability to localize dict contents as JS

## v1.0.1 (2019.08.28)

* Workflow files are first searched in the current test context directory, so it is no longer necessary to pass a relative path from the project root to workflow_runner
* Defined the concept of a module root, which is the first directory (starting from the test context directory) up that contains a "tests" folder
    * WDL files under the current module root are imported by default if an import_paths.txt file is not specified
    * The workflow_data_descriptor_file fixture is updated to correctly look for test_data.json in the tests/ directory of the current module
* Complex workflow inputs are now serialized properly, which ensures that data files in arrays or dicts are localized

## v1.0.0 (2019.08.23)

* First public release of pytest-wdl
