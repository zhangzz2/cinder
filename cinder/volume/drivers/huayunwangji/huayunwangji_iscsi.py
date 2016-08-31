# Copyright 2015 IBM Corp.
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
#


"""
Volume driver for Huayunwangji Fusionstor with iSCSI protocol.
"""

from __future__ import absolute_import
import io
import json
import math
import os
import tempfile

from eventlet import tpool
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import fileutils
from oslo_utils import units
from six.moves import urllib

from cinder import exception
from cinder.i18n import _, _LE, _LI, _LW
from cinder.image import image_utils
from cinder import utils
from cinder.volume import driver

from cinder.volume.drivers.huayunwangji import lichbd 
from cinder.volume.drivers.huayunwangji import shell 

LOG = logging.getLogger(__name__)

huayunwangji_iscsi_opts = [
    cfg.StrOpt('huayunwangji_manager_host',
               default="localhost",
               help='Default the manager host of fusionstor. '
                    '(Default is localhost.)'),
    cfg.StrOpt('huayunwangji_vip',
               default="localhost",
               help='Default the vip of fusionstor. '),
    cfg.StrOpt('huayunwangji_iqn',
               default="",
               help='Default the iqn of fusionstor. ')
]

CONF = cfg.CONF
CONF.register_opts(huayunwangji_iscsi_opts)

class HuayunwangjiISCSIDriver(driver.TransferVD, driver.ExtendVD,
                driver.CloneableImageVD, driver.SnapshotVD,
                driver.MigrateVD, driver.BaseVD):
    """huayunwangji fusionstor iSCSI volume driver.

    Version history:
    1.0.0 - Initial driver
    """

    VERSION = "1.0.0"

    def __init__(self, *args, **kwargs):
        super(HuayunwangjiISCSIDriver, self).__init__(*args, **kwargs)
        self.configuration.append_config_values(huayunwangji_iscsi_opts)

        self.huayunwangji_vip = getattr(self.configuration, 'huayunwangji_vip')
        self.huayunwangji_iqn = getattr(self.configuration, 'huayunwangji_iqn')
        self.huayunwangji_manager_host = getattr(self.configuration, 'huayunwangji_manager_host')

    def _update_volume_stats(self):
        data = {}
        data["volume_backend_name"] = "huayunwangji"
        data["vendor_name"] = 'huayunwangji'
        data["driver_version"] = self.VERSION
        data["storage_protocol"] = "iscsi"
        data['total_capacity_gb'] = 1000
        data['free_capacity_gb'] = 1000
        data['reserved_percentage'] = 1
        data['multiattach'] = True
        self._stats = data

    def check_for_setup_error(self):
        if self.huayunwangji_manager_host is None:
            msg = _('huayunwangji_manager_host not dound')
            raise exception.VolumeBackendAPIException(data=msg)

    def get_volume_stats(self, refresh=False):
        """Get volume status.

        If 'refresh' is True, run update the stats first.
        """

        if refresh:
            self._update_volume_stats()

        return self._stats

    def id2name(self, volume_id):
        return "volume-%s" % (volume_id)

    def name2pool(self, name):
        return name[:11]

    def name2id(self, name):
        return name[7:]

    def name2volume(self, name):
        return '%s/%s' % (self.name2pool(name), name)

    def create_volume(self, volume):
        size = "%s%s" % (int(volume.size), 'G')
        pool = self.name2pool(volume.name)

        lichbd.lichbd_mkpool(pool)
        path = "%s/%s" % (pool, volume.name)
        lichbd.lichbd_create(path, size)

        LOG.debug("creating volume '%s' size %s", volume.name, size)

    def clone_image(self, context, volume,
                    image_location, image_meta,
                    image_service):
        #'image_location': (u'cinder://ea6544d0-9594-4598-8560-a5eb310626e5', None)
        LOG.debug("clone image '%s', context: %s, image_location: %s, image_meta: %s, image_service: %s", volume.name, context, image_location, image_meta, image_service)
        if image_location:
            url_locations = image_location[0]
            volume_id = image_location[0].split("//")[-1]
            volume_name = self.id2name(volume_id)
            snapshot = "%s@%s" % (self.name2volume(volume_name), self.name2id(volume_name))
            self.create_snapshot(snapshot)

            assert(volume.id == self.name2id(volume.name))
            pool = self.name2pool(volume.name)
            lichbd.lichbd_mkpool(pool)
            dst = self.name2volume(volume.name)
            lichbd.lichbd_snap_clone(snapshot, dst)

            return {'provider_location': None}, True

        msg = "not support clone image without location"
        raise NotImplementedError(data=msg)

    def extend_volume(self, volume, new_size):
        """Extend an existing volume."""
        pass

    def delete_volume(self, volume):
        """Deletes a logical volume."""
        LOG.debug("delete volume '%s'", volume.name)

    def create_export(self, context, volume, connector):
        """Exports the volume."""
        LOG.debug("create export volume '%s'", volume.name)
        LOG.debug("volume: %s", volume)
        LOG.debug("context: %s", context)
        LOG.debug("connector: %s", connector)

        self.create_volume(volume)

        iqn = "%s:%s.%s" % (self.huayunwangji_iqn, self.name2pool(volume.name), volume.name)
        location = "%s %s %s" % (self.huayunwangji_vip + ':3260', iqn, 0)
        return {'provider_location': location,
                'provider_auth': None, }

        #iqn.2001-04-123.com.fusionstack:pool2.lunx
        #model_update['provider_location'] = (
            #'%s %s %s' % (volume['ipaddress'] + ':3260', volume['iqnname'], 0)
        #if chap:
            #model_update['provider_auth'] = ('CHAP %(username)s %(password)s'

    def ensure_export(self, context, volume):
        """Synchronously recreates an export for a logical volume."""
        pass

    def remove_export(self, context, volume):
        """Removes an export for a logical volume."""
        pass

    def create_snapshot(self, snapshot):
        """Creates an snapshot."""
        LOG.debug("create snapshot %s" % (snapshot))
        lichbd.lichbd_snap_create(snapshot)

    def create_volume_from_snapshot(self, volume, snapshot):
        """Creates a volume from a snapshot."""
        LOG.debug("create volume from a snapshot")

    def delete_snapshot(self, snapshot):
        """Deletes an rbd snapshot."""
        pass

    def migrate_volume(self, context, volume, host):
        return (False, None)

    def initialize_connection(self, volume, connector):
        LOG.debug("connection volume %s" % volume.name)
        LOG.debug("connection connector %s" % connector)

        data = {}
        data["target_discovered"] = False
        data["target_iqn"] = "%s:%s.%s" % (self.huayunwangji_iqn, self.name2pool(volume.name), volume.name)
        #data['target_lun'] = 0
        data["target_portal"] = "%s:%s" % (self.huayunwangji_vip, 3260)
        data["volume_id"] = volume['id']
        data["discard"] = False

        return {'driver_volume_type': 'iscsi', 'data': data}

        """
        {
                'driver_volume_type': 'iscsi'
                'data': {
                    'target_discovered': True,
                    'target_iqn': 'iqn.2010-10.org.openstack:volume-00000001',
                    'target_portal': '127.0.0.0.1:3260',
                    'volume_id': '9a0d35d0-175a-11e4-8c21-0800200c9a66',
                    'discard': False,
                }
            }
        """

    def terminate_connection(self, volume, connector, **kwargs):
        pass
