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
"""Pytest plugin exposing a ``target`` backed by physical hardware over SSH."""

import logging
import socket

import pytest

from score.itf.plugins.core import determine_target_scope
from score.itf.plugins.hardware.config import load_configuration
from score.itf.plugins.hardware.hardware_target import hardware_target

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--hardware-config",
        action="store",
        required=True,
        help="Path to JSON file with the physical hardware target configuration.",
    )


@pytest.fixture(scope=determine_target_scope)
def config(request):
    return load_configuration(request.config.getoption("hardware_config"))


@pytest.fixture(scope=determine_target_scope)
def target_init(config):
    logger.info(f"Starting tests on host: {socket.gethostname()}")
    with hardware_target(config) as hardware:
        logger.info(f"Connecting to hardware target {config.host}:{config.ssh_port}")
        if not hardware.ping(timeout=config.reboot_timeout_s, interval=1):
            raise RuntimeError(f"Hardware target {config.host} is not reachable (ping failed)")
        with hardware.ssh(timeout=config.ssh_timeout):
            logger.info("SSH connection to hardware target established")
        yield hardware
