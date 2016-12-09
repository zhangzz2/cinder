# Copyright 2016 Huayunwangji Corp.
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
import json

from cinder.i18n import _LE
# from cinder.i18n import _, _LW, _LE, _LI

from oslo_log import log as logging

import fusionstor
from cinder.volume.drivers.huayunwangji.lichbd_common import LichbdError

LOG = logging.getLogger(__name__)

# https://wiki.openstack.org/wiki/Cinder/how-to-contribute-a-driver

clusterm = None
hostm = None
poolm = None
volumem = None
snapshotm = None
cgsnapshotm = None
consistencygroupm = None


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
        LOG.error(_LE(resp))
        raise_exp(resp, 'not ok')


def lichbd_get_proto():
    return 'iscsi'


def __lichbd_get_cluster():
    _, resp = clusterm.list()
    if (len(resp.records) != 1):
        raise_exp(resp, "cluster not only")

    check_resp(resp)
    cluster = resp.records[0]
    cluster.update({"config_dict": json.loads(cluster["config_str"])})
    return cluster


def lichbd_get_iqn():
    cluster = __lichbd_get_cluster()
    return cluster["config_dict"]["iscsi.iqn"]


def lichbd_get_vip():
    cluster = __lichbd_get_cluster()
    return cluster["vip"]


def lichbd_get_port():
    cluster = __lichbd_get_cluster()
    return cluster["config_dict"]["iscsi.port"]


def lichbd_get_used():
    cluster = __lichbd_get_cluster()
    return long(cluster["disk_used"]) / (1024 ** 3)


def lichbd_get_capacity():
    cluster = __lichbd_get_cluster()
    return cluster["disk_total_gb"]


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
    size = int(size)
    _, resp = volumem.create(path, size,
                             protocol='iscsi', provisioning='thin')
    check_resp(resp)


def lichbd_volume_resize(path, size):
    size = int(size)
    _, resp = volumem.resize(path, size, protocol='iscsi')
    check_resp(resp)


def lichbd_volume_delete(path):
    _, resp = volumem.delete(path, protocol='iscsi')
    if resp.status_code == 404:
        return None

    check_resp(resp)


def lichbd_volume_rename(src, dist):
    LOG.debug("rename %s to %s" % (src, dist))
    _, resp = volumem.rename(src, path2=dist, protocol='iscsi')
    check_resp(resp)


def lichbd_volume_flatten(path):
    raise Exception("unsupport")
    _, resp = volumem.flatten(path, protocol='iscsi')
    check_resp(resp)


def lichbd_volume_stat(path):
    """size =  stat['size_gb']
    'source_snapshot': u'/iscsi/cinder:zxdd/volume_of_zxdd_for_snap@snap1'
    'iqn': u'iqn.2016-09-4821.com.huayunwangji
           :cinder:asdfxxd.volume_of_asdfxxd'
    """
    _, resp = volumem.stat(path, protocol='iscsi')
    check_resp(resp)
    stat = resp.records
    return stat


def lichbd_volume_exist(path):
    _, resp = volumem.stat(path, protocol='iscsi')
    if resp.status_code == 404:
        return False

    if resp.status_code == 200:
        return True

    check_resp(resp)
    raise


def lichbd_volume_copy(src, dst):
    raise Exception("unsupport, please set max_clone_depth > 0")
    _, resp = volumem.copy(src, dst, protocol='iscsi')
    check_resp(resp)


def lichbd_snap_create(snap_path):
    _, resp = snapshotm.create(snap_path, protocol='iscsi')
    check_resp(resp)


def lichbd_snap_exist(snap_path):
    _, resp = snapshotm.stat(snap_path, protocol='iscsi')
    if resp.status_code == 404:
        return False

    if resp.status_code == 200:
        return True

    check_resp(resp)
    raise


def lichbd_snap_delete(snap_path):
    _, resp = snapshotm.delete(snap_path, protocol='iscsi')
    if resp.status_code == 404:
        return None

    check_resp(resp)


def lichbd_snap_list(image_path):
    _, resp = volumem.list_snapshots(image_path, protocol='iscsi')
    check_resp(resp)

    snaps = []
    for snap in resp.records:
        snaps.append("%s@%s" % (image_path, snap["name"]))

    return snaps


def lichbd_snap_clone(src, dst):
    _, resp = snapshotm.clone(src, dst, protocol='iscsi')
    check_resp(resp)


def lichbd_snap_protect(snap_path):
    _, resp = snapshotm.protect(snap_path, is_protect=True, protocol='iscsi')
    check_resp(resp)


def lichbd_snap_unprotect(snap_path):
    _, resp = snapshotm.protect(snap_path, is_protect=False, protocol='iscsi')
    check_resp(resp)


def lichbd_cg_create(group_name):
    _, resp = consistencygroupm.create(group_name, protocol='iscsi')
    check_resp(resp)

def lichbd_cg_delete(group_name):
    _, resp = consistencygroupm.delete(group_name, protocol='iscsi')
    check_resp(resp)

def lichbd_cg_add_volume(group_name, volumes):
    '''volumes = [pool2/volume2, pool3/v, ...]
    '''
    _, resp = consistencygroupm.add(group_name, volumes, protocol='iscsi')
    check_resp(resp)

def lichbd_cg_remove_volume(group_name, volumes):
    '''volumes = [pool2/volume2, pool3/v, ...]
    '''
    _, resp = consistencygroupm.remove(group_name, volumes, protocol='iscsi')
    check_resp(resp)


def lichbd_cgsnapshot_create(group_name, snapshot_name):
    '''volumes = [pool2/volume2, pool3/v, ...]
    '''
    _, resp = cgsnapshotm.create(group_name, snapshot_name, protocol='iscsi')
    check_resp(resp)


def lichbd_cgsnapshot_delete(cgsnapshot_name):
    '''volumes = [pool2/volume2, pool3/v, ...]
    '''
    _, resp = cgsnapshotm.delete(cgsnapshot_name, protocol='iscsi')
    check_resp(resp)


def lichbd_init(host, port, username, password):
    fusionstor.config.init_ump(host, port, username, password)

    # LOG.error(_LE("%s %s" % (host, port)))

    global clusterm
    global hostm
    global poolm
    global volumem
    global snapshotm
    global consistencygroupm
    global cgsnapshotm

    clusterm = fusionstor.ClusterManager()
    hostm = fusionstor.HostManager()
    poolm = fusionstor.PoolManager()
    volumem = fusionstor.VolumeManager()
    snapshotm = fusionstor.SnapshotManager()
    consistencygroupm = fusionstor.VGroupManager()
    cgsnapshotm = fusionstor.CGSnapshotManager()
