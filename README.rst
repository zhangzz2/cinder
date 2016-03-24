======
CINDER
======

1
首先在集群内安装nova 和 lich。

安装：
在controller 节点: 
glance_stor (github)
cinder (github)
nova (github)

在compute节点：
cinder (github)
nova  (github)
libvirtd （git)
qemu (git)

并且在computer节点上定时修改/dev/shm/lich目录的用户为nova:
添加下面行到crontab
*/1 * * * * root chmod -R 777 /dev/shm/lich/

glance_stor:  


2，
上传镜像

注意事项：
a,镜像源必须采用：镜像地址
b,其他非必须项，采用默认值。

3，
云硬盘创建，删除。
创建时，输入磁盘名称和大小，其他为默认值。

4，
启动虚拟机实例

注意事项：
a,云主机启动源 必须选用倒数第二个方式：（从镜像启动，创建一新卷）
b,其他非必选项，采用默认值 或根据需要填写。
c,关机必须是‘关闭实例’。

4，
磁盘挂载
需要通过命令行的方式来挂载磁盘。
在使用命令行之前，需要先加载身份信息：
比如：
[root@controller ~]# cat admin-openrc.sh 
export OS_PROJECT_DOMAIN_ID=default
export OS_USER_DOMAIN_ID=default
export OS_PROJECT_NAME=admin
export OS_TENANT_NAME=admin
export OS_USERNAME=admin
export OS_PASSWORD=mds123
export OS_AUTH_URL=http://controller:35357/v3
export OS_IDENTITY_API_VERSION=3
export OS_IMAGE_API_VERSION=2

通过 sourece命令来加载：
[root@controller ~]# source admin-openrc.sh 
[root@controller ~]# 

然后，通过nova volume-attach 和 nova volume-detach来挂载和卸载。
帮助：
usage: nova volume-attach <server> <volume> [<device>]
usage: nova volume-detach <server> <volume>
例子：
nova volume-attach  2c0a672e-9199-4e57-8eab-e109a5a1485b 46b53b50-5fd8-44d3-8078-cb957a9e1a87
nova volume-detach  2c0a672e-9199-4e57-8eab-e109a5a1485b 46b53b50-5fd8-44d3-8078-cb957a9e1a87


You have come across a storage service for an open cloud computing service.
It has identified itself as `Cinder`. It was abstracted from the Nova project.

* Wiki: http://wiki.openstack.org/Cinder
* Developer docs: http://docs.openstack.org/developer/cinder

Getting Started
---------------

If you'd like to run from the master branch, you can clone the git repo:

    git clone https://github.com/openstack/cinder.git

For developer information please see
`HACKING.rst <https://github.com/openstack/cinder/blob/master/HACKING.rst>`_

You can raise bugs here http://bugs.launchpad.net/cinder

Python client
-------------
https://github.com/openstack/python-cinderclient.git
