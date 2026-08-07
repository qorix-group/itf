# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
import socket
import pytest

from score.itf.plugins.qemu.qemu_target import qemu_target
from score.itf.plugins.qemu.checks import pre_tests_phase
from score.itf.core.utils import padder
from score.itf.core.utils.bunch import Bunch
from score.itf.plugins.qemu.config import load_configuration

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--qemu-config",
        action="store",
        required=True,
        help="Path to json file with target configurations.",
    )
    parser.addoption("--qemu-image", action="store", help="Path to a QEMU image")
    parser.addoption(
        "--qemu-bios",
        action="store",
        default=None,
        help="Path to a BIOS/bootloader (required for aarch64 QEMU 'virt'; ignored on x86_64).",
    )


@pytest.fixture(scope="session")
def dlt():
    """Overrideable fixture for enabling dlt collection.
    The DLT plugin should be loaded after the base plugin.
    """
    pass


@pytest.fixture(scope="session")
def config(request):
    return Bunch(
        qemu_config=load_configuration(request.config.getoption("qemu_config")),
        qemu_image=request.config.getoption("qemu_image"),
        qemu_bios=request.config.getoption("qemu_bios"),
    )


@pytest.fixture(scope="session")
def target_init(config, request, dlt):
    logger.info(f"Starting tests on host: {socket.gethostname()}")
    with qemu_target(config) as qemu:
        pre_tests_phase(qemu)
        yield qemu
