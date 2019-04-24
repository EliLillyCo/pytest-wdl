# Test Data Type

expected output file data types are plugins. To test this, make sure to 
install the extras_requires for bam types.

`pip install pytest-cromwell[bam]`

If on a development copy, you can use `pip install .[bam]` from the top-level.

Then run the test:

`python -m pytest .`
