#!/usr/bin/env python2
#-*- coding: utf-8 -*-

import json

from fusionstor import ClusterManager, HostManager, PoolManager, \
        VolumeManager, SnapshotManager, config

print 'ump_init'
config.init_ump("192.168.120.214")
clusterm = ClusterManager()
hostm = HostManager()     
poolm = PoolManager()
volumem =  VolumeManager()
snapshotm = SnapshotManager()

def check_resp(resp, return_code):
    print resp.status_code, return_code
    if resp.status_code != return_code:
        raise Exception("fuck")

def test_base(pool_name):
    _, resp = clusterm.list()
    print 'zz2---cluster --list---', resp
    cluster = resp.records[0]
    assert(len(resp.records) == 1)
    print cluster["disk_used"]
    print cluster["disk_total_gb"]
    print cluster["config_str"]
    config = json.loads(cluster["config_str"])
    print type(cluster)
    print type(cluster["config_str"])
    print type(config)


    _, resp = poolm.create(pool_name, protocol='iscsi')
    print 'zz2---create---', resp
    check_resp(resp, 200)

    _, resp = poolm.stat(pool_name, protocol='iscsi')
    print 'zz2---stat---', resp
    check_resp(resp, 200)

    _, resp = poolm.delete(pool_name, protocol='iscsi')
    print 'zz2---delete---', resp
    check_resp(resp, 200)

    # volume test
    _, resp = poolm.create(pool_name, protocol='iscsi')
    print 'zz2---create---', resp
    check_resp(resp, 200)

    size = "%s" % (1*1024*1024*1024)
    vol_name = '%s/volume-of-%s' % (pool_name, pool_name)
    check_resp(resp, 200)

    _, resp = volumem.create(vol_name, size, provisioning='thin', protocol='iscsi')
    print 'zz2---volume-create---', resp
    check_resp(resp, 200)

    _, resp = volumem.stat(vol_name)
    print 'zz2---volume-stat---', resp
    check_resp(resp, 200)

    _, resp = volumem.stat(vol_name + "xxx")
    print 'zz2---404---volume-stat---', resp
    check_resp(resp, 404)

    newsize = "%s" % (2*1024*1024*1024)
    _, resp = volumem.resize(vol_name, newsize, provisioning='thin', protocol='iscsi')
    print 'zz2---volume-resize---', resp
    check_resp(resp, 200)

    _, resp = volumem.delete(vol_name, provisioning='thin', protocol='iscsi')
    print 'zz2---volume-delete---', resp
    check_resp(resp, 200)

    # snap test
    size = "%s" % (1*1024*1024*1024)
    vol_name = '%s/volume-of-%s-for-snap' % (pool_name, pool_name)
    _, resp = volumem.create(vol_name, size, provisioning='thin', protocol='iscsi')
    print 'zz2---volume-create---', resp
    check_resp(resp, 200)

    snap_name = "snap1"
    snap_path = "%s@%s"% (vol_name, snap_name)
    _, resp = snapshotm.create(snap_path,  protocol='iscsi')
    print 'zz2---snap-create---', resp
    check_resp(resp, 200)

    _, resp = volumem.list_snapshots(vol_name, protocol='iscsi')
    print 'zz2---snap-list---', resp
    print 'zz2---snap-list---', resp.records
    check_resp(resp, 200)

    _, resp = snapshotm.stat(snap_path,  protocol='iscsi')
    print 'zz2---snap-stat--', resp
    check_resp(resp, 200)

    _, resp = snapshotm.protect(snap_path,  protocol='iscsi')
    print 'zz2---snap-clone--', resp
    check_resp(resp, 200)

    vol_name_clone = '%s/volume-of-%s-for-snap-clone' % (pool_name, pool_name)
    _, resp = snapshotm.clone(snap_path, vol_name_clone,  protocol='iscsi')
    print 'zz2---snap-clone--', resp
    check_resp(resp, 200)

    snap_name_2 = "snap2"
    snap_path_2 = "%s@%s"% (vol_name_clone, snap_name_2)
    _, resp = snapshotm.create(snap_path_2,  protocol='iscsi')
    print 'zz2---snap-create-2--', resp
    check_resp(resp, 500)

    vol_name_clone_2 = '%s/volume-of-%s-for-snap-clone-2' % (pool_name, pool_name)
    _, resp = snapshotm.clone(snap_path_2, vol_name_clone_2,  protocol='iscsi')
    print 'zz2---snap-clone-2--', resp
    check_resp(resp, 404)

    # snap_name 是不是可以取消
    # 先不支持flatten
    # _, resp = snapshotm.flatten(vol_name_clone, snap_path,  protocol='iscsi')
    # print 'zz2---snap-stat--', resp

    _, resp = volumem.delete(vol_name_clone_2, provisioning='thin', protocol='iscsi')
    print 'zz2---volume-delete---', resp
    check_resp(resp, 404)

    _, resp = snapshotm.delete(snap_path_2,  protocol='iscsi')
    print 'zz2---snap-stat--', resp
    check_resp(resp, 404)

    _, resp = volumem.delete(vol_name_clone, provisioning='thin', protocol='iscsi')
    print 'zz2---volume-delete---', resp
    check_resp(resp, 200)

    _, resp = snapshotm.protect(snap_path, is_protect=False, protocol='iscsi')
    print 'zz2---snap-clone--', resp
    check_resp(resp, 200)

    _, resp = snapshotm.delete(snap_path,  protocol='iscsi')
    print 'zz2---snap-stat--', resp
    check_resp(resp, 200)

