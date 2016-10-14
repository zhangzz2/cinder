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
import math
import errno
import os
import time
import tempfile
import uuid

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import units
from oslo_utils import netutils
# from oslo_utils import fileutils

from cinder import context
from cinder.volume import volume_types
from cinder import exception
from cinder.i18n import _, _LW, _LE, _LI
# from cinder import objects
from cinder.objects import fields
# from cinder.i18n import _, _LE, _LI, _LW
from cinder.image import image_utils
from cinder import utils
from cinder.volume import driver
from cinder.volume.drivers.huayunwangji import lichbd_localcmd
from cinder.volume.drivers.huayunwangji import lichbd_rest
from cinder.volume.drivers.huayunwangji.lichbd_common import LichbdError

LOG = logging.getLogger(__name__)

huayunwangji_iscsi_opts = [
    cfg.StrOpt('huayunwangji_rest_host',
               default="localhost",
               help='Default the manager host of fusionstor. '
                    '(Default is localhost.)'),
    cfg.StrOpt('huayunwangji_rest_port',
               default="27914",
               help='Default the iqn of fusionstor. '),
    cfg.StrOpt('huayunwangji_client',
               default="rest",
               help='Default the vip of fusionstor. '),
    cfg.BoolOpt('huayunwangji_flatten_volume_from_snapshot',
                default=False,
                help='Flatten volumes created from snapshots to remove '
                     'dependency from volume to snapshot'),
    cfg.IntOpt('huayunwangji_max_clone_depth',
               default=1,
               help='Maximum number of nested volume clones that are '
                    'taken before a flatten occurs. Set to 0 to disable '
                    'cloning.'),
    cfg.StrOpt('huayunwangji_auth_method',
               # default='CHAP', help='auth method'),
               default='', help='auth method'),
    cfg.StrOpt('huayunwangji_auth_username',
               # default='cinder', help='auth username'),
               default='', help='auth username'),
    cfg.StrOpt('huayunwangji_auth_password',
               # default='cindermdsmds', help='auth username'),
               default='', help='auth username'),
]

CONF = cfg.CONF
CONF.register_opts(huayunwangji_iscsi_opts)


