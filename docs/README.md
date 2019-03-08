# Development Docs

## How to upload a release to Artifactory 

First, you need to setup your `~/.pypirc` to add the repository information:

```commandline
[distutils]
index-servers=
  omics-pypi
  
[omics-pypi]
repository: https://elilillyco.jfrog.io/elilillyco/api/pypi/omics-pypi-lc
username: <Artifactory Username - email>
password: <Artifactory API Token>
```

You will need the following dependencies installed in order to build 
and upload the package:

```commandline
pip install setuptools_scm twine
```

- `setuptool_scm` allows us to build the package using the scm information for versioning.
- `twine` is a preferred package for secure uploads over using setuptools to do the upload.

Then you can build the package:

Clone the repository and run the following command:

`python setup.py sdist bdist_wheel --universal`

Then we can use `twine` to upload to PyPi:

`twine upload -r omics-pypi dist/*`

