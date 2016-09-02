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

import errno
import time

from oslo_log import log as logging

LOG = logging.getLogger(__name__)

def get_proto():
    return 'iscsi'

class ShellError(Exception):
    '''shell error'''
    
class ShellCmd(object):
    '''
    classdocs
    '''
    
    def __init__(self, cmd, workdir=None, pipe=True):
        '''
        Constructor
        '''
        self.cmd = cmd
        if pipe:
            self.process = subprocess.Popen(cmd, shell=True,
                    stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                    stderr=subprocess.PIPE, executable='/bin/sh', cwd=workdir)
        else:
            self.process = subprocess.Popen(cmd,
                    shell=True, executable='/bin/sh', cwd=workdir)
            
        self.stdout = None
        self.stderr = None
        self.return_code = None

    def raise_error(self):
        err = []
        err.append('failed to execute shell command: %s' % self.cmd)
        err.append('return code: %s' % self.process.returncode)
        err.append('stdout: %s' % self.stdout)
        err.append('stderr: %s' % self.stderr)

        raise ShellError('\n'.join(err))
        
    def __call__(self, is_exception=True):
        if logcmd:
            LOG.debug(self.cmd)
            
        (self.stdout, self.stderr) = self.process.communicate()
        self.return_code = self.process.returncode
        if is_exception and self.process.returncode != 0:
            self.raise_error()

        return self.stdout

def __call_shellcmd(cmd, exception=False, workdir=None):
    shellcmd = ShellCmd(cmd, workdir)
    shellcmd(exception)
    return shellcmd

def call_try(cmd, exception=False, workdir=None, try_num = None):
    if try_num is None:
        try_num = 10

    shellcmd = None
    for i in range(try_num):
        shellcmd = __call_shellcmd(cmd, False, workdir)
        if shellcmd.return_code in [0, errno.EEXIST, errno.ENOENT]:
            break

        time.sleep(1)

    return shellcmd

def raise_exp(shellcmd):
    err = []
    err.append('failed to execute shell command: %s' % shellcmd.cmd)
    err.append('return code: %s' % shellcmd.process.returncode)
    err.append('stdout: %s' % shellcmd.stdout)
    err.append('stderr: %s' % shellcmd.stderr)
    raise ShellError('\n'.join(err))

def lichbd_config():
    pass

def lichbd_get_iqn():
    shellcmd = call_try(
            """lich  configdump 2>/dev/null|grep iqn|awk -F":" '{print $2}'""")
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    iqn = shellcmd.stdout.strip()
    return iqn

def lichbd_get_qemu_path():
    qemu_path = "/opt/fusionstack/qemu/bin/qemu-system-x86_64"
    return qemu_path 

def lichbd_get_qemu_img_path():
    qemu_path = "/opt/fusionstack/qemu/bin/qemu-img"
    return qemu_path

def lichbd_mkpool(path):
    proto = get_proto()
    shellcmd = call_try('lichbd mkpool %s -p %s 2>/dev/null' % (path, proto))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

def lichbd_lspools():
    proto = get_proto()
    shellcmd = call_try('lichbd lspools -p %s 2>/dev/null' % proto)
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    pools = []
    for pool in shellcmd.stdout.strip().split():
        pools.append(pool.strip())

    return pools

def lichbd_pool_exist(path):
    pools = lichbd_lspools()
    return (path in pools)

def lichbd_rmpool(path):
    proto = get_proto()
    shellcmd = call_try('lichbd rmpool %s -p %s 2>/dev/null' % (path, proto))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

def lichbd_create(path, size):
    proto = get_proto()
    cmd = 'lichbd create %s --size %s -p %s 2>/dev/null' % (path, size, proto)
    shellcmd = call_try(cmd)
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

def lichbd_resize(path, size):
    proto = get_proto()
    cmd = "lichbd resize %s --size %s -p %s 2>/dev/null" % (path, size, proto)
    shellcmd = call_try(cmd)
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

def lichbd_create_raw(path, size):
    lichbd_create(path, size)

def lichbd_copy(src_path, dst_path):
    shellcmd = None
    proto = get_proto()
    cmd = 'lichbd copy %s %s -p %s 2>/dev/null' % (src_path, dst_path, proto)
    shellcmd = call_try(cmd)
    if shellcmd.return_code == 0:
        return shellcmd
    else:
        if dst_path.startswith(":"):
            call("rm -rf %s" % (dst_path.lstrip(":")))
        else:
            lichbd_rm(dst_path)

    raise_exp(shellcmd)

