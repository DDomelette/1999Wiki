from __future__ import annotations

import json
import platform
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


MINIMUM_VERSION = (3, 12, 0)
MAXIMUM_VERSION = (3, 13, 0)


class UnsupportedPythonRuntime(RuntimeError):
    """Raised when an interpreter cannot run the Windows crawler package."""


@dataclass(frozen=True)
class PythonRuntimeInfo:
    system: str
    implementation: str
    version: tuple[int, int, int]
    machine: str
    pointer_bits: int
    executable: Path
    supported: bool
    reasons: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "system": self.system,
            "implementation": self.implementation,
            "version": list(self.version),
            "machine": self.machine,
            "pointer_bits": self.pointer_bits,
            "executable": str(self.executable),
            "supported": self.supported,
            "reasons": list(self.reasons),
        }


def inspect_runtime(
    *,
    system: str,
    implementation: str,
    version: Sequence[int],
    machine: str,
    pointer_bits: int,
    executable: str | Path,
) -> PythonRuntimeInfo:
    normalized_version = tuple(int(item) for item in version[:3])
    if len(normalized_version) != 3:
        raise ValueError("Python version must contain major, minor and patch")
    normalized_system = str(system)
    normalized_implementation = str(implementation).casefold()
    normalized_machine = str(machine)
    normalized_bits = int(pointer_bits)
    reasons: list[str] = []
    if normalized_system.casefold() != "windows":
        reasons.append("platform_not_windows")
    if normalized_implementation != "cpython":
        reasons.append("implementation_not_cpython")
    if not (MINIMUM_VERSION <= normalized_version < MAXIMUM_VERSION):
        reasons.append("version_not_3_12")
    if normalized_bits != 64:
        reasons.append("interpreter_not_64_bit")
    return PythonRuntimeInfo(
        system=normalized_system,
        implementation=normalized_implementation,
        version=normalized_version,
        machine=normalized_machine,
        pointer_bits=normalized_bits,
        executable=Path(executable).expanduser().resolve(strict=False),
        supported=not reasons,
        reasons=tuple(reasons),
    )


def current_runtime_info() -> PythonRuntimeInfo:
    return inspect_runtime(
        system=platform.system(),
        implementation=sys.implementation.name,
        version=sys.version_info[:3],
        machine=platform.machine(),
        pointer_bits=struct.calcsize("P") * 8,
        executable=sys.executable,
    )


def validate_runtime(info: PythonRuntimeInfo | None = None) -> PythonRuntimeInfo:
    inspected = current_runtime_info() if info is None else info
    if not inspected.supported:
        reasons = ", ".join(inspected.reasons)
        raise UnsupportedPythonRuntime(
            f"Huiji crawler requires Windows x64 CPython >=3.12.0,<3.13 ({reasons})"
        )
    return inspected


_PROBE_CODE = (
    "import json,platform,struct,sys;"
    "print(json.dumps({'system':platform.system(),'implementation':sys.implementation.name,"
    "'version':list(sys.version_info[:3]),'machine':platform.machine(),"
    "'pointer_bits':struct.calcsize('P')*8,'executable':sys.executable},sort_keys=True))"
)


def probe_python_command(
    command: Sequence[str],
    *,
    run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> PythonRuntimeInfo:
    if not command:
        raise ValueError("Python probe command must not be empty")
    completed = run_fn(
        [*command, "-c", _PROBE_CODE],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    payload = json.loads(completed.stdout.strip())
    if not isinstance(payload, dict):
        raise ValueError("Python probe did not return an object")
    return inspect_runtime(
        system=str(payload["system"]),
        implementation=str(payload["implementation"]),
        version=payload["version"],
        machine=str(payload["machine"]),
        pointer_bits=int(payload["pointer_bits"]),
        executable=Path(str(payload["executable"])),
    )
