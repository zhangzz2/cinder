#  Copyright 2015 Cloudbase Solutions Srl
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

import mock

from cinder import exception
from cinder import test
from cinder.volume.drivers.windows import windows_utils


class WindowsUtilsTestCase(test.TestCase):

    def setUp(self):
        super(WindowsUtilsTestCase, self).setUp()

        windows_utils.WindowsUtils.__init__ = lambda x: None
        self.wutils = windows_utils.WindowsUtils()
        self.wutils._conn_wmi = mock.Mock()
        self.wutils._conn_cimv2 = mock.MagicMock()

    @mock.patch.object(windows_utils.WindowsUtils, 'get_windows_version')
    def test_check_min_windows_version(self, mock_get_win_version):
        required_win_version = [6, 4]
        actual_win_version = '6.3.0'
        mock_get_win_version.return_value = actual_win_version

        self.assertFalse(self.wutils.check_min_windows_version(
            *required_win_version))

    def _test_copy_vhd_disk(self, source_exists=True, copy_failed=False):
        fake_data_file_object = mock.MagicMock()
        fake_data_file_object.Copy.return_value = [int(copy_failed)]

        fake_vhd_list = [fake_data_file_object] if source_exists else []
        mock_query = mock.Mock(return_value=fake_vhd_list)
        self.wutils._conn_cimv2.query = mock_query

        if not source_exists or copy_failed:
            self.assertRaises(exception.VolumeBackendAPIException,
                              self.wutils.copy_vhd_disk,
                              mock.sentinel.src,
                              mock.sentinel.dest)
        else:
            self.wutils.copy_vhd_disk(mock.sentinel.src, mock.sentinel.dest)

            expected_query = (
                "Select * from CIM_DataFile where Name = '%s'" %
                mock.sentinel.src)
            mock_query.assert_called_once_with(expected_query)
            fake_data_file_object.Copy.assert_called_with(
                mock.sentinel.dest)

    def test_copy_vhd_disk(self):
        self._test_copy_vhd_disk()

    def test_copy_vhd_disk_invalid_source(self):
        self._test_copy_vhd_disk(source_exists=False)

    def test_copy_vhd_disk_copy_failed(self):
        self._test_copy_vhd_disk(copy_failed=True)

    @mock.patch.object(windows_utils, 'wmi', create=True)
    def test_import_wt_disk_exception(self, mock_wmi):
        mock_wmi.x_wmi = Exception
        mock_import_disk = self.wutils._conn_wmi.WT_Disk.ImportWTDisk
        mock_import_disk.side_effect = mock_wmi.x_wmi

        self.assertRaises(exception.VolumeBackendAPIException,
                          self.wutils.import_wt_disk,
                          mock.sentinel.vhd_path,
                          mock.sentinel.vol_name)
        mock_import_disk.assert_called_once_with(
            DevicePath=mock.sentinel.vhd_path,
            Description=mock.sentinel.vol_name)

    def test_check_if_resize_is_needed_bigger_requested_size(self):
        ret_val = self.wutils.is_resize_needed(
            mock.sentinel.vhd_path, 1, 0)
        self.assertTrue(ret_val)

    def test_check_if_resize_is_needed_equal_requested_size(self):
        ret_val = self.wutils.is_resize_needed(
            mock.sentinel.vhd_path, 1, 1)
        self.assertFalse(ret_val)

    def test_check_if_resize_is_needed_smaller_requested_size(self):
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.wutils.is_resize_needed,
            mock.sentinel.vhd_path, 1, 2)

    @mock.patch.object(windows_utils.WindowsUtils, '_wmi_obj_set_attr')
    @mock.patch.object(windows_utils, 'wmi', create=True)
    def test_set_chap_credentials(self, mock_wmi, mock_set_attr):
        mock_wt_host = mock.Mock()
        mock_wt_host_class = self.wutils._conn_wmi.WT_Host
        mock_wt_host_class.return_value = [mock_wt_host]

        self.wutils.set_chap_credentials(mock.sentinel.target_name,
                                         mock.sentinel.chap_username,
                                         mock.sentinel.chap_password)

        mock_wt_host_class.assert_called_once_with(
            HostName=mock.sentinel.target_name)

        mock_set_attr.assert_has_calls([
            mock.call(mock_wt_host, 'EnableCHAP', True),
            mock.call(mock_wt_host, 'CHAPUserName',
                      mock.sentinel.chap_username),
            mock.call(mock_wt_host, 'CHAPSecret',
                      mock.sentinel.chap_password)])

        mock_wt_host.put.assert_called_once_with()

    @mock.patch.object(windows_utils.WindowsUtils, '_wmi_obj_set_attr')
    @mock.patch.object(windows_utils, 'wmi', create=True)
    def test_set_chap_credentials_exc(self, mock_wmi, mock_set_attr):
        mock_wmi.x_wmi = Exception
        mock_set_attr.side_effect = mock_wmi.x_wmi
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.wutils.set_chap_credentials,
                          mock.sentinel.target_name,
                          mock.sentinel.chap_username,
                          mock.sentinel.chap_password)

    def test_set_wmi_obj_attr(self):
        wmi_obj = mock.Mock()
        wmi_property_method = wmi_obj.wmi_property
        wmi_property = wmi_obj.wmi_property.return_value

        self.wutils._wmi_obj_set_attr(wmi_obj,
                                      mock.sentinel.key,
                                      mock.sentinel.value)

        wmi_property_method.assert_called_once_with(mock.sentinel.key)
        wmi_property.set.assert_called_once_with(mock.sentinel.value)