def test_create(pool_name, total):
    _, resp = poolm.create(pool_name, protocol='iscsi')
    print 'zz2---create---', resp
    check_resp(resp, 200)

    for i in range(1, total):
        size = "%s" % (1*1024*1024*1024)
        vol_name = '%s/volume-of-%s-%s' % (pool_name, pool_name, i)

        _, resp = volumem.create(vol_name, size, provisioning='thin', protocol='iscsi')
        print 'zz2---volume-create---', resp
        check_resp(resp, 200)

        _, resp = volumem.delete(vol_name, protocol='iscsi')
        print 'zz2---volume-delete---', resp
        check_resp(resp, 200)


if __name__ == "__main__":
    print 'xxx <pool_name>'
    import sys

    # pool test
    pool_name = sys.argv[1]
    # test_base(pool_name)
    test_create(pool_name+"2", 20)


"""
cluster:
    {u'status': None, u'config_str': u'{"globals.hostname": "site1.zone1.yuan1", "globals.crontab": "on", "metadata.meta": 7, "globals.nohosts": "off", "globals.localize": "on", "globals.testing": "off", "globals.log_max_bytes": 104857600, "iscsi.vip": "", "cdsconf.disk_keep": 10737418240, "globals.storage_area_max_node": 20, "globals.cleanlogcore": "on", "globals.home": "/opt/fusionstack", "globals.lichbd_root": "default", "globals.sheepdog_root": "default", "globals.default_protocol": "nbd", "globals.wmem_max": 1048576000, "globals.cgroup": "off", "globals.nbd_root": "default", "globals.clustername": "test", "cdsconf.use_wlog": 0, "iscsi.port": 3260, "globals.rmem_max": 1048576000, "iscsi.timeout": 300, "iscsi.iqn": "iqn.2016-05-1589.com.huayunwangji", "globals.replica_max": 4}', u'extra': None, u'updated_at': u'2016-09-13 14:22:17', u'mem_total': 6, u'home': u'/opt/fusionstack', u'volume_total': 0.0, u'lichbd_root': u'default', u'deleted_at': None, u'id': 1, u'usage_cpu': u'71.63', u'cpu_frequency': 14999.988000000001, u'license_permit': None, u'capacity': None, u'iscsi_port': 3260, u'usage_mem': 0.5490397931211496, u'deleted': False, u'arbitor_ip': u'', u'avail': None, u'parent_id': None, u'repnum': 2, u'nbd_root': u'default', u'type': None, u'license_capacity': None, u'used': None, u'description': None, u'volume_used': 0.0, u'deleted_friend': u'nerd', u'disk_total': 751619276800.0, u'overbooking': u'100', u'name': u'test', u'is_cluster': False, u'cluster_name': u'test', u'system_createtime': None, u'created_at': u'2016-09-13 10:48:38', u'iqn': u'iqn.2016-05-1589.com.huayunwangji', u'invalid_date': None, u'disk_used': 3.0, u'register_date': None, u'license_stat': None}
"""
"""{u'reply': {u'count': 0, u'is_success': True, u'error': u''}, u'records': {u'status': None, u'size_gb': 1, u'protocol': u'iscsi', u'extra': None, u'updated_at': None, u'used_gb': 0, u'connections': u'0', u'cluster_id': 1, u'deleted_at': None, u'id': 2, u'access_policy_id': None, u'is_boot': None, u'locked_at': u'2016-09-17 11:35:44', u'user_id': 2, u'description': None, u'format': None, u'deleted': False, u'protocol_root': u'iscsi', u'provisioning': u'thin', u'os_version': None, u'protection_domain_id': None, u'repnum': 2, u'username': u'cinder', u'realpath': u'cinder:xxx1/volume_of_xxx1', u'snapshot_time': None, u'qos_id': None, u'deleted_friend': u'nerd', u'is_share': False, u'path': None, u'arch': None, u'name': u'volume_of_xxx1', u'is_locked': False, u'created_at': u'2016-09-17 11:35:44', u'chunkid': None, u'pool_id': 7, u'cgsnapshot_id': None, u'iqn': u'iqn.2016-09-2573.com.huayunwangji:cinder:xxx1.volume_of_xxx1', u'mode': None, u'os_type': None}}, _ResponseInfo__response:<Response [200]>, text_body:{"reply": {"count": 0, "is_success": true, "error": ""}, "records": {"username": "cinder", "size_gb": 1, "protocol": "iscsi", "extra": null, "updated_at": null, "used_gb": 0, "connections": "0", "cluster_id": 1, "deleted_at": null, "id": 2, "snapshot_time": null, "is_boot": null, "locked_at": "2016-09-17 11:35:44", "user_id": 2, "os_version": null, "access_policy_id": null, "qos_id": null, "protocol_root": "iscsi", "provisioning": "thin", "deleted_friend": "nerd", "protection_domain_id": null, "repnum": 2, "status": null, "realpath": "cinder:xxx1/volume_of_xxx1", "description": null, "format": null, "deleted": false, "is_share": false, "cgsnapshot_id": null, "path": null, "arch": null, "name": "volume_of_xxx1", "is_locked": false, "created_at": "2016-09-17 11:35:44", "pool_id": 7, "chunkid": null, "iqn": "iqn.2016-09-2573.com.huayunwangji:cinder:xxx1.volume_of_xxx1", "mode": null, "os_type": null}}, req_id:None)
"""
