from __future__ import annotations

import os
import re
import subprocess
import tempfile

import pytest

from .utils import run_gdb_with_script

can_attach = False

if os.getuid() == 0:
    can_attach = True
else:
    # see `man ptrace`
    with open("/proc/sys/kernel/yama/ptrace_scope") as f:
        result = f.read()
        if len(result) >= 1 and result[0] == "0":
            can_attach = True

REASON_CANNOT_ATTACH = (
    "Test skipped due to inability to attach (needs sudo or sysctl -w kernel.yama.ptrace_scope=0"
)


@pytest.fixture
def launched_bash_binary():
    path = tempfile.mktemp()
    subprocess.check_output(["cp", "/bin/bash", path])

    process = subprocess.Popen([path], stdout=subprocess.PIPE, stdin=subprocess.PIPE)

    yield process.pid, path

    process.kill()

    os.remove(path)  # Cleanup


@pytest.mark.skipif(can_attach is False, reason=REASON_CANNOT_ATTACH)
def test_attachp_command_attaches_to_procname(launched_bash_binary):
    pid, binary_path = launched_bash_binary

    binary_name = binary_path.split("/")[-1]
    result = run_gdb_with_script(pyafter=f"attachp {binary_name}")

    matches = re.search(r"Attaching to ([0-9]+)", result).groups()
    assert matches == (str(pid),)

    assert re.search(rf"Detaching from program: {binary_path}, process {pid}", result)


@pytest.mark.skipif(can_attach is False, reason=REASON_CANNOT_ATTACH)
def test_attachp_command_attaches_to_pid(launched_bash_binary):
    pid, binary_path = launched_bash_binary

    result = run_gdb_with_script(pyafter=f"attachp {pid}")

    matches = re.search(r"Attaching to ([0-9]+)", result).groups()
    assert matches == (str(pid),)

    assert re.search(rf"Detaching from program: {binary_path}, process {pid}", result)


@pytest.mark.skipif(can_attach is False, reason=REASON_CANNOT_ATTACH)
def test_attachp_command_attaches_to_procname_too_many_pids(launched_bash_binary):
    pid, binary_path = launched_bash_binary

    process = subprocess.Popen([binary_path], stdout=subprocess.PIPE, stdin=subprocess.PIPE)

    binary_name = binary_path.split("/")[-1]
    result = run_gdb_with_script(pyafter=f"attachp {binary_name}")

    process.kill()

    matches = re.search(r"Found pids: ([0-9]+), ([0-9]+) \(use `attach <pid>`\)", result).groups()
    matches = list(map(int, matches))
    pid_strings = [str(pid_value) for pid_value in matches]
    matches.sort()

    expected_pids = [pid, process.pid]
    expected_pids.sort()

    assert matches == expected_pids
    expected_template = f"""\
        pwndbg: loaded ### pwndbg commands and ### shell commands. Type pwndbg [--shell | --all] [filter] for a list.
        pwndbg: created $rebase, $ida GDB functions (can be used with print/break)
        PID                USER    COMMAND                        PROCESS TREE
        {pid_strings[0]}   root    {binary_path}        {binary_name}({pid_strings[0]})
        {pid_strings[1]}   root    {binary_path}        {binary_name}({pid_strings[1]})

        Found pids: {', '.join(pid_strings)} (use `attach <pid>`)
"""
    # Remove spaces from the captured output and expected template
    captured_output_no_spaces = result.replace(" ", "")
    expected_template_no_spaces = expected_template.replace(" ", "")

    # Now assert that the modified templates match
    assert captured_output_no_spaces == expected_template_no_spaces


@pytest.mark.skipif(can_attach is False, reason=REASON_CANNOT_ATTACH)
def test_attachp_command_nonexistent_procname():
    result = run_gdb_with_script(
        pyafter="attachp some-nonexistent-process-name"
    )  # No chance there is a process name like this
    assert "Process some-nonexistent-process-name not found" in result


def test_attachp_command_no_pids():
    try:
        # On some machines/GDB versions this halts/waits forever, so we add a timeout here
        result = run_gdb_with_script(
            pyafter="attachp 99999999", timeout=5
        )  # No chance there is a PID like this
    except subprocess.TimeoutExpired:
        # Assume it works
        return

    assert "Error: ptrace: No such process." in result
