
# Copyright 2012 Josh Durgin
# Copyright 2013 Canonical Ltd.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import ddt

import mock

from cinder import context
from cinder import test
from cinder.tests.unit import fake_snapshot
from cinder.tests.unit import fake_volume
from cinder.volume import configuration as conf

import cinder.volume.drivers.huayunwangji.huayunwangji_iscsi as driver
from cinder.volume.drivers.huayunwangji import lichbd

LICHBD = "cinder.volume.drivers.huayunwangji.lichbd"
mock_lichbd = mock.patch(LICHBD)

def get_shellcmd(cmd, return_code, stdout, stderr):
    shellcmd = lichbd.ShellCmd(cmd)
    shellcmd.return_code = return_code
    shellcmd.stdout = stdout
    shellcmd.stderr = stderr
    return shellcmd


@ddt.ddt
class HuayunwangjiISCSIDriverTestCase(test.TestCase):

    def setUp(self):
        super(HuayunwangjiISCSIDriverTestCase, self).setUp()
        self.cfg = mock.Mock(spec=conf.Configuration)

        self.cfg.huayunwangji_vip = '192.168.120.38'
        self.cfg.huayunwangji_iqn = 'iqn.2001-04-123.com.fusionstack'
        self.cfg.huayunwangji_manager_host = "192.168.120.38"

        mock_exec = mock.Mock()
        mock_exec.return_value = ('', '')
        self.driver = driver.HuayunwangjiISCSIDriver(execute=mock_exec,
                                                     configuration=self.cfg)
        self.driver.set_initialized()
        self.driver.lichbd = mock_lichbd

        self.context = context.get_admin_context()

        self.volume_a = fake_volume.fake_volume_obj(
            self.context,
            **{'name': u'volume-0000000a',
               'id': '4c39c3c7-168f-4b32-b585-77f1b3bf0a38',
               'size': 10})

        self.volume_b = fake_volume.fake_volume_obj(
            self.context,
            **{'name': u'volume-0000000b',
               'id': '0c7d1f44-5a06-403f-bb82-ae7ad0d693a6',
               'size': 10})

        self.snapshot = fake_snapshot.fake_snapshot_obj(
            self.context, name='snapshot-0000000a')

    def test_create_volume_success(self):
        def _success(cmd):
            print 'fuck'
            return get_shellcmd(cmd, 0, "stdout", "stderr")

        mock_lichbd.call_try = _success
        mock_lichbd.lichbd_pool_exist.return_value = True
        mock_lichbd.lichbd_volume_create.return_value = 0
        self.driver.create_volume(self.volume_a)

    @mock.patch(LICHBD)
    def test_create_volume_fail(self, mock_lichbd):
        mock_lichbd.lichbd_pool_exist.return_value = True
        mock_lichbd.lichbd_volume_create.side_effect = lichbd.ShellError
        self.assertRaises(lichbd.ShellError,
                          self.driver.create_volume, self.volume_a)
