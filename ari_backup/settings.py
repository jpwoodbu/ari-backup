from __future__ import with_statement

import yaml

# Reads settings from /etc/ari-backup/ari-backup.conf.yaml and makes them
# available as properties of this module.

try:
    with open('/etc/ari-backup/ari-backup.conf.yaml', 'r') as conf_file:
        conf = yaml.load(conf_file)
except IOError:
    conf = dict()

# let's set some sane defaults
backup_store_path = conf.get('backup_store_path', None)
rdiff_backup_path = conf.get('rdiff_backup_path', '/usr/bin/rdiff-backup')
# TODO consider not setting the remote_user to root by default
remote_user = conf.get('remote_user', 'root')
ssh_path = conf.get('ssh_path', '/usr/bin/ssh')
ssh_compression = conf.get('ssh_compression', False)
snapshot_suffix = conf.get('snapshot_suffix', '-ari_backup')
snapshot_mount_root = conf.get('snapshot_mount_root', '/tmp')
rsync_path = conf.get('rsync_path', '/usr/bin/rsync')
zfs_snapshot_prefix = conf.get('zfs_snapshot_prefix', 'ari-backup-')
debug_logging = conf.get('debug_logging', False)
# TODO review these setting name; What is being retried? Are we sure that's a
# timeout and not a sleep?
max_retries = conf.get('max_retries', 3)
retry_timeout = conf.get('retry_timeout', 60)
