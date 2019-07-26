from abc import ABCMeta
import glob
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable, Optional, Type, Union, cast
import urllib.request

import delegator
from pkg_resources import iter_entry_points

from pytest_cromwell.utils import LOG, tempdir, deprecated


class Localizer(metaclass=ABCMeta):
    def __call__(self, destination: Path):
        pass


class UrlLocalizer:
    def __init__(
        self, url: str, http_headers: Optional[dict] = None,
        proxies: Optional[dict] = None
    ):
        self.url = url
        self.http_headers = http_headers
        self.proxies = proxies

    def __call__(self, destination: Path):
        LOG.debug(f"Persisting {destination} from url {self.url}")
        req = urllib.request.Request(self.url)
        if self.http_headers:
            for name, value in self.http_headers.items():
                req.add_header(name, value)
        if self.proxies:
            for proxy_type, url in self.proxies.items():
                req.set_proxy(url, proxy_type)
        rsp = urllib.request.urlopen(req)
        with open(destination, "wb") as out:
            shutil.copyfileobj(rsp, out)


class StringLocalizer:
    def __init__(self, contents: str):
        self.contents = contents

    def __call__(self, destination: Path):
        LOG.debug(f"Persisting {destination} from contents")
        with open(destination, "wt") as out:
            out.write(self.contents)


class LinkLocalizer:
    def __init__(self, source: Path):
        self.source = source

    def __call__(self, destination: Path):
        self.source.symlink_to(destination)


class DataFile:
    """
    A data file, which may be located locally, remotely, or represented as a string.

    Args:
        local_path: Path where the data file should exist after being localized.
        localizer:
        allowed_diff_lines:
    """
    def __init__(
        self,
        local_path: Path,
        localizer: Localizer,
        allowed_diff_lines: int = 0
    ):
        self.local_path = local_path
        self.localizer = localizer
        self.allowed_diff_lines = allowed_diff_lines

    @property
    def path(self):
        if not self.local_path.exists():
            self.localizer(self.local_path)
        return self.local_path

    def __str__(self):
        return self.local_path

    def assert_contents_equal(self, other):
        """
        Assert the contents of two files are equal.

        If `allowed_diff_lines == 0`, files are compared using MD5 hashes, otherwise
        their contents are compared using the linux `diff` command.

        Args:
            other: A `DataFile` or string file path.
        """
        allowed_diff_lines = self.allowed_diff_lines

        if isinstance(other, Path):
            other_path = other
        elif isinstance(other, str):
            other_path = Path(other)
        else:
            other_path = other.path
            allowed_diff_lines = max(allowed_diff_lines, other.allowed_diff_lines)

        self._assert_contents_equal(self.path, other_path, allowed_diff_lines)

    @classmethod
    def _assert_contents_equal(cls, file1: Path, file2: Path, allowed_diff_lines: int):
        if allowed_diff_lines:
            cls._diff_contents(file1, file2, allowed_diff_lines)
        else:
            cls._compare_hashes(file1, file2)

    @classmethod
    def _diff_contents(cls, file1: Path, file2: Path, allowed_diff_lines: int):
        if file1.suffix == ".gz":
            with tempdir() as temp:
                temp_file1 = temp / "file1"
                temp_file2 = temp / "file2"
                delegator.run(f"gunzip -c {file1} > {temp_file1}", block=True)
                delegator.run(f"gunzip -c {file2} > {temp_file2}", block=True)
                diff_lines = cls._diff(temp_file1, temp_file2)
        else:
            diff_lines = cls._diff(file1, file2)

        if diff_lines > allowed_diff_lines:
            raise AssertionError(
                f"{diff_lines} lines (which is > {allowed_diff_lines} allowed) are "
                f"different between files {file1}, {file2}"
            )

    @classmethod
    def _diff(cls, file1: Path, file2: Path):
        cmd = "diff -y --suppress-common-lines {} {} | grep '^' | wc -l".format(
            file1, file2
        )
        return int(delegator.run(cmd, block=True).out)

    @classmethod
    def _compare_hashes(cls, file1: Path, file2: Path):
        with open(file1, "rb") as inp1:
            file1_md5 = hashlib.md5(inp1.read()).hexdigest()
        with open(file2, "rb") as inp2:
            file2_md5 = hashlib.md5(inp2.read()).hexdigest()
        if file1_md5 != file2_md5:
            raise AssertionError(
                f"MD5 hashes differ between expected identical files "
                f"{file1}, {file2}"
            )


class _PluginFactory:
    def __init__(self, entry_point):
        self.entry_point = entry_point
        self.factory = None

    def __call__(self, *args, **kwargs):
        if self.factory is None:
            module = __import__(
                self.entry_point.module_name, fromlist=['__name__'], level=0
            )
            self.factory = getattr(module, self.entry_point.attrs[0])
        return self.factory(*args, **kwargs)


DATA_TYPES = dict(
    (entry_point.name, _PluginFactory(entry_point))
    for entry_point in iter_entry_points(group="pytest_cromwell")
)
"""Data type plugin modules from the discovered entry points."""


class DataDirs:
    """
    Provides data files from test data directory structure as defined by the
    datadir and datadir-ng plugins. Paths are resolved lazily upon first request.
    """
    def __init__(
        self, basedir: Path, module, cls: Optional[Type], function: Optional[Callable]
    ):
        self.basedir = basedir
        self.module = module
        self.cls = cls
        self.function = function
        self._paths = None

    @property
    def paths(self):
        if self._paths is None:
            def add_datadir_paths(root: Path):
                testdir = root / self.module.__name__
                if testdir.exists():
                    if self.cls is not None:
                        clsdir = testdir / self.cls.__name__
                        if clsdir.exists():
                            fndir = clsdir / self.function.__name__
                            if fndir.exists():
                                self._paths.apend(fndir)
                            self._paths.append(clsdir)
                    else:
                        fndir = testdir / self.function.__name__
                        if fndir.exists():
                            self._paths.apend(fndir)
                    self._paths.append(testdir)

            self._paths = []
            add_datadir_paths(self.basedir)
            data_root = self.basedir / "data"
            if data_root.exists():
                add_datadir_paths(data_root)
                self._paths.append(data_root)

        return self._paths


class TestDataResolver:
    """
    Resolves data files that may need to be localized.
    """
    def __init__(
        self, test_data_file: Path, localize_dir: Union[str, Path], http_headers: dict,
        proxies: dict
    ):
        with open(test_data_file, "rt") as inp:
            self._data = json.load(inp)
        if isinstance(localize_dir, Path):
            self.localize_dir = cast(Path, localize_dir)
        else:
            self.localize_dir = Path(cast(str, localize_dir))
        self.http_headers = http_headers
        self.proxies = proxies

    def resolve(
        self, name: str, datadirs: Optional[DataDirs] = None
    ) -> DataFile:
        if name not in self._data:
            raise ValueError(f"Unrecognized name {name}")

        value = self._data[name]
        if isinstance(value, dict):
            return self.create_data_file(datadirs=datadirs, **cast(dict, value))
        else:
            return value

    def create_data_file(
        self,
        type: Optional[str] = "default",
        name: Optional[str] = None,
        path: Optional[str] = None,
        url: Optional[str] = None,
        contents: Optional[str] = None,
        datadirs: Optional[DataDirs] = None,
        **kwargs
    ):
        data_file_class = DATA_TYPES.get(type, DataFile)
        local_path = None
        localizer = None

        if path:
            if os.path.isabs(path):
                path = Path(path)
            else:
                path = (self.localize_dir / path).absolute()
            local_path = path

        if url:
            localizer = UrlLocalizer(url, self.http_headers, self.proxies)
            if not local_path:
                if name:
                    local_path = (self.localize_dir / name).absolute()
                else:
                    filename = url.rsplit("/", 1)[1]
                    local_path = (self.localize_dir / filename).absolute()
        elif contents:
            localizer = StringLocalizer(contents)
            if not local_path:
                if name:
                    local_path = (self.localize_dir / name).absolute()
                else:
                    local_path = Path(tempfile.mkstemp(dir=self.localize_dir)[1])
        elif name and datadirs:
            for dd in datadirs.paths:
                dd_path = dd / name
                if dd_path.exists():
                    break
            else:
                raise ValueError(
                    f"File {name} not found in any of the following datadirs: "
                    f"{datadirs}"
                )
            if not local_path:
                local_path = dd_path
            else:
                localizer = LinkLocalizer(dd_path)
        else:
            raise ValueError(
                f"File {path or name} does not exist. Either a url, file contents, "
                f"or a local file must be provided."
            )

        return data_file_class(local_path, localizer, **kwargs)


class TestData:
    """
    Class that manages test data.

    Args:
        test_data_resolver: Module-level config.
        datadirs: Data directories to search for the data file.
    """
    def __init__(self, test_data_resolver: TestDataResolver, datadirs: DataDirs):
        self.test_data_config = test_data_resolver
        self.datadirs = datadirs

    def __getitem__(self, name):
        return self.test_data_config.resolve(name, self.datadirs)


class CromwellHarness:
    """
    Class that manages the running of WDL workflows using Cromwell.

    Args:
        project_root: The root path to which non-absolute WDL script paths are
            relative.
        import_dirs: Relative or absolute paths to directories containing WDL
            scripts that should be available as imports (one per line).
        java_bin:
        java_args: Default Java arguments to use; can be overidden by passing
            `java_args=...` to `run_workflow`.
        cromwell_jar_file:
        cromwell_args: Default Cromwell arguments to use; can be overridden by
            passing `cromwell_args=...` to `run_workflow`.

    Env:
        JAVA_HOME: path containing the bin dir that contains the java executable.
        CROMWELL_JAR: path to the cromwell JAR file.
    """
    def __init__(
        self, project_root, import_dirs=None, java_bin="/usr/bin/java",
        java_args=None, cromwell_jar_file="cromwell.jar", cromwell_args=None
    ):
        self.java_bin = java_bin
        self.java_args = java_args
        self.cromwell_jar = cromwell_jar_file
        self.cromwell_args = cromwell_args
        self.project_root = os.path.abspath(project_root)
        self.import_dirs = None
        if import_dirs:
            self.import_dirs = [self._get_path(path) for path in import_dirs]

    @deprecated
    def __call__(self, *args, **kwargs):
        """
        Briefly used as a replacement for run_workflow.
        """
        self.run_workflow(*args, **kwargs)

    @deprecated
    def run_workflow_in_tempdir(self, *args, **kwargs):
        """
        Conveience method for running a workflow with a temporary execution directory.
        """
        with tempdir() as tmpdir:
            self(*args, **kwargs, execution_dir=tmpdir)

    def run_workflow(
        self, wdl_script, workflow_name, inputs, expected=None, **kwargs
    ) -> dict:
        """
        Run a WDL workflow on given inputs, and check that the output matches
        given expected values.

        Args:
            wdl_script: The WDL script to execute.
            workflow_name: The name of the workflow in the WDL script.
            inputs: Object that will be serialized to JSON and provided to Cromwell
                as the workflow inputs.
            expected: Dict mapping output parameter names to expected values.
            kwargs: Additional keyword arguments, mostly for debugging:
                * execution_dir: DEPRECATED
                * inputs_file: Path to the Cromwell inputs file to use. Inputs are
                    written to this file only if it doesn't exist.
                * imports_file: Path to the WDL imports file to use. Imports are
                    written to this file only if it doesn't exist.
                * java_args: Additional arguments to pass to Java runtime.
                * cromwell_args: Additional arguments to pass to `cromwell run`.

        Returns:
            Dict of outputs.

        Raises:
            Exception if there was an error executing Cromwell.
        """
        if "execution_dir" in kwargs:
            LOG.warning(
                f"Parameter execution_dir is deprecated and will be removed. Use "
                f"the `chdir` context manager instead."
            )
            os.chdir(kwargs["execution_dir"])

        write_inputs = True
        if "inputs_file" in kwargs:
            inputs_file = os.path.abspath(kwargs["inputs_file"])
            if os.path.exists(inputs_file):
                write_inputs = False
            else:
                os.makedirs(os.path.dirname(inputs_file), exist_ok=True)
        else:
            inputs_file = tempfile.mkstemp(suffix=".json")[1]

        if write_inputs:
            cromwell_inputs = dict(
                (
                    f"{workflow_name}.{key}",
                    value.path if isinstance(value, DataFile) else value
                )
                for key, value in inputs.items()
            )
            with open(inputs_file, "wt") as out:
                json.dump(cromwell_inputs, out, default=str)
        else:
            with open(inputs_file, "rt") as inp:
                cromwell_inputs = json.load(inp)

        write_imports = bool(self.import_dirs)
        imports_file = None
        if "imports_file" in kwargs:
            imports_file = os.path.abspath(kwargs["imports_file"])
            if os.path.exists(imports_file):
                write_imports = False

        if write_imports:
            imports = [
                wdl
                for path in self.import_dirs
                for wdl in glob.glob(os.path.join(self.project_root, path, "*.wdl"))
            ]
            if imports:
                if imports_file:
                    os.makedirs(os.path.dirname(imports_file), exist_ok=True)
                else:
                    imports_file = tempfile.mkstemp(suffix=".zip")[1]

                imports_str = " ".join(imports)

                LOG.info(f"Writing imports {imports_str} to zip file {imports_file}")
                exe = delegator.run(
                    f"zip -j - {imports_str} > {imports_file}", block=True
                )
                if not exe.ok:
                    raise Exception(
                        f"Error creating imports zip file; stdout={exe.out}; "
                        f"stderr={exe.err}"
                    )

        imports_zip_arg = f"-p {imports_file}" if imports_file else ""

        java_args = kwargs.get("java_args", self.java_args) or ""
        cromwell_args = kwargs.get("cromwell_args", self.cromwell_args) or ""
        wdl_path = self._get_path(wdl_script, check_exists=True)

        cmd = (
            f"{self.java_bin} {java_args} -jar {self.cromwell_jar} run "
            f"{cromwell_args} -i {inputs_file} {imports_zip_arg} {wdl_path}"
        )
        LOG.info(
            f"Executing cromwell command '{cmd}' with inputs "
            f"{json.dumps(cromwell_inputs, default=str)}"
        )
        exe = delegator.run(cmd, block=True)
        if not exe.ok:
            raise Exception(
                f"Cromwell command failed; stdout={exe.out}; stderr={exe.err}"
            )

        outputs = self.get_cromwell_outputs(exe.out)

        if expected:
            for name, expected_value in expected.items():
                key = f"{workflow_name}.{name}"
                if key not in outputs:
                    raise AssertionError(f"Workflow did not generate output {key}")
                if isinstance(expected_value, DataFile):
                    expected_value.assert_contents_equal(outputs[key])
                else:
                    assert expected_value == outputs[key]

        return outputs

    def _get_path(self, path, check_exists=False):
        if not os.path.isabs(path):
            path = os.path.join(self.project_root, path)
        if check_exists and not os.path.exists(path):
            raise Exception(f"File not found at path {path}")
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
