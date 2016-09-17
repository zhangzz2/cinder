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

# import errno
# import subprocess
# import time

from cinder.i18n import _LE
# from cinder.i18n import _, _LW, _LE, _LI

from oslo_log import log as logging

import fusionstor
from cinder.volume.drivers.huayunwangji.lichbd_common import LichbdError

LOG = logging.getLogger(__name__)

# https://wiki.openstack.org/wiki/Cinder/how-to-contribute-a-driver

clusterm = fusionstor.ClusterManager()
hostm = fusionstor.HostManager()
poolm = fusionstor.PoolManager()
volumem = fusionstor.VolumeManager()
snapshotm = fusionstor.SnapshotManager()


def raise_exp(resp, message=None):
    err = []
    err.append('failed to execute rest command')
    if message:
        err.append(message)
    err.append('return code: %s' % resp.status_code)
    err.append('err: %s' % resp.error)
    err.append('request id: %s' % resp.req_id)
    err.append('text body: %s' % resp.text_body)
    err = '\n'.join(err)
    LOG.error(_LE("lichbd rest error: %s" % (err)))
    raise LichbdError(resp.status_code, err)


def check_resp(resp):
    if not resp.ok():
        raise_exp(resp, 'not ok')


def lichbd_get_proto():
    return 'iscsi'


def __lichbd_get_cluster():
    _, resp = clusterm.list()
    if (len(resp.records) != 1):
        raise_exp(resp, "cluster not only")

    check_resp(resp)
    return resp.records[0]


def lichbd_get_iqn():
    cluster = __lichbd_get_cluster()
    return cluster["config_str"]["iscsi.iqn"]


def lichbd_get_vip():
    cluster = __lichbd_get_cluster()
    return cluster["config_str"]["iscsi.vip"]


def lichbd_get_port():
    cluster = __lichbd_get_cluster()
    return cluster["config_str"]["iscsi.port"]


def lichbd_get_used():
    # todo
    return 1000


def lichbd_get_capacity():
    # todo
    return 1000


def lichbd_pool_creat(path):
    _, resp = poolm.create(path, protocol='iscsi')
    check_resp(resp)


def lichbd_pool_exist(path):
    _, resp = poolm.stat(path, protocol='iscsi')
    if resp.status_code == 404:
        return False

    if resp.status_code == 200:
        return True

    check_resp(resp)
    raise


def lichbd_pool_delete(path):
    _, resp = poolm.delete(path, protocol='iscsi')
    if resp.status_code == 404:
        return None

    check_resp(resp)


def lichbd_volume_create(path, size):
    size = "%sB" % (size * 1024 * 1024 * 1024)
    _, resp = volumem.create(path, size,
                             protocol='iscsi', provisioning='thin')
    check_resp(resp)


def lichbd_volume_resize(path, size):
    size = "%sB" % (size * 1024 * 1024 * 1024)
    _, resp = volumem.resize(path, size, protocol='iscsi')
    check_resp(resp)


def lichbd_volume_delete(path):
    _, resp = volumem.delete(path, protocol='iscsi')
    if resp.status_code == 404:
        return None

    check_resp(resp)


def lichbd_volume_rename(dist, src):
    raise
    # _, resp = volumem.rename(name, protocol='iscsi')
    # check_resp(resp)


def lichbd_volume_flatten(path):
    # todo flatten
    raise
    _, resp = volumem.flatten(path, protocol='iscsi')
    check_resp(resp)


def lichbd_volume_stat(path):
    """size =  stat['size_gb']
    source = stat["source"] "/iscsi/zz/0@snap001"
    """
    _, resp = volumem.stat(path, protocol='iscsi')
    check_resp(resp)
    stat = resp["records"]
    return stat


def lichbd_volume_clone_depth(path):
    return 0


def lichbd_volume_exist(path):
    _, resp = volumem.stat(path, protocol='iscsi')
    if resp.status_code == 404:
        return False

    if resp.status_code == 200:
        return True

    check_resp(resp)
    raise


def lichbd_volume_copy(src, dst):
    _, resp = volumem.copy(src, dst, protocol='iscsi')
    check_resp(resp)


def lichbd_snap_create(snap_path):
    volume = snap_path.split('@')[0]
    snap = snap_path.split('@')[1]
    _, resp = snapshotm.create(volume, snap, protocol='iscsi')
    check_resp(resp)


def lichbd_snap_exist(snap_path):
    image_path = snap_path.split("@")[0]
    snap = snap_path.split("@")[1]

    _, resp = snapshotm.stat(image_path, snap, protocol='iscsi')
    if resp.status_code == 404:
        return False

    if resp.status_code == 200:
        return True

    check_resp(resp)
    raise


def lichbd_snap_delete(snap_path):
    image_path = snap_path.split("@")[0]
    snap = snap_path.split("@")[1]

    _, resp = snapshotm.delete(image_path, snap, protocol='iscsi')
    if resp.status_code == 404:
        return None

    check_resp(resp)


def lichbd_snap_list(image_path):
    _, resp = snapshotm.list(image_path, protocol='iscsi')
    check_resp(resp)
    return resp['records']


def lichbd_snap_clone(src, dst):
    image_path = src.split("@")[0]
    snap = src.split("@")[1]
    _, resp = snapshotm.clone(image_path, snap, dst, protocol='iscsi')
    check_resp(resp)


def lichbd_snap_protect(snap_path):
    image_path = snap_path.split("@")[0]
    snap = snap_path.split("@")[1]

    _, resp = snapshotm.protect(image_path, snap,
                                is_protect=True, protocol='iscsi')
    check_resp(resp)


def lichbd_snap_unprotect(snap_path):
    image_path = snap_path.split("@")[0]
    snap = snap_path.split("@")[1]

    _, resp = snapshotm.protect(image_path, snap,
                                is_protect=False, protocol='iscsi')
    check_resp(resp)


def lichbd_cg_create(group_name):
    pass


def lichbd_cg_delete(group_name):
    pass


def lichbd_cg_add_volume(group_name, volumes):
    '''volumes = [pool2/volume2, pool3/v, ...]
    '''
    pass


def lichbd_cg_remove_volume(group_name, volumes):
    '''volumes = [pool2/volume2, pool3/v, ...]
    '''
    return None


def lichbd_cgsnapshot_create(group_name, snapshot_name):
    '''volumes = [pool2/volume2, pool3/v, ...]
    '''
    return None


def lichbd_cgsnapshot_delete(group_name, snapshot_name):
    '''volumes = [pool2/volume2, pool3/v, ...]
    '''
    return None
