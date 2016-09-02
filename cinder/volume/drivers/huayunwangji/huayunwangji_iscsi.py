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

from oslo_config import cfg
from oslo_log import log as logging

from cinder import exception
from cinder.i18n import _, _LE, _LI, _LW
#from cinder.image import image_utils
#from cinder import utils
from cinder.volume import driver

from cinder.volume.drivers.huayunwangji import lichbd 

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

        self.vip = getattr(self.configuration, 'huayunwangji_vip')
        self.iqn = getattr(self.configuration, 'huayunwangji_iqn')
        self.manager_host = getattr(
                self.configuration, 'huayunwangji_manager_host')

        self.lichbd = lichbd

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
        if self.manager_host is None:
            msg = _('manager_host not dound')
            raise exception.VolumeBackendAPIException(data=msg)

    def get_volume_stats(self, refresh=False):
        """Get volume status.

        If 'refresh' is True, run update the stats first.
        """

        if refresh:
            self._update_volume_stats()

        return self._stats

    def __id2name(self, volume_id):
        return "volume-%s" % (volume_id)

    def __name2pool(self, name):
        return name[:11]

    def __name2volume(self, name):
        return '%s/%s' % (self.__name2pool(name), name)

    def _id2volume(self, volume_id):
        return "%s/%s" % self.__name2volume((self.__id2name(volume_id)))

    def _id2pool(self, volume_id):
        return "%s/%s" % self.__name2pool((self.__id2name(volume_id)))

    def create_volume(self, volume):
        size = "%s%s" % (int(volume.size), 'G')
        pool = self._id2pool(volume.id)
        path = "%s/%s" % (pool, volume.name)

        if not self.lichbd.lichbd_pool_exist(pool):
            self.lichbd.lichbd_mkpool(pool)

        if not self.lichbd.lichbd_volume_exist(path):
            self.lichbd.lichbd_create(path, size)

        LOG.debug("creating volume '%s' size %s", volume.name, size)

    def create_cloned_volume(self, volume, src_vref):
        LOG.debug("create cloned volume '%s' src_vref %s", volume, src_vref)

        snapshot_id = "snapforclone-%s" % (uuid.uuid4().__str__())
        snapshot = "%s@%s" % (self._id2volume(src_vref['id']), snapshot_id)
        self.lichbd.lichbd_snap_create(snapshot)

        target_pool = self._id2pool(volume.id)
        target_volume = self._id2volume(volume.id)
        if not self.lichbd.lichbd_pool_exist(target_pool):
            self.lichbd.lichbd_mkpool(target_pool)
        self.lichbd.lichbd_snap_clone(snapshot, target_volume)
        self.lichbd.lichbd_flatten(target_volume)
        self.lichbd.lichbd_snap_delete(snapshot)

        if (volume.size > src_vref.size):
            size = "%sG" % (volume.size)
            self.lichbd.lichbd_volume_truncate(target_volume, size)

    def clone_image(self, context, volume,
                    image_location, image_meta,
                    image_service):
        #'image_location': 
        #(u'cinder://ea6544d0-9594-4598-8560-a5eb310626e5', None)
        LOG.debug("clone image '%s', context: %s,image_location: %s,
                image_meta: %s, image_service: %s",
                volume.name, context, image_location,
                image_meta, image_service)

        if image_location:
            url_locations = image_location[0]
            volume_id = image_location[0].split("//")[-1]
            snapshot = "%s@%s" % (self._id2volume(volume_id), volume_id)
            if not self.lichbd.lichbd_snap_exist(snapshot):
                self.lichbd.lichbd_snap_create(snapshot)

            pool = self._id2pool(volume.id)
            if not self.lichbd.lichbd_pool_exist(pool):
                self.lichbd.lichbd_mkpool(pool)
            target = self._id2volume(volume.id)
            self.lichbd.lichbd_snap_clone(snapshot, target)

            return {'provider_location': None}, True

        msg = "not support clone image without location"
        raise NotImplementedError(data=msg)

    def copy_image_to_volume(self, context, volume, image_service, image_id):
        LOG.debug("copy_image_to_volume")
        LOG.debug("copy_image_to_volume context %s" % (context))
        LOG.debug("copy_image_to_volume volume %s" % (volume))
        LOG.debug("copy_image_to_volume image_service %s" % (image_service))
        LOG.debug("copy_image_to_volume image_id %s" % (image_id))

        raise NotImplementedError()

    def copy_volume_to_image(self, context, volume, image_service, image_meta):
        LOG.debug("copy_volume_to_image")
        LOG.debug("copy_volume_to_image context %s" % (context))
        LOG.debug("copy_volume_to_image volume %s" % (volume))
        LOG.debug("copy_volume_to_image image_service %s" % (image_service))
        LOG.debug("copy_volume_to_image image_id %s" % (image_id))
        raise NotImplementedError()

    def extend_volume(self, volume, new_size):
        """Extend an existing volume."""

        LOG.debug("resize volume '%s' to %s" % (volume.name, new_size))
        target = self._id2volume(volume.id)
        size = "%sG" % (new_size)
        self.lichbd.lichbd_resize(target, size)

    def delete_volume(self, volume):
        """Deletes a logical volume."""

        LOG.debug("delete volume '%s'", volume.name)
        target = self._id2volume(volume.id)
        self.lichbd.lichbd_rm(target)

    def create_export(self, context, volume, connector):
        """Exports the volume."""

        LOG.debug("create export volume '%s'", volume.name)
        LOG.debug("volume: %s", volume)
        LOG.debug("context: %s", context)
        LOG.debug("connector: %s", connector)

        self.create_volume(volume)

        iqn = "%s:%s.%s" % (self.iqn, self._id2pool(volume.id), volume.name)
        location = "%s %s %s" % (self.vip + ':3260', iqn, 0)
        return {'provider_location': location,
                'provider_auth': None, }

        #iqn.2001-04-123.com.fusionstack:pool2.lunx
        #model_update['provider_location'] = (
            #'%s %s %s' % (volume['ipaddress'] + ':3260', volume['iqnname'], 0)
        #if chap:
            #model_update['provider_auth'] = ('CHAP %(username)s %(password)s'

    def ensure_export(self, context, volume):
        """Synchronously recreates an export for a logical volume."""

        LOG.debug("ensure export context: %s, volume: %s" % (context, volume))

    def remove_export(self, context, volume):
        """Removes an export for a logical volume."""

        LOG.debug("remove export context: %s, volume: %s" % (context, volume))

    def create_snapshot(self, snapshot):
        """Creates an snapshot."""

        LOG.debug("create snapshot %s" % (snapshot))
        LOG.debug("create snapshot volume_name: %s" % (snapshot.volume_name))
        LOG.debug("create snapshot snap_name: %s" % (snapshot.name))
        snapshot = "%s@%s" % (self._id2volume(snapshot.volume_id), snapshot.id)
        self.lichbd.lichbd_snap_create(snapshot)

    def create_volume_from_snapshot(self, volume, snapshot):
        """Creates a volume from a snapshot."""

        LOG.debug("create volume from a snapshot")

        snapshot = "%s@%s" % (self._id2volume(snapshot.volume_id, snapshot.id)

        target_pool = self._id2pool(volume.id)
        target_volume = self._id2volume(volume.id)
        if not self.lichbd.lichbd_pool_exist(target_pool):
            self.lichbd.lichbd_mkpool(target_pool)

        self.lichbd.lichbd_snap_clone(snapshot, target_volume)
        self.lichbd.lichbd_flatten(target_volume)

        if (volume.size > snapshot.volume_size):
            size = "%sG" % (volume.size)
            self.lichbd.lichbd_volume_truncate(target_volume, size)

    def delete_snapshot(self, snapshot):
        """Deletes an rbd snapshot."""

        LOG.debug("snapshot %s" % (snapshot))
        LOG.debug("snapshot volume_name: %s" % (snapshot.volume_name))
        LOG.debug("snapshot volume_id: %s" % (snapshot.volume_id))
        LOG.debug("snapshot snap_name: %s" % (snapshot.name))
        snapshot = "%s@%s" % (self._id2volume(snapshot.volume_id), snapshot.id)
        self.lichbd.lichbd_snap_delete(snapshot)

    def migrate_volume(self, context, volume, host):
        #http://docs.openstack.org/developer/cinder/devref/migration.html
        raise NotImplementedError("")
        return (False, None)

    def update_migrated_volume(self, ctxt, volume, new_volume,
            original_volume_status):
        """Return model update from huayunwangji for migrated volume.

        This method should rename the back-end volume name(id) on the
        destination host back to its original name(id) on the source host.

        :param ctxt: The context used to run the method update_migrated_volume
        :param volume: The original volume that was migrated to this backend
        :param new_volume: The migration volume object that was created on
                           this backend as part of the migration process
        :param original_volume_status: The status of the original volume
        :returns: model_update to update DB with any needed changes
        """
        pass

    def initialize_connection(self, volume, connector):
        LOG.debug("connection volume %s" % volume.name)
        LOG.debug("connection connector %s" % connector)

        data = {}
        data["target_discovered"] = False
        data["target_iqn"] = "%s:%s.%s" % (
                self.iqn, self._id2pool(volume.id), volume.name)
        #data['target_lun'] = 0
        data["target_portal"] = "%s:%s" % (self.vip, 3260)
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
        LOG.debug("terminate connection")
        LOG.debug("terminate connection volume: %s" % (volume))
        LOG.debug("terminate connection connector : %s" % (connector))
        LOG.debug("terminate connection kwargs : %s" % (kwargs))
        pass
