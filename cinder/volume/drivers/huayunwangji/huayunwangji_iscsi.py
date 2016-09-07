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

# import copy
# import math
import errno
import os
# import time
import tempfile
import uuid

from cinder import exception
 from cinder.i18n import _
# from cinder.i18n import _, _LE, _LI, _LW
from cinder import context
from cinder.volume import volume_types

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import fileutils

from cinder import exception
from cinder.i18n import _, _LW
# from cinder.i18n import _, _LE, _LI, _LW
from cinder.image import image_utils
# from cinder import utils
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
        self.manager_host = getattr(self.configuration,
                                    'huayunwangji_manager_host')
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

    def _get_volume_type(self, volume):
        volume_type = None
        type_id = volume['volume_type_id']
        if type_id:
            ctxt = context.get_admin_context()
            volume_type = volume_types.get_volume_type(ctxt, type_id)

        return volume_type

    def __id2name(self, volume_id):
        return "volume-%s" % (volume_id)

    def __name2pool(self, name):
        return name[:11]

    def __name2volume(self, name):
        return '%s/%s' % (self.__name2pool(name), name)

    def _id2volume(self, volume_id):
        return self.__name2volume((self.__id2name(volume_id)))

    def _id2pool(self, volume_id):
        return self.__name2pool((self.__id2name(volume_id)))

    def create_volume(self, volume):
        LOG.debug("zz2 volume: %s volume.size %s" % (volume.name, volume.size))
        LOG.debug("zz2 user_id %s" % (volume.user_id))
        LOG.debug("zz2 project_id %s" % (volume.project_id))
        LOG.debug("zz2 availableiliyt_zone %s" % (volume.availability_zone))

        # time.sleep(100)
        # raise NotImplementedError("")
        volume_type = self._get_volume_type(volume)
        if volume_type:
            LOG.debug("zz2 volume_type %s" % (volume_type))
            LOG.debug("zz2 dir volume_type %s" % (dir(volume_type)))
            LOG.debug("zz2 volume_type %s" % (volume_type["name"]))

        size = "%s%s" % (int(volume.size), 'Gi')
        pool = self._id2pool(volume.id)
        path = "%s/%s" % (pool, volume.name)

        if not self.lichbd.lichbd_pool_exist(pool):
            self.lichbd.lichbd_mkpool(pool)

        # if not self.lichbd.lichbd_volume_exist(path):
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
        # 'image_location':
        # (u'cinder://ea6544d0-9594-4598-8560-a5eb310626e5', None)
        LOG.debug("clone image '%s', context: %s,image_location: %s, \
                  image_meta: %s, image_service: %s" % (
                  volume.name, context, image_location,
                  image_meta, image_service))

        if image_location:
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
        LOG.debug(msg)
        return ({}, False)

    def _image_conversion_dir(self):
        tmpdir = CONF.image_conversion_dir
        if not tmpdir:
            tmpdir = tempfile.gettempdir()
            LOG.warning(_LW('image_conversion_dir not set, so use tmpfile'))

        if not os.path.exists(tmpdir):
            os.makedirs(tmpdir)

        return tmpdir

    def copy_image_to_volume(self, context, volume, image_service, image_id):
        LOG.debug("copy_image_to_volume context %s" % (context))
        LOG.debug("copy_image_to_volume volume %s" % (volume))
        LOG.debug("copy_image_to_volume image_service %s" % (image_service))
        LOG.debug("copy_image_to_volume image_id %s" % (image_id))

        raise NotImplementedError()
        tmp_dir = self._image_conversion_dir()

        with tempfile.NamedTemporaryFile(dir=tmp_dir) as tmp:
            image_utils.fetch_to_raw(context, image_service, image_id,
                                     tmp.name,
                                     self.configuration.volume_dd_blocksize,
                                     size=volume.size)

            # self.delete_volume(volume)
            src_path = tmp.name
            dst_path = self._id2volume(volume.id)
            dst_pool = self._id2pool(volume.id)

            if not self.lichbd.lichbd_pool_exist(dst_pool):
                self.lichbd.lichbd_mkpool(dst_pool)

            self.lichbd.lichbd_import(src_path, dst_path)

    def backup_volume(self, context, backup, backup_service):
        """Create a new backup from an existing volume."""
        pass
        LOG.debug("volume backup complete.")

    def restore_backup(self, context, backup, volume, backup_service):
        """Restore an existing backup to a new or existing volume."""
        pass
        LOG.debug("volume restore complete.")

    def copy_volume_to_image(self, context, volume, image_service, image_meta):
        LOG.debug("copy_volume_to_image")
        LOG.debug("copy_volume_to_image context %s" % (context))
        LOG.debug("copy_volume_to_image volume %s" % (volume))
        LOG.debug("copy_volume_to_image image_service %s" % (image_service))
        LOG.debug("copy_volume_to_image image_meta %s" % (image_meta))

        tmp_dir = self._image_conversion_dir()
        tmp_file = os.path.join(tmp_dir,
                                volume.name + '-' + image_meta['id'])

        with fileutils.remove_path_on_error(tmp_file):
            src_path = self._id2volume(volume.id)
            dst_path = tmp_file

            self.lichbd.lichbd_export(src_path, dst_path)

            image_utils.upload_volume(context, image_service,
                                      image_meta, tmp_file)
        os.unlink(tmp_file)

    def extend_volume(self, volume, new_size):
        """Extend an existing volume."""

        LOG.debug("resize volume '%s' to %s" % (volume.name, new_size))
        target = self._id2volume(volume.id)
        size = "%sGi" % (new_size)
        self.lichbd.lichbd_resize(target, size)

    def delete_volume(self, volume):
        """Deletes a logical volume."""

        LOG.debug("delete volume '%s'", volume.name)
        target = self._id2volume(volume.id)
        self.lichbd.lichbd_rm(target)

    def retype(self, context, volume, new_type, diff, host):
        """Retypes a volume, allow Qos and extra_specs change."""

        # No need to check encryption, extra_specs and Qos here as:
        # encryptions have been checked as same.
        # extra_specs are not used in the driver.
        # Qos settings are not used in the driver.
        LOG.debug('retype called for volume %s. No action '
                  'required for volumes.', volume.id)
        return True

    def create_export(self, context, volume, connector):
        """Exports the volume."""

        LOG.debug("create export volume '%s'", volume.name)
        LOG.debug("volume: %s", volume)
        LOG.debug("context: %s", context)
        LOG.debug("connector: %s", connector)

        # self.create_volume(volume)

        iqn = "%s:%s.%s" % (self.iqn, self._id2pool(volume.id), volume.name)
        location = "%s %s %s" % (self.vip + ':3260', iqn, 0)
        return {'provider_location': location,
                'provider_auth': None, }

        """
        iqn.2001-04-123.com.fusionstack:pool2.lunx
        model_update['provider_location'] = (
            '%s %s %s' % (volume['ipaddress'] + ':3260', volume['iqnname'], 0)
        if chap:
            model_update['provider_auth'] = ('CHAP %(username)s %(password)s'
        """

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

        snapshot = "%s@%s" % (self._id2volume(snapshot.volume_id), snapshot.id)
        target_pool = self._id2pool(volume.id)
        target_volume = self._id2volume(volume.id)

        if not self.lichbd.lichbd_pool_exist(target_pool):
            self.lichbd.lichbd_mkpool(target_pool)

        self.lichbd.lichbd_snap_clone(snapshot, target_volume)
        self.lichbd.lichbd_flatten(target_volume)

        if (volume.size > snapshot.volume_size):
            size = "%sG" % (volume.size)
            self.lichbd.lichbd_volume_truncate(target_volume, size)

    def manage_existing(self, volume, existing_ref):
        """Manage an existing volume on the backend storage.
            {'source-name': <pool_name/volume_name>}
        """
        src_path = existing_ref['source-name']
        dst_path = self._id2volume(volume.id)
        dst_pool = self._id2pool(volume.id)

        if not self.lichbd.lichbd_pool_exist(dst_pool):
            self.lichbd.lichbd_mkpool(dst_pool)

        try:
            self.lichbd.lichbd_mv(src_path, dst_path)
        except self.lichbd.ShellError, e:
            if e.code = errno.ENOENT:
                raise exception.ManageExistingInvalidReference(
                    existing_ref, reason=e.message)
            else:
                raise exception.VolumeBackendAPIException(data=e.message)

    def manage_existing_get_size(self, volume, existing_ref):
        """Return size of an existing image for manage_existing.
        """
        src_path = external_ref.get('source-name')

        size = 0
        try:
            size = self.lichbd.lichbd_file_size(src_path)
        except self.lichbd.ShellError, e:
            if e.code = errno.ENOENT:
                raise exception.ManageExistingInvalidReference(
                    existing_ref, reason=e.message)
            else:
                raise exception.VolumeBackendAPIException(data=e.message)

        convert_size = int(math.ceil(int(size))) / units.Gi
        return convert_size

    def delete_snapshot(self, snapshot):
        """Deletes an rbd snapshot."""

        LOG.debug("snapshot %s" % (snapshot))
        LOG.debug("snapshot volume_name: %s" % (snapshot.volume_name))
        LOG.debug("snapshot volume_id: %s" % (snapshot.volume_id))
        LOG.debug("snapshot snap_name: %s" % (snapshot.name))
        snapshot = "%s@%s" % (self._id2volume(snapshot.volume_id), snapshot.id)
        self.lichbd.lichbd_snap_delete(snapshot)

    def migrate_volume(self, context, volume, host):
        # http://docs.openstack.org/developer/cinder/devref/migration.html
        raise NotImplementedError("")
        return (False, None)

    def update_migrated_volume(self, ctxt, volume,
                               new_volume, original_volume_status):
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
        raise NotImplementedError()

    def initialize_connection(self, volume, connector):
        LOG.debug("connection volume %s" % volume.name)
        LOG.debug("connection connector %s" % connector)

        data = {}
        data["target_discovered"] = False
        data["target_iqn"] = "%s:%s.%s" % (self.iqn,
                                           self._id2pool(volume.id),
                                           volume.name)
        # data['target_lun'] = 0
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
