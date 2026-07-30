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
        # Reachability is established with SSH rather than ICMP: everything the
        # target contract does runs over SSH, and a test process without
        # CAP_NET_RAW (any sandboxed runner) cannot send ICMP at all.
        try:
            with hardware.ssh(
                timeout=config.ssh_timeout,
                n_retries=config.n_retries,
                retry_interval=config.retry_interval,
            ):
                logger.info("SSH connection to hardware target established")
        except Exception as exc:
            raise RuntimeError(
                f"Hardware target {config.host}:{config.ssh_port} is not reachable over SSH "
                f"after {config.n_retries} attempts: {exc}"
            ) from exc
        yield hardware
