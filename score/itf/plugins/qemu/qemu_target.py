# *******************************************************************************
# Copyright (c) 2025-2026 Contributors to the Eclipse Foundation
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
import logging
from contextlib import contextmanager, nullcontext

from score.itf.core.target.ssh_target import SshTarget
from score.itf.plugins.qemu.qemu_process import QemuProcess


logger = logging.getLogger(__name__)


class QemuTarget(SshTarget):
    def __init__(self, process, config):
        super().__init__()
        self._process = process
        self._config = config

    def _ssh_host(self) -> str:
        return self._config.networks[0].ip_address

    def _ssh_port(self) -> int:
        return self._config.ssh_port

    def kill_process(self):
        self._process.stop()

    def restart_process(self):
        self._process.restart()

    def restart(self) -> None:
        self.restart_process()


@contextmanager
def qemu_target(test_config):
    """Context manager for QEMU target setup."""
    with (
        QemuProcess(
            test_config.qemu_image,
            test_config.qemu_config.qemu_ram_size,
            test_config.qemu_config.qemu_num_cores,
            network_adapters=[adapter.name for adapter in test_config.qemu_config.networks],
            port_forwarding=test_config.qemu_config.port_forwarding
            if hasattr(test_config.qemu_config, "port_forwarding")
            else [],
        )
        if test_config.qemu_image
        else nullcontext() as qemu_process
    ):
        target = QemuTarget(qemu_process, test_config.qemu_config)
        yield target
