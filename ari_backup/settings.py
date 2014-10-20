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

# The top_level_src_dir setting is used to define the context for the backup
# mirror. This is especially handy when backing up mounted spanshots so
# that the mirror doesn't also include the directory in which the
# snapshot is mounted.
#
# For example, if our source data is /tmp/database-server1_snapshot and
# our destination directory is /backup-store/database-server1, then
# setting the top_level_src_dir to '/' would build your backup mirror at
# /backup-store/database-server1/tmp/database-server1_snapshot. If you
# instead set the top_level_src_dir to '/tmp/database-server1_snapshot'
# then your backup mirror would be built at
# /backup-store/database-server1, which is probably what you want.
top_level_src_dir = conf.get('top_level_src_dir', '/')
snapshot_suffix = conf.get('snapshot_suffix', '-ari_backup')
snapshot_mount_root = conf.get('snapshot_mount_root', '/tmp')
rsync_path = conf.get('rsync_path', '/usr/bin/rsync')
rsync_options = conf.get('rsync_options',
                         '--archive --acls --numeric-ids --delete --inplace')
zfs_snapshot_prefix = conf.get('zfs_snapshot_prefix', 'ari-backup-')
debug_logging = conf.get('debug_logging', False)
dry_run = conf.get('dry_run', False)
# TODO review these setting name; What is being retried? Are we sure that's a
# timeout and not a sleep?
max_retries = conf.get('max_retries', 3)
retry_timeout = conf.get('retry_timeout', 60)
