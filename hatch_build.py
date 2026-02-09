from __future__ import annotations

from io import TextIOWrapper
import json
import os
from pathlib import Path
import subprocess
from subprocess import CompletedProcess

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

PACKAGE_MGR = "npm"
PACKAGE_NAME = "streamlit-javascript"
STREAMLIT_VERSION = "1.42.0"  # PEP-440
PACKAGE_DIR = Path(__file__).resolve().parent


class BuildErrorException(RuntimeError):
    msg: str

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg


class BuildFrontendHook(BuildHookInterface):
    description: str = "Build React interface"
    log_file: TextIOWrapper

    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002
        original_directory = os.getcwd()
        try:
            os.chdir(PACKAGE_DIR)
            with open("setup.log", mode="w", encoding="utf-8") as log_file:
                self.log_file = log_file
                self._run()
        finally:
            os.chdir(original_directory)

    def _run(self) -> None:
        self.frontend_dir = PACKAGE_DIR / "streamlit_javascript" / "frontend"
        self.modules_dir = self.frontend_dir / "node_modules"
        self.build_dir = self.frontend_dir / "build"

        # Pre-install checks
        self._check_package_json()
        self._check_need_protobuf()
        self._show_msg_if_build_dir_exists()
        self._show_msg_if_modules_dir_exists()
        self._check_node_installed()
        self._check_pkgmgr_installed()

        # Install + build
        result = self._run_install()
        if "npm audit fix" in result.stdout:
            self._run_npm_audit()
        self._run_build()

        # Post-install checks
        self._check_build_output_ok()

    def _msg_log(self, msg: str, /, indent: int = 0) -> None:
        assert self.log_file.writable()
        for line in msg.splitlines():
            if line.strip():
                self.log_file.write(" " * indent + line + os.linesep)
        self.log_file.flush()

    def _msg_run(self, result: CompletedProcess, /, indent: int) -> CompletedProcess:
        self._msg_log(f"RC:{result.returncode}", indent=indent)
        self._msg_log("STDOUT:", indent=indent)
        self._msg_log(result.stdout, indent=indent + 2)
        self._msg_log("STDERR:", indent=indent)
        self._msg_log(result.stderr, indent=indent + 2)
        return result

    def _check_package_json(self) -> None:
        self._msg_log("Checking package.json version...")
        package_json_path = self.frontend_dir / "package.json"
        with open(package_json_path, mode="r", encoding="utf-8") as pkg_json:
            try:
                pkg_desc = json.load(pkg_json)
                if "version" not in pkg_desc:
                    self._msg_log(
                        f"WARNING: package.json:version is missing, should be {STREAMLIT_VERSION}"
                    )
                elif pkg_desc["version"] != STREAMLIT_VERSION:
                    self._msg_log(
                        "WARNING: package.json:version should be "
                        f"{STREAMLIT_VERSION} not {pkg_desc['version']}"
                    )
            except json.decoder.JSONDecodeError as exc:
                self._msg_log("Unable to read package.json file - syntax error")
                raise json.decoder.JSONDecodeError(
                    "package.json: " + exc.msg,
                    str(package_json_path),
                    exc.pos,
                ) from None

    def _check_need_protobuf(self) -> None:
        # streamlit-javascript does not use protobuf, but we should have a test.
        self._msg_log(f"{PACKAGE_NAME} does not use protobuf...")

    def _show_msg_if_build_dir_exists(self) -> None:
        self._msg_log("Checking if frontend has already been built...")
        if self.build_dir.is_dir():
            self._msg_log("Found build directory", indent=2)

    def _show_msg_if_modules_dir_exists(self) -> None:
        self._msg_log("Checking if node_modules exists...")
        if self.modules_dir.is_dir():
            self._msg_log("Found node_modules directory", indent=2)

    def _check_node_installed(self) -> CompletedProcess:
        self._msg_log("Checking node is installed...")
        result: CompletedProcess = self._msg_run(
            subprocess.run(
                ["node", "--version"],
                executable="node",
                cwd=str(PACKAGE_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
            ),
            indent=2,
        )
        if result.returncode != 0:
            raise BuildErrorException(
                "Could not find node - it is required for React components"
            )
        return result

    def _check_pkgmgr_installed(self) -> CompletedProcess:
        self._msg_log(f"Checking {PACKAGE_MGR} is installed...")
        result = self._msg_run(
            subprocess.run(
                [PACKAGE_MGR, "--version"],
                executable=PACKAGE_MGR,
                cwd=str(PACKAGE_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
            ),
            indent=2,
        )
        if PACKAGE_MGR == "yarn":
            self._msg_log("Checking yarn corepack is installed")
            result = self._msg_run(
                subprocess.run(
                    ["corepack", "enable"],
                    executable="corepack",
                    cwd=str(PACKAGE_DIR),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                ),
                indent=2,
            )
            if result.returncode != 0:
                raise BuildErrorException(
                    f"Could not find corepack/{PACKAGE_MGR} - it is required "
                    "to install node packages"
                )

        if result.returncode != 0:
            raise BuildErrorException(
                f"Could not find {PACKAGE_MGR} - it is required to install node packages"
            )
        return result

    def _run_install(self) -> CompletedProcess:
        self._msg_log(f"Running {PACKAGE_MGR} install...")
        return self._msg_run(
            subprocess.run(
                [PACKAGE_MGR, "install"],
                executable=PACKAGE_MGR,
                cwd=str(self.frontend_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
            ),
            indent=2,
        )

    def _run_build(self) -> CompletedProcess:
        self._msg_log(f"Running {PACKAGE_MGR} run build...")
        return self._msg_run(
            subprocess.run(
                [PACKAGE_MGR, "run", "build"],
                executable=PACKAGE_MGR,
                cwd=str(self.frontend_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
            ),
            indent=2,
        )

    def _run_npm_audit(self) -> CompletedProcess:
        self._msg_log("Running npm audit...")
        return self._msg_run(
            subprocess.run(
                [PACKAGE_MGR, "audit"],
                executable=PACKAGE_MGR,
                cwd=str(self.frontend_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
            ),
            indent=2,
        )

    def _check_build_output_ok(self) -> None:
        self._msg_log("Checking if frontend was built...")
        if self.build_dir.is_dir():
            self._msg_log("Found build directory", indent=2)
        else:
            raise BuildErrorException("Failed to create output directory")


