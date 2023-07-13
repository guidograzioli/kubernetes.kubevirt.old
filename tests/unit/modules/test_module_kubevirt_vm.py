# -*- coding: utf-8 -*-
# Copyright: (c) 2021, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import unittest

from unittest.mock import MagicMock, patch, call

from ansible.module_utils import basic
from ansible_collections.kubernetes.kubevirt.plugins.modules import kubevirt_vm
from ansible_collections.kubernetes.core.tests.unit.utils.ansible_module_mock import (
    AnsibleFailJson,
    AnsibleExitJson,
    exit_json,
    fail_json,
    get_bin_path,
    set_module_args,
)


class TestCreateVMI(unittest.TestCase):
    def setUp(self):
        self.mock_module_helper = patch.multiple(
            basic.AnsibleModule,
            exit_json=exit_json,
            fail_json=fail_json,
            get_bin_path=get_bin_path,
        )
        self.mock_module_helper.start()

        # Stop the patch after test execution
        # like tearDown but executed also when the setup failed
        self.addCleanup(self.mock_module_helper.stop)

    def test_module_fail_when_required_args_missing(self):
        with self.assertRaises(AnsibleFailJson):
            set_module_args({})
            kubevirt_vm.main()

    def test_create(self):
        set_module_args(
            {
                "name": "testvm",
                "namespace": "default",
                "state": "present",
                "labels": {
                    "service": "loadbalancer",
                    "environment": "staging"
                }
            }
        )
        with patch.object(basic.AnsibleModule, "run_command") as mock_run_command:
            mock_run_command.return_value = (
                0,
                "configuration updated",
                "",
            )  # successful execution
            with self.assertRaises(AnsibleExitJson) as result:
                kubevirt_vm.main()
        #kubevirt_vm.assert_called_once_with()
        #mock_run_command.assert_called_once_with(
        #    "/usr/bin/helm upgrade -i --reset-values test /tmp/path",
        #    environ_update={"HELM_NAMESPACE": "test"},
        #)
        assert (
            result.exception.args[0]["command"]
            == "/usr/bin/helm upgrade -i --reset-values test /tmp/path"
        )
