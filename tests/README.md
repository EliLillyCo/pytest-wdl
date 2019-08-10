# Test Data Type

expected output file data types are plugins. To test this, make sure to install the extras_requires for bam types.

`pip install pytest-wdl[bam]`

If on a development copy, you can use `pip install .[bam]` from the top-level.

Then run the test:

`python -m pytest .`


## No Random BAM test

This test is for removing samtools random UNSET IDs when comparing. The two test files are from the same bam, but one had the UNSET-* IDs replaced. This is the only difference, so comparing them with pytest-wdl should evaluate as equal.
