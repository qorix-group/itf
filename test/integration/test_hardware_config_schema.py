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

import json

import pytest

from python.runfiles import runfiles
from score.itf.plugins.hardware.config import load_configuration


def _resource_path(filename: str) -> str:
    rf = runfiles.Create()
    return rf.Rlocation(f"score_itf/test/resources/{filename}")


def test_sample_hardware_config_validates() -> None:
    config = load_configuration(_resource_path("hardware_config.json"))
    assert config.host
    # Defaults are applied for optional keys.
    assert config.ssh_port == 22
    assert config.reboot_command == "reboot"


def test_minimal_hardware_config_applies_defaults(tmp_path) -> None:
    config_file = tmp_path / "hardware_minimal.json"
    config_file.write_text(json.dumps({"host": "10.0.0.1"}), encoding="utf-8")

    config = load_configuration(config_file)

    assert config.host == "10.0.0.1"
    assert config.ssh_port == 22
    assert config.username == "root"
    assert config.reboot_timeout_s == 180


def test_missing_host_is_rejected(tmp_path) -> None:
    config_file = tmp_path / "hardware_no_host.json"
    config_file.write_text(json.dumps({"ssh_port": 22}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_configuration(config_file)


def test_unknown_key_is_rejected(tmp_path) -> None:
    config_file = tmp_path / "hardware_extra_key.json"
    config_file.write_text(json.dumps({"host": "10.0.0.1", "bogus": 1}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_configuration(config_file)


def test_invalid_port_is_rejected(tmp_path) -> None:
    config_file = tmp_path / "hardware_bad_port.json"
    config_file.write_text(json.dumps({"host": "10.0.0.1", "ssh_port": 99999}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_configuration(config_file)
