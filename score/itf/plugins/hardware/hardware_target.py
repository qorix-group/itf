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
"""Target implementation for physical hardware reached over SSH."""

import logging
import time
from contextlib import contextmanager

from score.itf.core.target.ssh_target import SshTarget

logger = logging.getLogger(__name__)


class HardwareTarget(SshTarget):
    """A :class:`Target` backed by a physical board reachable over SSH.

    Unlike the QEMU and Docker backends there is no local process to manage;
    the board is assumed to be powered on and running an SSH server. All command
    execution and file transfer happen over SSH/SFTP (see :class:`SshTarget`).
    """

    def __init__(self, config):
        super().__init__()
        self._config = config

    def _ssh_host(self) -> str:
        return self._config.host

    def _ssh_port(self) -> int:
        return self._config.ssh_port

    def _ssh_username(self) -> str:
        return self._config.username

    def _ssh_password(self) -> str:
        return self._config.password

    def _ssh_pkey_path(self) -> str:
        return self._config.private_key_path

    def restart(self) -> None:
        """Reboot the board and wait until it is reachable again.

        The reboot command (``reboot`` by default, overridable via the
        ``reboot_command`` config key) is issued over SSH. The dropped
        connection while the board goes down is expected and ignored. The method
        then waits for the board to disappear and come back within
        ``reboot_timeout_s`` seconds.

        Both waits probe with SSH rather than ICMP so the plugin works from a
        test runner that has no permission to send ICMP.

        :raises RuntimeError: if the board is not reachable again in time.
        """
        command = self._config.reboot_command
        timeout_s = self._config.reboot_timeout_s
        logger.info(f"Rebooting hardware target with command '{command}'")

        try:
            self.execute(command)
        except Exception as exc:
            # The connection is expected to drop as the board goes down.
            logger.info(f"Connection dropped while issuing reboot (expected): {exc}")

        # Wait for the board to actually go down first, so a board that has not
        # started rebooting yet is not mistaken for one that already finished.
        # Bound this so a board that never drops does not eat the whole budget.
        down_deadline = time.monotonic() + min(30, timeout_s)
        while time.monotonic() < down_deadline:
            if not self.is_reachable(timeout=2):
                break
            time.sleep(1)

        logger.info(f"Waiting up to {timeout_s}s for hardware target to come back online")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.is_reachable(timeout=5):
                logger.info("Hardware target is back online")
                return
            time.sleep(2)

        raise RuntimeError(f"Hardware target did not come back online within {timeout_s} seconds after reboot")


@contextmanager
def hardware_target(config):
    """Context manager for hardware target setup.

    There is no process lifecycle to manage for a physical board, so this simply
    yields a :class:`HardwareTarget` bound to *config*.
    """
    yield HardwareTarget(config)
