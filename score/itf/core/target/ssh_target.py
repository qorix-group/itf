# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""Reusable SSH/SFTP based :class:`Target` implementation.

Any target that is reachable over SSH (a QEMU guest, a Docker container or a
physical board) shares the same command-execution and file-transfer logic.
This module extracts that logic so concrete backends only need to provide the
connection parameters (host, port, credentials) and a :meth:`~Target.restart`
implementation.

Subclasses supply connection details by overriding the ``_ssh_*`` hooks.
"""

import logging
import os
import shlex
import threading
import time

from score.itf.core.com.ping import ping, ping_lost
from score.itf.core.com.sftp import Sftp
from score.itf.core.com.ssh import Ssh
from score.itf.core.process.async_process import AsyncProcess
from score.itf.core.target.target import Target

logger = logging.getLogger(__name__)

SSH_CAPABILITIES = ["ssh", "sftp"]


class SshAsyncProcess(AsyncProcess):
    """Handle for a non-blocking command execution on a target via SSH."""

    def __init__(self, target, ssh_ctx, channel, pid, output_thread, output_lines):
        self._target = target
        self._ssh_ctx = ssh_ctx
        self._channel = channel
        self._pid = pid
        self._output_thread = output_thread
        self._output_lines = output_lines
        self._logger = logging.getLogger(f"async_exec.{pid}")
        self._closed = False

    def pid(self) -> int:
        """Return the PID of the running command."""
        return self._pid

    def is_running(self) -> bool:
        """Return *True* if the command is still executing."""
        return not self._channel.exit_status_ready()

    def get_exit_code(self) -> int:
        """Return the exit code of the finished command."""
        return self._channel.recv_exit_status()

    def wait(self, timeout_s: float = 15) -> int:
        """Block until the command finishes or *timeout_s* elapses.

        :param timeout_s: maximum seconds to wait.
        :return: exit code of the command.
        :raises RuntimeError: on timeout.
        """
        start_time = time.time()
        while self.is_running():
            if time.time() - start_time > timeout_s:
                raise RuntimeError(
                    f"Waiting for process with PID [{self._pid}] to terminate timed out after {timeout_s} seconds"
                )
            time.sleep(0.1)
        self._output_thread.join()
        exit_code = self.get_exit_code()
        self._close_ssh()
        return exit_code

    def stop(self) -> int:
        """Terminate the running command, escalating to SIGKILL if needed.

        :return: exit code of the stopped command.
        """
        self._terminate()
        for _ in range(5):
            time.sleep(1)
            if not self.is_running():
                break
        if self.is_running():
            self._logger.error(f"Process with PID [{self._pid}] did not terminate properly, sending SIGKILL.")
            self._kill()
            self.wait()
        self._output_thread.join()
        exit_code = self.get_exit_code()
        self._close_ssh()
        return exit_code

    def _close_ssh(self):
        if not self._closed:
            self._closed = True
            try:
                self._ssh_ctx.__exit__(None, None, None)
            except Exception:
                pass

    def _terminate(self):
        self._target.execute(f"kill {self._pid}")

    def _kill(self):
        self._target.execute(f"kill -9 {self._pid}")

    def get_output(self) -> str:
        """Return the captured stdout of the command."""
        return "\n".join(self._output_lines) + ("\n" if self._output_lines else "")


class SshTarget(Target):
    """Base :class:`Target` that talks to a remote host over SSH/SFTP.

    Concrete backends override the ``_ssh_*`` hooks to supply the connection
    parameters and implement :meth:`restart`.
    """

    def __init__(self, capabilities=None):
        caps = set(SSH_CAPABILITIES)
        if capabilities is not None:
            caps.update(capabilities)
        super().__init__(capabilities=caps)

    # ---- connection parameter hooks (override in subclasses) ---------------

    def _ssh_host(self) -> str:
        raise NotImplementedError

    def _ssh_port(self) -> int:
        return 22

    def _ssh_username(self) -> str:
        return "root"

    def _ssh_password(self) -> str:
        return ""

    def _ssh_pkey_path(self) -> str:
        return ""

    # ---- Target contract ---------------------------------------------------

    def execute(self, command: str):
        timeout = 30
        max_exec_time = 180
        verbose = True

        with self.ssh(timeout=timeout) as ssh:
            exit_code, output_lines, _ = ssh.execute_command_output(
                command,
                timeout=timeout,
                max_exec_time=max_exec_time,
                verbose=verbose,
            )
        output = "".join(output_lines).encode()
        return exit_code, output

    def upload(self, local_path: str, remote_path: str) -> None:
        with self.sftp() as sftp:
            sftp.upload(local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        with self.sftp() as sftp:
            sftp.download(remote_path, local_path)

    def execute_async(self, binary_path, args=None, cwd="/", **kwargs) -> SshAsyncProcess:
        """Start a binary without blocking and return a :class:`SshAsyncProcess` handle.

        The command is executed over a dedicated SSH session.  A shell wrapper
        prints the shell PID first, then runs the command.  The PID is used
        for later signal delivery via ``kill``.

        :param binary_path: path to the binary to execute.
        :param args: list of string arguments for the binary.
        :param cwd: working directory inside the target.
        :return: a :class:`SshAsyncProcess` instance for lifecycle management.
        """
        if args is None:
            args = []
        command = f"{binary_path} {' '.join(shlex.quote(a) for a in args)}"

        ssh_ctx = self.ssh(timeout=30, n_retries=5)
        ssh_ctx.__enter__()
        try:
            transport = ssh_ctx.get_paramiko_client().get_transport()
            channel = transport.open_session()
            channel.set_combine_stderr(True)
            inner = (
                f"[ -r /etc/profile ] && . /etc/profile >/dev/null 2>&1; echo $$; cd {shlex.quote(cwd)} && {command}"
            )
            channel.exec_command(f"sh -lc {shlex.quote(inner)}")

            # Read the PID from the first line of output.
            channel.settimeout(30)
            pid_line = b""
            while True:
                byte = channel.recv(1)
                if not byte or byte == b"\n":
                    break
                pid_line += byte
            channel.settimeout(None)
            pid = int(pid_line.decode().strip())

            cmd_logger = logging.getLogger(os.path.basename(command.split()[0]))
            output_lines = []

            def _async_log():
                def _recv_and_process():
                    data = channel.recv(4096)
                    if not data:
                        return False
                    for line in data.decode(errors="replace").strip().split("\n"):
                        cmd_logger.info(line)
                        output_lines.append(line)
                    return True

                while True:
                    if channel.recv_ready():
                        if not _recv_and_process():
                            break
                    elif channel.exit_status_ready():
                        while channel.recv_ready():
                            if not _recv_and_process():
                                break
                        break
                    else:
                        time.sleep(0.1)

            output_thread = threading.Thread(target=_async_log, daemon=True)
            output_thread.start()

            return SshAsyncProcess(self, ssh_ctx, channel, pid, output_thread, output_lines)
        except Exception:
            ssh_ctx.__exit__(None, None, None)
            raise

    # ---- connection helpers ------------------------------------------------

    def ssh(
        self,
        timeout: int = 15,
        port: int = None,
        n_retries: int = 5,
        retry_interval: int = 1,
        pkey_path: str = None,
        username: str = None,
        password: str = None,
        ext_ip: bool = False,
    ):
        """Create SSH connection to target.

        :param int timeout: Connection timeout in seconds. Default is 15 seconds.
        :param int port: SSH port, if None use default port from config.
        :param int n_retries: Number of retries to connect. Default is 5 retries.
        :param int retry_interval: Interval between retries in seconds. Default is 1 second.
        :param str pkey_path: Path to private key file. If None use default from config.
        :param str username: SSH username. If None use default from config.
        :param str password: SSH password. If None use default from config.
        :param bool ext_ip: Use external IP address if True, otherwise use internal IP address.
        :return: Ssh connection object.
        :rtype: Ssh
        """
        return Ssh(
            target_ip=self._ssh_host(),
            port=port if port else self._ssh_port(),
            timeout=timeout,
            n_retries=n_retries,
            retry_interval=retry_interval,
            pkey_path=pkey_path if pkey_path is not None else self._ssh_pkey_path(),
            username=username if username is not None else self._ssh_username(),
            password=password if password is not None else self._ssh_password(),
        )

    def sftp(self, ssh_connection=None):
        return Sftp(ssh_connection, self._ssh_host(), self._ssh_port())

    def ping(self, timeout, wait_ms_precision=None):
        return ping(
            address=self._ssh_host(),
            timeout=timeout,
            wait_ms_precision=wait_ms_precision,
        )

    def ping_lost(self, timeout, interval=1, wait_ms_precision=None):
        return ping_lost(
            address=self._ssh_host(),
            timeout=timeout,
            interval=interval,
            wait_ms_precision=wait_ms_precision,
        )
