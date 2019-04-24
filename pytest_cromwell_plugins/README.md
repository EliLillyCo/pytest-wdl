# Plugins


## Data Types

To create a new data type plugin, add a module in the data_types directory.

This should subclass the `pytest_cromwell_core.utils.DataFile` class and override 
its methods for _assert_contents_equal() and _diff to define the behavior for this 
file type. Additionally a class attribute should be set to override `name` which 
is used as the key.

The `name` and the module file name should ideally be the same and the module 
name is what is used when defining the type in the test_data.json file.

If the data type requires more dependencies be installed, make sure to use a 
Try/Except ImportError to warn about this and add the extra dependencies under 
the setup.py's `extras_require` like:

```python
extras_require={
    'data_type': ['module']
}
```

which enables installing these extra dependencies with `pip install pytest-cromwell[$data_type]`

See the `bam` type for an example that fully exercises these changes for adding 
a new type.