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
"""Hardware plugin configuration loading and validation.

The hardware pytest plugin connects to an already-running board over SSH. The
connection details are provided by a JSON configuration file passed via the
`--hardware-config` command line option. The configuration is validated using
Pydantic (unknown keys are rejected) and returned as a Pydantic model.

JSON is used (rather than YAML) to stay consistent with the QEMU and DLT
plugins, which also load their configuration from JSON.

Required top-level keys:
    - `host` (string): IPv4 address or hostname of the target board.

Optional top-level keys:
    - `ssh_port` (int 1..65535, default 22)
    - `username` (string, default "root")
    - `password` (string, default "")
    - `private_key_path` (string, path to an SSH private key)
    - `ssh_timeout` (int seconds, default 15)
    - `n_retries` (int >= 1, default 5)
    - `retry_interval` (int seconds >= 0, default 1)
    - `reboot_command` (string, default "reboot")
    - `reboot_timeout_s` (int seconds >= 1, default 180)

Example:

        {
            "host": "192.168.1.50",
            "ssh_port": 22,
            "username": "root",
            "password": "root",
            "reboot_command": "reboot",
            "reboot_timeout_s": 180
        }
"""

import json
import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class HardwareConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default="root", min_length=1)
    password: str = ""
    private_key_path: str = ""
    ssh_timeout: int = Field(default=15, ge=1)
    n_retries: int = Field(default=5, ge=1)
    retry_interval: int = Field(default=1, ge=0)
    reboot_command: str = Field(default="reboot", min_length=1)
    reboot_timeout_s: int = Field(default=180, ge=1)


def load_configuration(config_file: str) -> HardwareConfigModel:
    """Load and validate a hardware configuration file.

    Args:
        config_file: Path to a JSON configuration file.

    Returns:
        A validated Pydantic model.

    Raises:
        ValueError: If validation fails.
    """
    logger.info(f"Loading configuration from {config_file}")

    with open(config_file, "r") as f:
        config_data = json.load(f)

    try:
        return HardwareConfigModel.model_validate(config_data)
    except ValidationError as exc:
        prefix = f"Invalid hardware configuration in '{config_file}'"
        raise ValueError(prefix + f": {exc}") from exc
