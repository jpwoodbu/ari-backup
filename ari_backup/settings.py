from __future__ import with_statement

import yaml

from logger import Logger

# Reads and validates settings from /etc/ari-backup/ari-backup.conf.yaml and
# makes them available as properties of this module.  

# let's set some sane defaults
rdiff_backup_path = '/usr/bin/rdiff-backup'
# TODO consider not setting the remote_user to root by default
remote_user = 'root'
ssh_path = '/usr/bin/ssh'
ssh_compression = False
snapshot_suffix = '-ari_backup'
rsync_path = '/usr/bin/rsync'
zfs_snapshot_prefix = 'ari-backup-'
debug_logging = False
max_retries = 3
retry_timeout = 60

# setup logging
log = Logger('ARIBackup (settings)')

with open('/etc/ari-backup/ari-backup.conf.yaml', 'r') as conf_file:
    conf = yaml.load(conf_file)

# Any supported settings should be included in this block, otherwise
# they won't become attributes of the settings module.
# TODO We need a way for extensions to ARIBackup to register settings
for k, v in conf.iteritems():
    if k == 'backup_store_path': backup_store_path = v
    elif k == 'rdiff_backup_path': rdiff_backup_path = v
    elif k == 'remote_user': remote_user = v
    elif k == 'ssh_compression': ssh_compression = v
    elif k == 'ssh_path': ssh_path = v
    elif k == 'snapshot_mount_root': snapshot_mount_root = v
    elif k == 'snapshot_suffix': snapshot_suffix = v
    elif k == 'rsync_path': rsync_path = v
    elif k == 'rsync_options': rsync_options = v
    elif k == 'zfs_snapshot_prefix': zfs_snapshot_prefix = v
    elif k == 'debug_logging': debug_logging = v
    elif k == 'max_retries': max_retries = v
    elif k == 'retry_timeout': retry_timeout = v
    else:
        log.warning('{key}:{value} is not a recognized setting'.format(key=k, value=v))