def lichbd_import(src_path, dst_path):
    shellcmd = None
    proto = get_proto()
    cmd = 'lichbd import %s %s -p %s 2>/dev/null' % (src_path, dst_path, proto)
    shellcmd = call_try(cmd)
    if shellcmd.return_code == 0:
        return shellcmd
    else:
        lichbd_rm(dst_path)

    raise_exp(shellcmd)

def lichbd_export(src_path, dst_path):
    shellcmd = None
    proto = get_proto()
    cmd = 'lichbd export %s %s -p %s 2>/dev/null' % (src_path, dst_path, proto)
    shellcmd = call_try(cmd)
    if shellcmd.return_code == 0:
        return shellcmd
    else:
        call("rm -rf %s" % dst_path)

    raise_exp(shellcmd)

def lichbd_rm(path):
    proto = get_proto()
    shellcmd = call_try('lichbd rm %s -p %s 2>/dev/null' % (path, proto))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.ENOENT:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_mv(dist, src):
    proto = get_proto()
    cmd = 'lichbd mv %s %s -p %s 2>/dev/null' % (src, dist, proto)
    shellcmd = call_try(cmd)
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

def lichbd_flatten(path):
    #todo 实现flatten
    return None
    proto = get_proto()
    cmd = 'lich.inspect flat %s 2>/dev/null' % ("%s/%s" % (proto, path))
    shellcmd = call_try(cmd)
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

def lichbd_volume_info(path):
    proto = get_proto()
    shellcmd = call_try("lichbd info %s -p %s" % (path, proto))

    return shellcmd.stdout.strip()

def lichbd_volume_exist(path):
    proto = get_proto()
    shellcmd = call_try("lichbd info %s -p %s" % (path, proto))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == 2:
            return False
        elif shellcmd.return_code == 21:
            return True
        else:
            raise_exp(shellcmd)
    return True

def lichbd_cluster_stat():
    shellcmd = call_try('lich stat --human-unreadable 2>/dev/null')
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_get_used():
    o = lichbd_cluster_stat()
    for l in o.split("\n"):
        if 'used:' in l:
            used = long(l.split("used:")[-1])
            return used

    raise ShellError('lichbd_get_used')

def lichbd_get_capacity():
    try:
        o = lichbd_cluster_stat()
    except Exception, e:
        raise ShellError('lichbd_get_capacity')

    total = 0
    used = 0
    for l in o.split("\n"):
        if 'capacity:' in l:
            total = long(l.split("capacity:")[-1])
        elif 'used:' in l:
            used = long(l.split("used:")[-1])

    return total, used

def lichbd_snap_create(snap_path):
    proto = get_proto()
    shellcmd = call_try('lichbd snap create %s -p %s' % (snap_path, proto))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_list(image_path):
    snaps = []
    proto = get_proto()
    cmd = 'lichbd snap ls %s -p %s 2>/dev/null' % (image_path, proto)
    shellcmd = call_try(cmd)
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    for snap in shellcmd.stdout.strip().split():
        snaps.append(snap.strip())

    return snaps

def lichbd_snap_exist(snap_path):
    image_path = snap_path.split("@")[0]
    snap = snap_path.split("@")[1]
    snaps = lichbd_snap_list(image_path)

    return (snap in sanps)

def lichbd_snap_delete(snap_path):
    proto = get_proto()
    cmd = 'lichbd snap remove %s -p %s' % (snap_path, proto)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        #126 is ENOKEY 
        if shellcmd.return_code == 126:
            pass
        else:
            raise_exp(shellcmd)

    return shellcmd.stdout
 
def lichbd_snap_clone(src, dst):
    proto = get_proto()
    cmd = 'lichbd clone %s %s -p %s' % (src, dst, proto)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_rollback(snap_path):
    proto = get_proto()
    cmd = 'lichbd snap rollback %s -p %s' % (snap_path, proto)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_protect(snap_path):
    proto = get_proto()
    cmd = 'lichbd snap protect %s -p %s' % (snap_path, proto)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_unprotect(snap_path):
    proto = get_proto()
    cmd = 'lichbd snap unprotect %s -p %s' % (snap_path, proto)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout
