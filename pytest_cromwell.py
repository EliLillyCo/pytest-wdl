#! /usr/bin/env python
"""
Fixtures for writing tests that execute WDL workflows using Cromwell.
"""
import contextlib
import copy
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request

import delegator
import pytest


class DataFile:
    """
    A data file, which may be located locally, remotely, or represented as a string.

    Args:
        path: Path to a local file. If this file doesn't exist, it will be created by
            either downloading the given URL or persisting the given file contents.
        url: A URL of a remote file.
        contents: The contents of the file.
        local_dir: Directory where a file should be created, if `path` is not provided.
        http_headers: Headers to add to the requrests to download the remote file from
            Artifactory.
        proxies: Proxies to add to the requests to download the remote file from
            Artifactory.
    """
    def __init__(
        self, path=None, url=None, contents=None, local_dir=".", http_headers=None,
        proxies=None, allowed_diff_lines=0
    ):
        self.url = url
        self.contents = contents
        self.http_headers = http_headers
        self.proxies = proxies
        self.allowed_diff_lines = allowed_diff_lines
        if path:
            if not os.path.isabs(path):
                path = os.path.abspath(os.path.join(local_dir, path))
            self._path = path
        elif url:
            filename = url.rsplit("/", 1)[1]
            self._path = os.path.abspath(os.path.join(local_dir, filename))
        else:
            self._path = tempfile.mkstemp(dir=local_dir)

    @property
    def path(self):
        if not os.path.exists(self._path):
            self._persist()
        return self._path

    def assert_contents_equal(self, other):
        """
        Assert the contents of two files are equal.

        If `allowed_diff_lines == 0`, files are compared using MD5 hashes, otherwise
        their contents are compared using the linux `diff` command.

        Args:
            other: A `DataFile` or string file path.
        """
        allowed_diff_lines = self.allowed_diff_lines

        if isinstance(other, str):
            other_path = other
        else:
            other_path = other.path
            allowed_diff_lines = max(allowed_diff_lines, other.allowed_diff_lines)

        self._assert_contents_equal(self.path, other_path, allowed_diff_lines)

    @classmethod
    def _assert_contents_equal(cls, file1, file2, allowed_diff_lines):
        if allowed_diff_lines:
            cls._diff_contents(file1, file2, allowed_diff_lines)
        else:
            cls._compare_hashes(file1, file2)

    @classmethod
    def _diff_contents(cls, file1, file2, allowed_diff_lines):
        if file1.endswith(".gz"):
            with _tempdir() as temp:
                temp_file1 = os.path.join(temp, "file1")
                temp_file2 = os.path.join(temp, "file2")
                delegator.run(
                    "gunzip -c {} > {}".format(file1, temp_file1), block=True
                )
                delegator.run(
                    "gunzip -c {} > {}".format(file2, temp_file2), block=True
                )
                diff_lines = cls._diff(temp_file1, temp_file2)
        else:
            diff_lines = cls._diff(file1, file2)

        if diff_lines > allowed_diff_lines:
            raise AssertionError(
                "{} lines (which is > {} allowed) are different between files {}, "
                "{}".format(diff_lines, allowed_diff_lines, file1, file2)
            )

    @classmethod
    def _diff(cls, file1, file2):
        cmd = "diff -y --suppress-common-lines {} {} | grep '^' | wc -l".format(
            file1, file2
        )
        return int(delegator.run(cmd, block=True).out)

    @classmethod
    def _compare_hashes(cls, file1, file2):
        with open(file1, "rb") as inp1:
            file1_md5 = hashlib.md5(inp1.read()).hexdigest()
        with open(file2, "rb") as inp2:
            file2_md5 = hashlib.md5(inp2.read()).hexdigest()
        if file1_md5 != file2_md5:
            raise AssertionError(
                "MD5 hashes differ between expected identical files "
                "{}, {}".format(file1, file2)
            )

    def _persist(self):
        if self.url:
            req = urllib.request.Request(self.url)
            if self.http_headers:
                for name, value in self.http_headers.items():
                    req.add_header(name, value)
            if self.proxies:
                for proxy_type, url in self.proxies.items():
                    req.set_proxy(url, proxy_type)
            rsp = urllib.request.urlopen(req)
            with open(self._path, "wb") as out:
                shutil.copyfileobj(rsp, out)
        elif self.contents:
            with open(self._path, "wt") as out:
                out.write(self.contents)
        else:
            raise ValueError(
                "Either a url, file contents, or a local file must be provided"
            )


class VcfDataFile(DataFile):
    @classmethod
    def _assert_contents_equal(cls, file1, file2, allowed_diff_lines):
        cls._diff_contents(file1, file2, allowed_diff_lines)

    @classmethod
    def _diff(cls, file1, file2):
        """
        Special handling for VCF files to only compare the first 5 columns.

        Args:
            file1:
            file2:
        """
        with _tempdir() as temp:
            cmp_file1 = os.path.join(temp, "file1")
            cmp_file2 = os.path.join(temp, "file2")
            job1 = delegator.run(
                f"cat {file1} | grep -vP '^#' | cut -d$'\t' -f 1-5 > {cmp_file1}"
            )
            job2 = delegator.run(
                f"cat {file2} | grep -vP '^#' | cut -d$'\t' -f 1-5 > {cmp_file2}"
            )
            for job in (job1, job2):
                job.block()
            return super()._diff(cmp_file1, cmp_file2)


DATA_TYPES = {
    "vcf": VcfDataFile,
    "default": DataFile
}


class Data:
    """
    Class that manages test data.

    Args:
        data_dir: Directory where test data files should be stored temporarily, if
            they are being downloaded from a remote server.
        data_file: JSON file describing the test data.
        http_headers: Http(s) headers.
        proxies: Http(s) proxies.
    """
    def __init__(self, data_dir, data_file, http_headers, proxies):
        self.data_dir = data_dir
        self.http_headers = http_headers
        self.proxies = proxies
        self._values = {}
        with open(data_file, "rt") as inp:
            self._data = json.load(inp)

    def __getitem__(self, name):
        if name not in self._values:
            if name not in self._data:
                raise ValueError("Unrecognized name {}".format(name))
            value = self._data[name]
            if isinstance(value, dict):
                data_file_class = DATA_TYPES[value.pop("type", "default")]
                self._values[name] = data_file_class(
                    local_dir=self.data_dir, http_headers=self.http_headers,
                    proxies=self.proxies, **value
                )
            else:
                self._values[name] = value

        return self._values[name]


class CromwellHarness:
    """
    Class that manages the running of WDL workflows using Cromwell.

    Args:
        project_root: The root path to which non-absolute WDL script paths are
            relative.
        import_paths_file: File that contains relative or absolute paths to
            directories containing WDL scripts that should be available as
            imports (one per line).

    Env:
        JAVA_HOME: path containing the bin dir that contains the java executable.
        CROMWELL_JAR: path to the cromwell JAR file.
    """
    def __init__(
        self, project_root, import_paths_file=None, java_bin="/usr/bin/java",
        cromwell_jar_file="cromwell.jar"
    ):
        self.java_bin = java_bin
        self.cromwell_jar = cromwell_jar_file
        self.project_root = os.path.abspath(project_root)
        self.import_paths = None
        if import_paths_file:
            with open(import_paths_file, "rt") as inp:
                self.import_paths = [
                    self._get_path(import_path)
                    for import_path in inp.read().splitlines(keepends=False)
                ]

    def run_workflow(
        self, wdl_script, workflow_name, inputs, expected, execution_dir=None
    ):
        if execution_dir:
            os.chdir(execution_dir)

        cromwell_inputs = dict(
            (
                "{}.{}".format(workflow_name, key),
                value.path if isinstance(value, DataFile) else value
            )
            for key, value in inputs.items()
        )
        inputs_file = "inputs.json"
        with open(inputs_file, "wt") as out:
            json.dump(cromwell_inputs, out)

        wdl_path = self._get_path(wdl_script)

        imports_zip_arg = ""
        if self.import_paths:
            imports = " ".join(
                os.path.join(self.project_root, path, "*.wdl")
                for path in self.import_paths
            )
            delegator.run(f"zip -j imports.zip {imports}", block=True)
            imports_zip_arg = "-p imports.zip"

        cmd = (
            f"{self.java_bin} -Ddocker.hash-lookup.enabled=false -jar "
            f"{self.cromwell_jar} run -i {inputs_file} {imports_zip_arg} "
            f"{wdl_path}"
        )
        print(f"Executing cromwell command '{cmd}'")
        exe = delegator.run(cmd, block=True)
        if not exe.ok:
            raise Exception(
                f"Cromwell command failed; stdout={exe.out}; stderr={exe.err}"
            )

        outputs = self.get_cromwell_outputs(exe.out)

        for name, expected_value in expected.items():
            key = "{}.{}".format(workflow_name, name)
            if key not in outputs:
                raise AssertionError(
                    "Workflow did not generate output {}".format(key)
                )
            if isinstance(expected_value, DataFile):
                expected_value.assert_contents_equal(outputs[key])
            else:
                assert expected_value == outputs[key]

    def _get_path(self, path):
        if not os.path.isabs(path):
            path = os.path.join(self.project_root, path)
        return path

    @staticmethod
    def get_cromwell_outputs(output):
        lines = output.splitlines(keepends=False)
        start = None
        for i, line in enumerate(lines):
            if line == "{" and lines[i+1].lstrip().startswith('"outputs":'):
                start = i
            elif line == "}" and start is not None:
                end = i
                break
        else:
            raise AssertionError("No outputs JSON found in Cromwell stdout")
        return json.loads("\n".join(lines[start:(end + 1)]))["outputs"]


