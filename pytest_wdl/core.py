from abc import ABCMeta, abstractmethod
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable, List, Optional, Type, Union, cast
import urllib.request

import delegator
from pkg_resources import iter_entry_points

from pytest_wdl.utils import LOG, tempdir, to_path, canonical_path


UNSAFE_RE = re.compile(r"[^\w.-]")


class Localizer(metaclass=ABCMeta):  # pragma: no-cover
    """
    Abstract base of classes that implement file localization.
    """
    @abstractmethod
    def localize(self, destination: Path) -> None:
        """
        Localize a resource to `destination`.

        Args:
            destination: Path to file where the non-local resource is to be localized.
        """
        pass


class UrlLocalizer(Localizer):
    """
    Localizes a file specified by a URL.
    """
    def __init__(
        self, url: str,
        http_headers: Optional[dict] = None,
        proxies: Optional[dict] = None
    ):
        self.url = url
        self.http_headers = http_headers
        self.proxies = proxies

    def localize(self, destination: Path):
        LOG.debug(
            f"Localizing url %s to %s with headers %s and proxies %s",
            self.url, str(destination), str(self.http_headers), str(self.proxies)
        )
        try:
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
        except Exception as err:
            raise RuntimeError(f"Error localizing url {self.url}") from err


class StringLocalizer(Localizer):
    """
    Localizes a string by writing it to a file.
    """
    def __init__(self, contents: str):
        self.contents = contents

    def localize(self, destination: Path):
        LOG.debug(f"Persisting {destination} from contents")
        with open(destination, "wt") as out:
            out.write(self.contents)


class LinkLocalizer(Localizer):
    """
    Localizes a file to another destination using a symlink.
    """
    def __init__(self, source: Path):
        self.source = source

    def localize(self, destination: Path):
        destination.symlink_to(self.source)


class DataFile:
    """
    A data file, which may be local, remote, or represented as a string.

    Args:
        local_path: Path where the data file should exist after being localized.
        localizer: Localizer object, for persisting the file on the local disk.
        allowed_diff_lines: Number of lines by which the file is allowed to differ
            from another and still be considered equal.
    """
    def __init__(
        self,
        local_path: Path,
        localizer: Optional[Localizer] = None,
        allowed_diff_lines: Optional[int] = 0
    ):
        if localizer is None and not local_path.exists():
            raise ValueError(
                f"Local path {local_path} does not exist and 'localizer' is None"
            )
        self.local_path = local_path
        self.localizer = localizer
        self.allowed_diff_lines = allowed_diff_lines or 0

    @property
    def path(self) -> Path:
        if not self.local_path.exists():
            self.localizer.localize(self.local_path)
        return self.local_path

    def __str__(self) -> str:
        return str(self.local_path)

    def assert_contents_equal(self, other: Union[str, Path, "DataFile"]) -> None:
        """
        Assert the contents of two files are equal.

        If `allowed_diff_lines == 0`, files are compared using MD5 hashes, otherwise
        their contents are compared using the linux `diff` command.

        Args:
            other: A `DataFile` or string file path.

        Raises:
            AssertionError if the files are different.
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
    def _assert_contents_equal(
        cls, file1: Path, file2: Path, allowed_diff_lines: int
    ) -> None:
        if allowed_diff_lines:
            cls._diff_contents(file1, file2, allowed_diff_lines)
        else:
            cls._compare_hashes(file1, file2)

    @classmethod
    def _diff_contents(cls, file1: Path, file2: Path, allowed_diff_lines: int) -> None:
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
    def _diff(cls, file1: Path, file2: Path) -> int:
        cmd = f"diff -y --suppress-common-lines {file1} {file2} | grep '^' | wc -l"
        return int(delegator.run(cmd, block=True).out)

    @classmethod
    def _compare_hashes(cls, file1: Path, file2: Path) -> None:
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
    """
    Lazily loads a DataFile plugin class associated with a data type.
    """
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
    for entry_point in iter_entry_points(group="pytest_wdl")
)
"""Data type plugin modules from the discovered entry points."""


class DataDirs:
    """
    Provides data files from test data directory structure as defined by the
    datadir and datadir-ng plugins. Paths are resolved lazily upon first request.
    """
    def __init__(
        self,
        basedir: Path,
        module,  # TODO: no Module type in typelib yet
        function: Callable,
        cls: Optional[Type] = None
    ):
        module_path = module.__name__.split(".")
        if len(module_path) > 1:
            for mod in reversed(module_path[:-1]):
                if basedir.name == mod:
                    basedir = basedir.parent
                else:
                    raise RuntimeError(
                        f"Module path {module_path} does not match basedir {basedir}"
                    )
        self.basedir = basedir
        self.module = os.path.join(*module_path)
        self.function = function.__name__
        self.cls = cls.__name__ if cls else None
        self._paths = None

    @property
    def paths(self) -> List[Path]:
        if self._paths is None:
            def add_datadir_paths(root: Path):
                testdir = root / self.module
                print(f"Checking {testdir}")
                if testdir.exists():
                    if self.cls is not None:
                        clsdir = testdir / self.cls
                        print(f"Checking {clsdir}")
                        if clsdir.exists():
                            fndir = clsdir / self.function
                            print(f"Checking {fndir}")
                            if fndir.exists():
                                self._paths.append(fndir)
                            self._paths.append(clsdir)
                    else:
                        fndir = testdir / self.function
                        print(f"Checking {fndir}")
                        if fndir.exists():
                            self._paths.append(fndir)
                    self._paths.append(testdir)

            self._paths = []
            add_datadir_paths(self.basedir)
            data_root = self.basedir / "data"
            if data_root.exists():
                add_datadir_paths(data_root)
                self._paths.append(data_root)

        return self._paths


class DataResolver:
    """
    Resolves data files that may need to be localized.
    """
    def __init__(
        self,
        data_descriptors: dict,
        cache_dir: Optional[Path] = None,
        http_headers: Optional[dict] = None,
        proxies: Optional[dict] = None
    ):
        self.data_descriptors = data_descriptors
        self.cache_dir = cache_dir
        self.http_headers = http_headers
        self.proxies = proxies

    def resolve(
        self, name: str, datadirs: Optional[DataDirs] = None
    ) -> DataFile:
        if name not in self.data_descriptors:
            raise ValueError(f"Unrecognized name {name}")

        value = self.data_descriptors[name]
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
    ) -> DataFile:
        data_file_class = DATA_TYPES.get(type, DataFile)
        local_path = None
        localizer = None

        if path:
            local_path = to_path(path, self.cache_dir)

        if url:
            localizer = UrlLocalizer(url, self.http_headers, self.proxies)
            if not local_path:
                if name:
                    local_path = canonical_path(self.cache_dir / name)
                else:
                    filename = url.rsplit("/", 1)[1]
                    local_path = canonical_path(self.cache_dir / filename)
        elif contents:
            localizer = StringLocalizer(contents)
            if not local_path:
                if name:
                    local_path = canonical_path(self.cache_dir / name)
                else:
                    local_path = canonical_path(
                        Path(tempfile.mktemp(dir=self.cache_dir))
                    )
        elif name and datadirs:
            for dd in datadirs.paths:
                dd_path = dd / name
                if dd_path.exists():
                    break
            else:
                raise FileNotFoundError(
                    f"File {name} not found in any of the following datadirs: "
                    f"{datadirs.paths}"
                )
            if not local_path:
                local_path = dd_path
            else:
                localizer = LinkLocalizer(dd_path)
        else:
            raise FileNotFoundError(
                f"File {path or name} does not exist. Either a url, file contents, "
                f"or a local file must be provided."
            )

        return data_file_class(local_path, localizer, **kwargs)


class DataManager:
    """
    Manages test data, which is defined in a test_data.json file.

    Args:
        data_resolver: Module-level config.
        datadirs: Data directories to search for the data file.
    """
    def __init__(self, data_resolver: DataResolver, datadirs: DataDirs):
        self.data_resolver = data_resolver
        self.datadirs = datadirs

    def __getitem__(self, name):
        return self.data_resolver.resolve(name, self.datadirs)


class CromwellHarness:
    """
    Manages the running of WDL workflows using Cromwell.

    Args:
        project_root: The root path to which non-absolute WDL script paths are
            relative.
        import_dirs: Relative or absolute paths to directories containing WDL
            scripts that should be available as imports.
        java_bin: Path to the java executable.
        java_args: Default Java arguments to use; can be overidden by passing
            `java_args=...` to `run_workflow`.
        cromwell_jar_file: Path to the Cromwell JAR file.
        cromwell_args: Default Cromwell arguments to use; can be overridden by
            passing `cromwell_args=...` to `run_workflow`.
    """
    def __init__(
        self,
        project_root: Path,
        java_bin: Path,
        cromwell_jar_file: Path,
        import_dirs: Optional[List[Path]] = None,
        java_args: Optional[str] = None,
        cromwell_args: Optional[str] = None
    ):
        self.project_root = project_root
        self.import_dirs = import_dirs
        self.java_bin = java_bin
        self.java_args = java_args
        self.cromwell_jar = cromwell_jar_file
        self.cromwell_args = cromwell_args

    def run_workflow(
        self,
        wdl_script: Union[str, Path],
        workflow_name: Optional[str] = None,
        inputs: Optional[dict] = None,
        expected: Optional[dict] = None,
        **kwargs
    ) -> dict:
        """
        Run a WDL workflow on given inputs, and check that the output matches
        given expected values.

        Args:
            wdl_script: The WDL script to execute.
            workflow_name: The name of the workflow in the WDL script. If None, the
                name of the WDL script is used (without the .wdl extension).
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
            Exception: if there was an error executing Cromwell
            AssertionError: if the actual outputs don't match the expected outputs
        """
        if "execution_dir" in kwargs:
            LOG.warning(
                f"Parameter execution_dir is deprecated and will be removed. Use "
                f"the `chdir` context manager instead."
            )
            os.chdir(kwargs["execution_dir"])

        wdl_path = to_path(wdl_script, self.project_root, canonicalize=True)
        if not wdl_path.exists():
            raise FileNotFoundError(f"WDL file not found at path {wdl_path}")

        if not workflow_name:
            workflow_name = UNSAFE_RE.sub("_", wdl_path.stem)

        cromwell_inputs = None
        inputs_file = None

        if "inputs_file" in kwargs:
            inputs_file = canonical_path(Path(kwargs["inputs_file"]))
            if inputs_file.exists():
                with open(inputs_file, "rt") as inp:
                    cromwell_inputs = json.load(inp)

        if cromwell_inputs is None and inputs:
            if inputs_file:
                inputs_file.parent.mkdir(parents=True)
            else:
                inputs_file = Path(tempfile.mkstemp(suffix=".json")[1])

            cromwell_inputs = dict(
                (
                    f"{workflow_name}.{key}",
                    value.path if isinstance(value, DataFile) else value
                )
                for key, value in inputs.items()
            )
            with open(inputs_file, "wt") as out:
                json.dump(cromwell_inputs, out, default=str)

        write_imports = bool(self.import_dirs)
        imports_file = None
        if "imports_file" in kwargs:
            imports_file = canonical_path(Path(kwargs["imports_file"]))
            if imports_file.exists():
                write_imports = False

        if write_imports:
            imports = [
                wdl
                for path in self.import_dirs
                for wdl in glob.glob(str(path / "*.wdl"))
            ]
            if imports:
                if imports_file:
                    imports_file.parent.mkdir(parents=True)
                else:
                    imports_file = Path(tempfile.mkstemp(suffix=".zip")[1])

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

        inputs_arg = f"-i {inputs_file}" if cromwell_inputs else ""
        imports_zip_arg = f"-p {imports_file}" if imports_file else ""
        java_args = kwargs.get("java_args", self.java_args) or ""
        cromwell_args = kwargs.get("cromwell_args", self.cromwell_args) or ""

        cmd = (
            f"{self.java_bin} {java_args} -jar {self.cromwell_jar} run "
            f"{cromwell_args} {inputs_arg} {imports_zip_arg} {wdl_path}"
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

        outputs = CromwellHarness.get_cromwell_outputs(exe.out)

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
