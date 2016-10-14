#!/usr/bin/env python2
#-*- coding: utf-8 -*-

import time
import uuid

from cinder.volume.drivers.huayunwangji.lichbd_localcmd import call_try, raise_exp

def call_assert(cmd, return_code = None, p=True):
    if p:
        print 'call', cmd

    shellcmd = call_try(cmd, try_num=1)
    if return_code is not None:
        if (shellcmd.return_code != return_code):
            print shellcmd.process.returncode
            print shellcmd.stdout
            print shellcmd.stderr
            raise_exp(shellcmd)

    return shellcmd

def test_get_id(name):
    cmd = "cinder list | grep %s |awk '{print $2}'" % (name)
    shellcmd = call_assert(cmd, 0)
    return shellcmd.stdout.strip() 

def test_get_snap_id(volume_id, name):
    cmd = "cinder snapshot-list | grep %s |grep %s|awk '{print $2}'" % (volume_id, name)
    shellcmd = call_assert(cmd, 0)
    return shellcmd.stdout.strip() 

def test_get_image_id(name):
    cmd = "openstack image list | grep %s|awk '{print $2}'" % (name)
    shellcmd = call_assert(cmd, 0)
    return shellcmd.stdout.strip()

def test_wait_snapshot_available(name):
    while True:
        cmd = "cinder snapshot-list | grep %s|awk '{print $6}'" % (name)
        shellcmd = call_assert(cmd, 0)
        status = shellcmd.stdout.strip()
        if status == 'available':
            break
        else:
            print 'wait %s active, now: %s' % (name, status)
        time.sleep(3)

def test_wait_volume_available(name):
    while True:
        cmd = "cinder list | grep %s|awk '{print $4}'" % (name)
        shellcmd = call_assert(cmd, 0)
        status = shellcmd.stdout.strip()
        if status == 'available':
            break
        else:
            print 'wait %s active, now: %s' % (name, status)
        time.sleep(3)

def test_wait_image_active(name):
    while True:
        cmd = "openstack image list | grep %s|awk '{print $6}'" % (name)
        shellcmd = call_assert(cmd, 0)
        status = shellcmd.stdout.strip()
        if status == 'active':
            break
        else:
            print 'wait %s active, now: %s' % (name, status)
        time.sleep(3)

def test_volume_2():
    # ==============
    print 'create volume'

    volume_name = 'test_volume_001_' + uuid.uuid4().__str__()
    size = 1
    cmd = "cinder create --name %s %s" % (volume_name, size)
    call_assert(cmd, 0)
    test_wait_volume_available(volume_name)

    volume_id = test_get_id(volume_name)

    # ==============
    print 'upload volume to image'

    image_name = 'image_upload_from_' + volume_name
    cmd = 'cinder upload-to-image %s %s' % (volume_id, image_name)
    call_assert(cmd, 0)
    test_wait_image_active(image_name)

    image_id = test_get_image_id(image_name)

    # ==============
    print 'delete volume'

    cmd = "cinder delete %s" % (volume_id)
    call_assert(cmd, 0)

    # ==============
    print 'delete image'

    cmd = "openstack image delete %s" % (image_id)
    call_assert(cmd, 0)

    # ==============
    print 'test ok'


def test_volume_1():
    # ==============
    image_file = '/root/fake_tmp_image'
    for i in range(10):
        cmd = "echo %s > %s" % ('test'*1024, image_file)
        call_assert(cmd, 0, p=False)

    print 'create image'
    image_name = "test_image" + uuid.uuid4().__str__()
    cmd = "openstack image create %s --file %s --disk-format raw --public" % (image_name, image_file)
    call_assert(cmd, 0)
    test_wait_image_active(image_name)

    image_id = test_get_image_id(image_name)

    # ==============
    print 'create volume'

    volume_name = 'test_volume_001_' + uuid.uuid4().__str__()
    size = 1
    cmd = "cinder create --name %s %s" % (volume_name, size)
    call_assert(cmd, 0)
    test_wait_volume_available(volume_name)

    volume_id = test_get_id(volume_name)

    # ==============
    print 'extend volume'

    new_size = 2
    cmd = "cinder extend %s %s" % (volume_id, new_size)
    call_assert(cmd, 0)
    test_wait_volume_available(volume_name)

    # ==============
    print 'create snap'

    snap_name = "snap1" + uuid.uuid4().__str__()
    cmd = "cinder snapshot-create --name %s %s" % (snap_name, volume_id)
    call_assert(cmd, 0)
    test_wait_snapshot_available(snap_name)
    snap_id = test_get_snap_id(volume_id, snap_name)

    # ==============
    print 'create from snap'

    volume_name_from_snap = volume_name + 'clone'
    cmd = "cinder create --name %s  --snapshot-id %s %s" % (volume_name_from_snap, snap_id, new_size)
    call_assert(cmd, 0)
    test_wait_volume_available(volume_name_from_snap)

    volume_name_from_snap_id = test_get_id(volume_name_from_snap)

    # ==============
    print 'create from image'

    volume_name_from_image = volume_name + 'image'
    cmd = "cinder create --name %s  --image-id %s %s" % (volume_name_from_image, image_id, new_size)
    call_assert(cmd, 0)
    test_wait_volume_available(volume_name_from_image)

    volume_name_from_image_id = test_get_id(volume_name_from_image)

    # ==============
    print 'create from volume'

    volume_name_from_volume = volume_name + 'volume'
    cmd = "cinder create --name %s  --source-volid %s %s" % (volume_name_from_volume, volume_id, new_size)
    call_assert(cmd, 0)
    test_wait_volume_available(volume_name_from_volume)

    volume_name_from_volume_id = test_get_id(volume_name_from_volume)

    # ==============
    print 'delete volume_from_volume'

    cmd = "cinder delete %s" % (volume_name_from_volume_id)
    call_assert(cmd, 0)

    # ==============
    print 'delete volume_from_image'

    cmd = "cinder delete %s" % (volume_name_from_image_id)
    call_assert(cmd, 0)

    # ==============
    print 'delete volume_from_snap'

    cmd = "cinder delete %s" % (volume_name_from_snap_id)
    call_assert(cmd, 0)

    # ==============
    print 'delete snapshot'

    cmd = "cinder snapshot-delete %s" % (snap_id)
    call_assert(cmd, 0)

    # ==============
    print 'delete volume'

    cmd = "cinder delete %s" % (volume_id)
    call_assert(cmd, 0)

    # ==============
    print 'delete image'

    cmd = "openstack image delete %s" % (image_id)
    call_assert(cmd, 0)

    # ==============

    print 'test ok'

if __name__ == "__main__":
    print "hello, word!"
    test_volume_1()
    test_volume_2()
