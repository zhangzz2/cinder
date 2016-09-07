
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

from cinder import test
from cinder.volume import configuration as conf

import cinder.volume.drivers.huayunwangji.huayunwangji_iscsi as driver
from cinder.volume.drivers.huayunwangji import lichbd

test_volume = {
    'name': 'volume-41319c5d-b94d-4fca-a5e6-553da0fe0940',
    'size': 1,
    'volume_name': 'vol1',
    'id': '41319c5d-b94d-4fca-a5e6-553da0fe0940',
    'volume_id': '41319c5d-b94d-4fca-a5e6-553da0fe0940',
    'provider_auth': None,
    'project_id': 'project',
    'display_name': 'vol1',
    'display_description': 'test volume',
    'volume_type_id': None,
    'host': 'controller',
    'provider_location': '',
    'status': 'available',
    'admin_metadata': {},
}

LICHBD = "cinder.volume.drivers.huayunwangji.lichbd"


@ddt.ddt
class HuayunwangjiISCSIDriverTestCase(test.TestCase):

    def setUp(self):
        super(HuayunwangjiISCSIDriverTestCase, self).setUp()
        self.cfg = mock.Mock(spec=conf.Configuration)

        self.cfg.vip = '192.168.120.38'
        self.cfg.iqn = 'iqn.2001-04-123.com.fusionstack'
        self.manager_host = "192.168.120.38"

        mock_exec = mock.Mock()
        mock_exec.return_value = ('', '')
        self.driver = driver.HuayunwangjiISCSIDriver(execute=mock_exec,
                                                     configuration=self.cfg)
        self.driver.set_initialized()
        # mock_create = mock.MagicMock(return_value=0)
        # mock.patch("lichbd.lichbd_pool_exist", mock_pool_exist)

    def test_create_volume_success(self):
        # mock_mkpool = mock.MagicMock(return_value=0)
        mock_create = mock.MagicMock(return_value=0)
        mock_pool_exist = mock.MagicMock(return_value=True)
        # mock_volume_exist = mock.MagicMock(return_value=False)

        with mock.patch("%s.lichbd_pool_exist" % (LICHBD), mock_pool_exist):
            with mock.patch("%s.lichbd_create" % (LICHBD), mock_create):
                self.driver.create_volume(test_volume)

    def test_create_volume_fail(self):
        # mock_mkpool = mock.MagicMock(return_value=0)
        mock_create = mock.MagicMock(side_effect=lichbd.ShellError)
        mock_pool_exist = mock.MagicMock(return_value=True)
        # mock_volume_exist = mock.MagicMock(return_value=False)

        with mock.patch("%s.lichbd_pool_exist" % (LICHBD), mock_pool_exist):
            with mock.patch("%s.lichbd_create" % (LICHBD), mock_create):
                self.driver.create_volume(test_volume)
                self.assertRaises(lichbd.ShellError,
                                  self.driver.create_volume,
                                  test_volume)

# from cinder.tests.unit import utils
# from cinder.volume.flows.manager import create_volume