@contextlib.contextmanager
def _tempdir():
    temp = tempfile.mkdtemp()
    try:
        yield temp
    finally:
        shutil.rmtree(temp)


@pytest.fixture(scope="module")
def project_root(request):
    return os.path.abspath(os.path.join(os.path.dirname(request.fspath), "../.."))


@pytest.fixture(scope="module")
def test_data_file():
    return "tests/test_data.json"


@pytest.fixture(scope="module")
def test_data_dir(project_root):
    test_data_dir = os.environ.get("TEST_DATA_DIR", None)
    cleanup = False
    if not test_data_dir:
        test_data_dir = tempfile.mkdtemp()
        cleanup = True
    else:
        if not os.path.isabs(test_data_dir):
            test_data_dir = os.path.abspath(os.path.join(project_root, test_data_dir))
        if not os.path.exists(test_data_dir):
            os.makedirs(test_data_dir, exist_ok=True)
    try:
        yield test_data_dir
    finally:
        if cleanup:
            shutil.rmtree(test_data_dir)


@pytest.fixture(scope="session")
def default_env():
    return None


@pytest.fixture(scope="session")
def http_headers(default_env):
    headers = copy.copy(default_env) if default_env else {}
    for name, ev in {"X-JFrog-Art-Api": "TOKEN"}.items():
        value = os.environ.get(ev, None)
        if value:
            headers[name] = value
    return headers


@pytest.fixture(scope="session")
def proxies(default_env):
    proxies = copy.copy(default_env) if default_env else {}
    for name, ev in {"http": "HTTP_PROXY", "https": "HTTPS_PROXY"}.items():
        proxy = os.environ.get(ev, None)
        if proxy:
            proxies[name] = proxy
    return proxies


@pytest.fixture(scope="session")
def import_paths():
    return None


@pytest.fixture(scope="session")
def java_bin():
    return os.path.join(
        os.path.abspath(os.environ.get("JAVA_HOME", "/usr")),
        "bin", "java"
    )


@pytest.fixture(scope="session")
def cromwell_jar_file():
    if "CROMWELL_JAR" in os.environ:
        return os.environ.get("CROMWELL_JAR")

    classpath = os.environ.get("CLASSPATH")
    if classpath:
        for path in classpath.split(os.pathsep):
            if os.path.basename(path).lower().startswith("cromwell"):
                return path

    return "cromwell.jar"


@pytest.fixture(scope="module")
def test_data(test_data_file, test_data_dir, http_headers, proxies):
    """
    Provides an accessor for test data files, which may be local or in a remote
    repository. Requires a `test_data_file` argument, which is provided by a
    `@pytest.mark.parametrize` decoration. The test_data_file file is a JSON file
    with keys being workflow input or output parametrize, and values being hashes with
    any of the following keys:

    * url: URL to the remote data file
    * path: Path to the local data file
    * type: File type; recoginzed values: "vcf"

    Args:
        test_data_file:
        test_data_dir:
        http_headers:
        proxies:

    Examples:
        @pytest.mark.parametrize('test_data_file', ['tests/test_data.json'])
        def test_workflow(test_data):
            print(test_data["myfile"])
    """
    return Data(test_data_dir, test_data_file, http_headers, proxies)


@pytest.fixture(scope="module")
def cromwell_harness(project_root, import_paths, java_bin, cromwell_jar_file):
    """
    Provides a harness for calling Cromwell on WDL scripts. Accepts an `import_paths`
    argument, which is provided by a `@pytest.mark.parametrize` decoration. The
    import_paths file contains a list of directories (one per line) that contain WDL
    files that should be made available as imports to the running WDL workflow.

    Examples:
        @pytest.mark.parametrize('import_paths', ['tests/import_paths.txt'])
        def test_workflow(cromwell_harness):
            cromwell_harness.run_workflow(...)
    """
    return CromwellHarness(project_root, import_paths, java_bin, cromwell_jar_file)