class HuayunwangjiISCSIDriver(driver.ConsistencyGroupVD, driver.TransferVD,
                              driver.ExtendVD,
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

        if (getattr(self.configuration, 'huayunwangji_client') == 'rest'):
            self.lichbd = lichbd_rest
        else:
            self.lichbd = lichbd_localcmd

        self.rest_host = getattr(self.configuration, 'huayunwangji_rest_host')
        self.rest_port = getattr(self.configuration, 'huayunwangji_rest_port')
        self.lichbd.lichbd_init(self.rest_host, self.rest_port)
        LOG.info(_LI("huayunwangji_client use rest"))

    def _update_volume_stats(self):
        data = {}
        data["volume_backend_name"] = "huayunwangji"
        data["vendor_name"] = 'huayunwangji'
        data["driver_version"] = self.VERSION
        data["storage_protocol"] = self.lichbd.lichbd_get_proto()
        total = self.lichbd.lichbd_get_capacity()
        used = self.lichbd.lichbd_get_used()
        data['total_capacity_gb'] = total
        data['free_capacity_gb'] = total - used
        data['reserved_percentage'] = 1
        data['consistencygroup_support'] = False
        data['multiattach'] = True
        self._stats = data

    def check_for_setup_error(self):
        if not netutils.is_valid_ip(self.rest_host):
            msg = _('vip error: %s' % (self.rest_host))
            LOG.error(_LE(msg))
            raise exception.VolumeBackendAPIException(data=msg)

        if not netutils.is_valid_port(self.rest_port):
            msg = _('port error' % (self.rest_port))
            LOG.error(_LE(msg))
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

    def _get_volume(self, volume):
        return '%s/%s' % (volume.user_id, volume.id)

    def _get_pool(self, volume):
        return '%s' % (volume.user_id)

    def _get_volume_by_id(self, volume_id):
        ctx = context.get_admin_context()
        v = self.db.volume_get(ctx, volume_id)
        return self._get_volume(v)

    def _get_source(self, path):
        parent = None
        parent_snap = None

        stat = self.lichbd.lichbd_volume_stat(path)
        if stat['source_snapshot'].strip():
            p = stat['source_snapshot'].split(":")[1]
            parent = p.split('@')[0]
            parent_snap = p

        return parent, parent_snap

    def _get_clone_depth(self, volume_name, depth=0):
        parent, parent_snap = self._get_source(volume_name)

        if not parent:
            return depth

        if depth > self.configuration.huayunwangji_max_clone_depth:
            raise Exception(_("clone depth exceeds limit of %s") %
                            (self.configuration.huayunwangji_max_clone_depth))

        return self._get_clone_depth(parent, depth + 1)

    def _check_max_clone_depth(self, src_volume):
        depth = self._get_clone_depth(src_volume)
        if depth == self.configuration.huayunwangji_max_clone_depth:
            raise exception.NotSupportedOperation(
                operation=_("clone depth more than 1, not support flatten"))

            LOG.debug("maximum clone depth (%d) has been reached - "
                      "flattening source volume",
                      self.configuration.huayunwangji_max_clone_depth)
            self.lichbd.lichbd_volume_flatten(src_volume)

    def create_volume(self, volume):
        LOG.debug("zz2 volume: %s volume.size %s" % (volume.name, volume.size))
        LOG.debug("zz2 user_id %s" % (volume.user_id))
        LOG.debug("zz2 project_id %s" % (volume.project_id))
        LOG.debug("zz2 availableiliyt_zone %s" % (volume.availability_zone))

        # time.sleep(100)
        volume_type = self._get_volume_type(volume)
        if volume_type:
            LOG.debug("zz2 volume_type %s" % (volume_type))
            LOG.debug("zz2 dir volume_type %s" % (dir(volume_type)))
            LOG.debug("zz2 volume_type %s" % (volume_type["name"]))

        size = int(volume.size)
        pool = self._get_pool(volume)
        path = self._get_volume(volume)

        if not self.lichbd.lichbd_pool_exist(pool):
            self.lichbd.lichbd_pool_creat(pool)

        # if not self.lichbd.lichbd_volume_exist(path):
        self.lichbd.lichbd_volume_create(path, size)

        if (volume.get('consistencygroup_id')):
            group_name = volume['consistencygroup_id']
            self.lichbd.lichbd_cg_add_volume(group_name, [path])

        LOG.debug("creating volume '%s' size %s", volume.name, size)

    def create_cloned_volume(self, volume, src_vref):
        LOG.debug("create cloned volume '%s' src_vref %s", volume, src_vref)

        target_pool = self._get_pool(volume)
        target_volume = self._get_volume(volume)
        src_volume = self._get_volume_by_id(src_vref['id'])

        if not self.lichbd.lichbd_pool_exist(target_pool):
            self.lichbd.lichbd_pool_creat(target_pool)

        # Do full copy if requested
        if self.configuration.huayunwangji_max_clone_depth <= 0:
            self.lichbd.lichbd_volume_copy(src_volume, target_volume)
            return

        self._check_max_clone_depth(src_volume)

        snapshot_id = "snapforclone-%s" % (uuid.uuid4().__str__())
        snapshot = "%s@%s" % (src_volume, snapshot_id)
        self.lichbd.lichbd_snap_create(snapshot)
        self.lichbd.lichbd_snap_protect(snapshot)
        try:
            self.lichbd.lichbd_snap_clone(snapshot, target_volume)
        except Exception:
            self.lichbd.lichbd_snap_unprotect(snapshot)
            self.lichbd.lichbd_snap_delete(snapshot)
            raise

        # self.lichbd.lichbd_volume_flatten(target_volume)
        # self.lichbd.lichbd_snap_delete(snapshot)

        if (volume.size > src_vref.size):
            size = volume.size
            self.lichbd.lichbd_volume_truncate(target_volume, size)

        if (volume.get('consistencygroup_id')):
            group_name = volume['consistencygroup_id']
            self.lichbd.lichbd_cg_add_volume(group_name, [target_volume])

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
            snapshot = "%s@%s" % (self._get_volume_by_id(volume_id), volume_id)
            if not self.lichbd.lichbd_snap_exist(snapshot):
                self.lichbd.lichbd_snap_create(snapshot)

            pool = self._get_pool(volume)
            if not self.lichbd.lichbd_pool_exist(pool):
                self.lichbd.lichbd_pool_creat(pool)
            target = self._get_volume(volume)
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

    def _dd_copy(src_path, dst_path):
        utils.execute("dd", "if=%s" % (src_path),
                      "of=%s" % (dst_path), "oflag=direct")

    def copy_image_to_volume(self, context, volume, image_service, image_id):
        LOG.debug("copy_image_to_volume context %s" % (context))
        LOG.debug("copy_image_to_volume volume %s" % (volume))
        LOG.debug("copy_image_to_volume volume.size %s" % (volume.size))
        LOG.debug("copy_image_to_volume image_service %s" % (image_service))
        LOG.debug("copy_image_to_volume image_id %s" % (image_id))

        tmp_dir = self._image_conversion_dir()

        with tempfile.NamedTemporaryFile(dir=tmp_dir) as tmp:
            image_utils.fetch_to_raw(context, image_service, image_id,
                                     tmp.name,
                                     self.configuration.volume_dd_blocksize,
                                     size=volume.size)

            size = math.ceil(float(utils.get_file_size(tmp.name)) / units.Gi)
            src_path = tmp.name

            self.create_volume(volume)
            if (size > volume.size):
                self.extend_volume(volume, size)

            by_path = self._makesure_login(volume)
            try:
                self._dd_copy(src_path, by_path)
            except Exception:
                self._makesure_logout(volume)
                raise

        if (volume.get('consistencygroup_id')):
            group_name = volume['consistencygroup_id']
            path = self._get_volume(volume)
            self.lichbd.lichbd_cg_add_volume(group_name, [path])

    def backup_volume(self, context, backup, backup_service):
        """Create a new backup from an existing volume."""
        volume = self.db.volume_get(context, backup.volume_id)
        by_path = self._makesure_login(volume)

        try:
            with open(by_path, "rb") as f:
                backup_service.backup(backup, f)
        except Exception:
            self._makesure_logout(volume)
            raise

        LOG.debug("volume backup complete. %s" % (by_path))

    def restore_backup(self, context, backup, volume, backup_service):
        """Restore an existing backup to a new or existing volume."""
        volume = self.db.volume_get(context, backup.volume_id)
        by_path = self._makesure_login(volume)

        try:
            with open(by_path, "wb") as f:
                backup_service.restore(backup, volume.id, f)
        except Exception:
            self._makesure_logout(volume)
            raise

        LOG.debug("volume restore complete. %s" % (by_path))

    def copy_volume_to_image(self, context, volume, image_service, image_meta):
        LOG.debug("copy_volume_to_image")
        LOG.debug("copy_volume_to_image context %s" % (context))
        LOG.debug("copy_volume_to_image volume %s" % (volume))
        LOG.debug("copy_volume_to_image image_service %s" % (image_service))
        LOG.debug("copy_volume_to_image image_meta %s" % (image_meta))

        by_path = self._makesure_login(volume)
        try:
            image_utils.upload_volume(context,
                                      image_service, image_meta, by_path)
        except Exception:
            raise
        finally:
            self._makesure_logout(volume)

    def extend_volume(self, volume, new_size):
        """Extend an existing volume."""

        LOG.debug("resize volume '%s' to %s" % (volume.name, new_size))
        target = self._get_volume(volume)
        self.lichbd.lichbd_volume_resize(target, new_size)

    def _delete_clone_parent_refs(self, path, src_snap):
        self.lichbd.lichbd_snap_unprotect(src_snap)
        self.lichbd.lichbd_snap_delete(src_snap)

        has_snaps = bool(self.lichbd.lichbd_snap_list(path))
        if (not has_snaps) and path.endswith(".deleted"):
            parent, parent_snap = self._get_source(path)
            self.lichbd.lichbd_volume_delete(path)
            if parent:
                self._delete_clone_parent_refs(parent, parent_snap)

    def delete_volume(self, volume):
        """Deletes a logical volume."""
        LOG.debug("delete volume '%s'", volume.name)
        path = self._get_volume(volume)
        used_clone = False
        parent = None
        parent_snap = None

        # # Ensure any backup snapshots are deleted
        # self._delete_backup_snaps(path)

        snaps = self.lichbd.lichbd_snap_list(path)
        for s in snaps:
            if s.startswith('snapforclone-'):
                used_clone = True
                break

        if used_clone:
            new_name = "%s.deleted" % (path)
            self.lichbd.lichbd_volume_rename(path, new_name)
        else:
            parent, parent_snap = self._get_source(path)
            self.lichbd.lichbd_volume_delete(path)
            if parent:
                self._delete_clone_parent_refs(parent, parent_snap)

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

        iqn = self._get_iqn(self._get_volume(volume))
        location = "%s:%s %s %s" % (self.lichbd.lichbd_get_vip(),
                                    self.lichbd.lichbd_get_port(), iqn, 0)
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

        snap_path = self._get_snap_path(snapshot)
        self.lichbd.lichbd_snap_create(snap_path)

    def _get_snap_path(self, snapshot):
        if snapshot.get('cgsnapshot_id'):
            snap_path = "%s@%s" % (self._get_volume_by_id(snapshot.volume_id),
                                   self._get_cgsnap_name(snapshot.cgsnapshot))
        else:
            snap_path = "%s@%s" % (self._get_volume_by_id(snapshot.volume_id),
                                   snapshot.id)
        return snap_path

    def create_volume_from_snapshot(self, volume, snapshot):
        """Creates a volume from a snapshot."""
        LOG.debug("create volume from a snapshot")

        snap_path = self._get_snap_path(snapshot)
        target_pool = self._get_pool(volume)
        target_volume = self._get_volume(volume)

        if not self.lichbd.lichbd_pool_exist(target_pool):
            self.lichbd.lichbd_pool_creat(target_pool)

        self.lichbd.lichbd_snap_clone(snap_path, target_volume)

        if self.configuration.huayunwangji_flatten_volume_from_snapshot:
            self.lichbd.lichbd_volume_flatten(target_volume)

        if (volume.size > snapshot.volume_size):
            size = volume.size
            self.lichbd.lichbd_volume_truncate(target_volume, size)

        if (volume.get('consistencygroup_id')):
            group_name = volume['consistencygroup_id']
            self.lichbd.lichbd_cg_add_volume(group_name, [target_volume])

    def manage_existing(self, volume, existing_ref):
        """Manage an existing volume on the backend storage.
            {'source-name': <pool_name/volume_name>}
        """
        src_path = existing_ref['source-name']
        dst_path = self._get_volume(volume)
        dst_pool = self._get_pool(volume)

        if not self.lichbd.lichbd_pool_exist(dst_pool):
            self.lichbd.lichbd_pool_creat(dst_pool)

        try:
            self.lichbd.lichbd_volume_rename(src_path, dst_path)
        except LichbdError, e:
            if e.code == errno.ENOENT:
                raise exception.ManageExistingInvalidReference(
                    existing_ref, reason=e.message)
            else:
                raise exception.VolumeBackendAPIException(data=e.message)

    def manage_existing_get_size(self, volume, existing_ref):
        """Return size of an existing image for manage_existing.
        """
        src_path = existing_ref.get('source-name')

        size = 0
        try:
            size = self.lichbd.lichbd_volume_stat(src_path)["size_gb"]
        except LichbdError, e:
            if e.code == errno.ENOENT:
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

        snap_path = self._get_snap_path(snapshot)
        self.lichbd.lichbd_snap_delete(snap_path)

    def migrate_volume(self, context, volume, host):
        # http://docs.openstack.org/developer/cinder/devref/migration.html
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
        name_id = None
        provider_location = None

        src_path = self._get_volume(new_volume)
        dst_path = self._get_volume(volume)
        dst_pool = self._get_pool(volume)

        if not self.lichbd.lichbd_pool_exist(dst_pool):
            self.lichbd.lichbd_pool_creat(dst_pool)

        try:
            self.lichbd.lichbd_volume_rename(src_path, dst_path)
        except LichbdError, e:
            if e.code == errno.ENOENT:
                LOG.error(_LE('Unable to rename the logical volume '
                              'for %s to %s.'), src_path, dst_path)
                name_id = new_volume._name_id or new_volume.id
                provider_location = new_volume['provider_location']
            else:
                raise exception.VolumeBackendAPIException(data=e.message)

        return {'_name_id': name_id, 'provider_location': provider_location}

    def _get_iqn(self, path):
        stat = self.lichbd.lichbd_volume_stat(path)
        return stat["iqn"]

    def _initialize_connection(self, volume):
        data = {}
        data["target_discovered"] = False
        data["target_iqn"] = self._get_iqn(self._get_volume(volume))
        # data['target_lun'] = 0
        data["target_portal"] = "%s:%s" % (self.lichbd.lichbd_get_vip(),
                                           self.lichbd.lichbd_get_port())
        data["volume_id"] = volume['id']
        data["discard"] = False

        if self.configuration.huayunwangji_auth_method:
            data['auth_method'] = self.configuration.huayunwangji_auth_method
            data['auth_username'] = self.configuration.huayunwangji_auth_username
            data['auth_password'] = self.configuration.huayunwangji_auth_password

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

    def initialize_connection(self, volume, connector):
        LOG.debug("connection volume %s" % volume.name)
        LOG.debug("connection connector %s" % connector)

        return self._initialize_connection(volume)

    def terminate_connection(self, volume, connector, **kwargs):
        LOG.debug("terminate connection")
        LOG.debug("terminate connection volume: %s" % (volume))
        LOG.debug("terminate connection connector : %s" % (connector))
        LOG.debug("terminate connection kwargs : %s" % (kwargs))
        pass

    def _run_iscsiadm(self, iscsi_properties, iscsi_command, **kwargs):
        check_exit_code = kwargs.pop('check_exit_code', 0)
        (out, err) = utils.execute('iscsiadm', '-m', 'node', '-T',
                                   iscsi_properties['target_iqn'],
                                   '-p', iscsi_properties['target_portal'],
                                   *iscsi_command, run_as_root=True,
                                   check_exit_code=check_exit_code)
        LOG.debug("iscsiadm %(command)s: stdout=%(out)s stderr=%(err)s",
                  {'command': iscsi_command, 'out': out, 'err': err})
        return (out, err)

    def _makesure_login(self, volume):
        """
        /dev/disk/by-path/
        ip-192.168.120.38:3260-iscsi-iqn.2001-04-123.com.fusionstack
        :volume-37bf.volume-37bf545f-0cfa-4361-a4bc-eda3f6d30809-lun-0
        """

        ctx = context.get_admin_context()
        self.ensure_export(ctx, volume)

        connection = self._initialize_connection(volume)
        iscsi_properties = connection["data"]

        x = iscsi_properties
        by_path = "/dev/disk/by-path"
        f = "ip-%s-iscsi-%s-lun-0" % (x["target_portal"], x["target_iqn"])
        by_path = os.path.join(by_path, f)

        iscsi_command = ('--op', 'new', '--interface', 'default')
        self._run_iscsiadm(iscsi_properties, iscsi_command)

        if self.configuration.huayunwangji_auth_method:
            iscsi_command = ('--op', 'update',
                         '-n', 'node.session.auth.authmethod',
                         '-v', iscsi_properties["auth_method"])
            self._run_iscsiadm(iscsi_properties, iscsi_command)

            iscsi_command = ('--op', 'update',
                         '-n', 'node.session.auth.username',
                         '-v', iscsi_properties["auth_username"])
            self._run_iscsiadm(iscsi_properties, iscsi_command)

            iscsi_command = ('--op', 'update',
                         '-n', 'node.session.auth.password',
                         '-v', iscsi_properties["auth_password"])
            self._run_iscsiadm(iscsi_properties, iscsi_command)

        retry_max = 30
        find = False
        while (retry_max > 0):
            iscsi_command = ('--login',)
            self._run_iscsiadm(iscsi_properties, iscsi_command)

            for i in range(10):
                if os.path.islink(by_path):
                    find = True
                    break
                time.sleep(1)

            if find:
                break

            iscsi_command = ('--logout',)
            self._run_iscsiadm(iscsi_properties, iscsi_command)

            LOG.warning(_LW('Failed to login volume %s, retry: %s') % (
                iscsi_properties, retry_max))
            retry_max = retry_max - 1
            time.sleep(3)

        if not find:
            raise Exception('fail login')

        return by_path

    def _makesure_logout(self, volume):
        connection = self._initialize_connection(volume)
        iscsi_properties = connection["data"]

        x = iscsi_properties
        by_path = "/dev/disk/by-path"
        f = "ip-%s-iscsi-%s-lun-0" % (x["target_portal"], x["target_iqn"])
        by_path = os.path.join(by_path, f)

        retry_max = 30
        while (retry_max > 0):
            iscsi_command = ('--logout',)
            self._run_iscsiadm(iscsi_properties, iscsi_command)

            if not os.path.islink(by_path):
                break

            LOG.warning(_LW('Failed to logout volume %s, retry: %s') % (
                iscsi_properties, retry_max))
            retry_max = retry_max - 1
            time.sleep(3)

        iscsi_command = ('--op', 'delete')
        self._run_iscsiadm(iscsi_properties, iscsi_command)

    def _get_cgsnap_name(self, cgsnapshot):
        return '%s--%s' % (cgsnapshot['consistencygroup_id'], cgsnapshot['id'])

    def create_cgsnapshot(self, context, cgsnapshot, snapshots):
        """Creates a cgsnapshot."""
        LOG.debug("cgsnapshot: %s, snapshots: %s" % (cgsnapshot, snapshots))

        group_name = cgsnapshot['consistencygroup_id']
        snapshot_name = self._get_cgsnap_name(cgsnapshot)
        self.lichbd.lichbd_cgsnapshot_create(group_name, snapshot_name)
        return (None, None)

    def delete_cgsnapshot(self, context, cgsnapshot, snapshots):
        """Deletes a cgsnapshot."""
        LOG.debug("cgsnapshot: %s, snapshots: %s" % (cgsnapshot, snapshots))

        group_name = cgsnapshot['consistencygroup_id']
        snapshot_name = self._get_cgsnap_name(cgsnapshot)
        self.lichbd.lichbd_cgsnapshot_delete(group_name, snapshot_name)
        return (None, None)

    def create_consistencygroup(self, context, group):
        """Creates a consistencygroup."""
        LOG.debug("group: %s" % (group))
        self.lichbd.lichbd_cg_create(group['id'])
        return {'status': fields.ConsistencyGroupStatus.AVAILABLE}

    def delete_consistencygroup(self, context, group, volumes):
        """Deletes a consistency group."""
        LOG.debug("group: %s, volume: %s" % (group, volumes))

        self.lichbd.lichbd_cg_delete(group['id'])
        return (None, None)

    def update_consistencygroup(self, context, group,
                                add_volumes=None, remove_volumes=None):
        """Updates a consistency group.

        :param context: the context of the caller.
        :param group: the dictionary of the consistency group to be updated.
        :param add_volumes: a list of volume dictionaries to be added.
        :param remove_volumes: a list of volume dictionaries to be removed.
        :returns: model_update, add_volumes_update, remove_volumes_update
        """
        add_volumes = add_volumes if add_volumes else []
        remove_volumes = remove_volumes if remove_volumes else []

        add_volumes = [self._get_volume(x) for x in add_volumes]
        remove_volumes = [self._get_volume(x) for x in remove_volumes]
        group_name = group['id']

        if add_volumes:
            self.lichbd.lichbd_cg_add_volume(group_name, add_volumes)

        if remove_volumes:
            self.lichbd.lichbd_cg_remove_volume(group_name, add_volumes)

        return None, None, None

    def create_consistencygroup_from_src(self, context, group, volumes,
                                         cgsnapshot=None, snapshots=None,
                                         source_cg=None, source_vols=None):
        """Creates a consistencygroup from source.

        :param context: the context of the caller.
        :param group: the dictionary of the consistency group to be created.
        :param volumes: a list of volume dictionaries in the group.
        :param cgsnapshot: the dictionary of the cgsnapshot as source.
        :param snapshots: a list of snapshot dictionaries in the cgsnapshot.
        :param source_cg: the dictionary of a consistency group as source.
        :param source_vols: a list of volume dictionaries in the source_cg.
        :returns model_update, volumes_model_update
        """
        if not (cgsnapshot and snapshots and not source_cg or
                source_cg and source_vols and not cgsnapshot):
            msg = _("create_consistencygroup_from_src only supports a "
                    "cgsnapshot source or a consistency group source. "
                    "Multiple sources cannot be used.")
            raise exception.InvalidInput(msg)

        if cgsnapshot:
            for volume, snapshot in zip(volumes, snapshots):
                self.create_volume_from_snapshot(volume, snapshot)
        elif source_cg:
            snap_name = "snapforcreatecg-%s" % (uuid.uuid4().__str__())
            self.lichbd.lichbd_cgsnapshot_create(source_cg['id'], snap_name)

            for volume, src_vol in zip(volumes, source_vols):
                src = "%s@%s" % (self._get_volume_by_id(src_vol["id"]),
                                 snap_name)
                dst = self._get_volume(volume)
                self.lichbd.lichbd_snap_clone(src, dst)
                self.lichbd.lichbd_volume_flatten(dst)

                if volume["size"] > src_vol["size"]:
                    size = volume.size
                    self.lichbd.lichbd_volume_truncate(dst, size)

            self.lichbd.lichbd_cgsnapshot_delete(source_cg['id'], snap_name)

        self.lichbd.lichbd_cg_create(group['id'])
        paths = [self._get_volume(x) for x in volumes]
        self.lichbd.lichbd_cg_add_volume(group['id'], paths)

        return None, None

    def accept_transfer(self, context, volume, new_user, new_project):
        """Accept the transfer of a volume for a new user/project."""
        src_path = self._get_volume(volume)

        volume.user_id = new_user
        volume.project_id = new_project
        dst_pool = self._get_pool(volume)
        dst_path = self._get_volume(volume)

        if not self.lichbd.lichbd_pool_exist(dst_pool):
            self.lichbd.lichbd_pool_creat(dst_pool)

        self.lichbd.lichbd_volume_rename(src_path, dst_path)
