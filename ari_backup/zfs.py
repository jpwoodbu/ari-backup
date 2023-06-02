"""ZFS based backup workflows."""
import datetime
import shlex

from absl import flags

from ari_backup import lvm
from ari_backup import workflow


FLAGS = flags.FLAGS
flags.DEFINE_string('rsync_options',
                    '--archive --acls --numeric-ids --delete --inplace',
                    'rsync command options')
flags.DEFINE_string('rsync_path', '/usr/bin/rsync', 'path to rsync binary')
flags.DEFINE_string('zfs_snapshot_prefix', 'ari-backup-',
                    'prefix for historical ZFS snapshots')
flags.DEFINE_string(
    'zfs_snapshot_timestamp_format', '%Y-%m-%d--%H%M',
    'strftime() formatted timestamp used when naming new ZFS snapshots')


class ZFSLVMBackup(lvm.LVMSourceMixIn, workflow.BaseWorkflow):
    """Workflow for backing up a logical volume to a ZFS dataset.

    Data is copied from and LVM snapshot to a ZFS dataset using rsync and then
    ZFS commands are issued to create historical snapshots. The ZFS snapshot
    lifecycle is also managed by this class. When a backup completes, snapshots
    older than snapshot_expiration_days are destroyed.

    This approach has some benefits over rdiff-backup in that all backup
    datapoints are easily browseable and replication of the backup data using
    ZFS streams is generally less resource intensive than using something like
    rsync to mirror the files created by rdiff-backup.

    One downside is that it's easier to store all file metadata using
    rdiff-backup. Rsync can only store metadata for files that the destination
    file system can also store. For example, if extended file system
    attributes are used on the source file system, but aren't available on the
    destination, rdiff-backup will still record those attributes in its own
    files. If faced with that same scenario, rsync would lose those attributes.
    Furthermore, rsync must have root privilege to write arbitrary file
    metadata.

    New post-job hooks are added for creating ZFS snapshots and trimming old
    ones.
    """
    def __init__(self,
                 label: str,
                 source_hostname: str,
                 rsync_dst: str,
                 zfs_hostname: str,
                 dataset_name: str,
                 snapshot_expiration_days: int,
                 **kwargs):
        """Configure a ZFSLVMBackup object.

        Args:
            label: label for the backup job (e.g. database-server1).
            source_hostname: the name of the host with the source data to
                backup.
            rsync_dst: the destination argument for the rsync command line
                (e.g. backupbox:/backup-store/database-server1).
            zfs_hostname: the name of the backup destination host where we will
                be managing the ZFS snapshots.
            dataset_name: the full ZFS path (not file system path) to the
                dataset holding the backups for this job
                (e.g. tank/backup-store/database-server1).
            snapshot_expiration_days: the maxmium age of a ZFS snapshot in
                days.

        Pro tip: It's a good practice to reuse the label argument as the last
        path component in the rsync_dst and dataset_name arguments.
        """
        # Call our super class's constructor to enable LVM snapshot management
        super().__init__(label, **kwargs)

        # Assign instance vars specific to this class.
        self.source_hostname = source_hostname
        self.rsync_dst = rsync_dst
        self.zfs_hostname = zfs_hostname
        self.dataset_name = dataset_name

        # Assign flags to instance vars so they might be easily overridden in
        # workflow configs.
        self.rsync_options = FLAGS.rsync_options
        self.rsync_path = FLAGS.rsync_path
        self.zfs_snapshot_prefix = FLAGS.zfs_snapshot_prefix
        self.zfs_snapshot_timestamp_format = \
            FLAGS.zfs_snapshot_timestamp_format

        self.add_post_hook(self._create_zfs_snapshot)
        self.add_post_hook(self._destroy_expired_zfs_snapshots,
                           {'days': snapshot_expiration_days})

    def _get_current_datetime(self) -> datetime.datetime:
        """Returns datetime object with the current date and time.

        This method is mostly useful for testing purposes.
        """
        return datetime.datetime.now()

    def _run_custom_workflow(self) -> None:
        """Run rsync backup of LVM snapshot to ZFS dataset."""
        # TODO(jpwoodbu) Consider throwing an exception if we see things in the
        # include or exclude lists since we don't use them in this class.
        self.logger.debug('ZFSLVMBackup._run_custom_workflow started.')

        # Since we're dealing with ZFS datasets, let's always exclude the .zfs
        # directory in our rsync options.
        rsync_options = shlex.split(self.rsync_options) + \
            ['--exclude', '/.zfs']

        # We add a trailing slash to the src path otherwise rsync will make a
        # subdirectory at the destination, even if the destination is already a
        # directory.
        rsync_src = self._snapshot_mount_point_base_path + '/'

        command = [self.rsync_path] + rsync_options + \
            [rsync_src, self.rsync_dst]
        self.run_command(command, self.source_hostname)
        self.logger.debug('ZFSLVMBackup._run_custom_workflow completed.')

    def _create_zfs_snapshot(self, error_case: bool) -> None:
        """Creates a new ZFS snapshot of our destination dataset.

        The name of the snapshot will include the zfs_snapshot_prefix provided
        by FLAGS and a timestamp. The zfs_snapshot_prefix is used by
        _remove_zfs_snapshots_older_than() when deciding which snapshots to
        destroy. The timestamp encoded in a snapshot name is only for end-user
        convenience. The creation metadata on the ZFS snapshot is what is used
        to determine a snapshot's age.

        This method does nothing if error_case is True.

        Args:
            error_case: whether an error has occurred during the backup.
        """
        if not error_case:
            self.logger.info('Creating ZFS snapshot...')
            timestamp = self._get_current_datetime().strftime(
                self.zfs_snapshot_timestamp_format)
            snapshot_name = self.zfs_snapshot_prefix + timestamp
            snapshot_path = '{dataset_name}@{snapshot_name}'.format(
                dataset_name=self.dataset_name, snapshot_name=snapshot_name)
            command = ['zfs', 'snapshot', snapshot_path]
            self.run_command(command, self.zfs_hostname)

    def _find_snapshots_older_than(self, days: int) -> list[str]:
        """Returns snapshots older than the given number of days.

        Only snapshots that meet the following criteria are returned:
            1. They were created at least "days" ago.
            2. Their name is prefixed with FLAGS.zfs_snapshot_prefix.

        Args:
            days: the minimum age of the snapshots in days.

        Returns:
            A list of filtered snapshots.
        """
        expiration = self._get_current_datetime() - \
            datetime.timedelta(days=days)
        # Let's find all the snapshots for this dataset.
        command = ['zfs', 'get', '-rH', '-o', 'name,value', 'type',
                   self.dataset_name]
        stdout, unused_stderr = self.run_command(command, self.zfs_hostname)

        snapshots = list()
        # Sometimes we get extra lines which are empty, so we'll strip the
        # lines.
        for line in stdout.strip().splitlines():
            name, dataset_type = line.split('\t')
            if dataset_type == 'snapshot':
                # Let's try to only consider destroying snapshots made by us ;)
                if name.split('@')[1].startswith(self.zfs_snapshot_prefix):
                    snapshots.append(name)

        expired_snapshots = list()
        for snapshot in snapshots:
            creation_time = self._get_snapshot_creation_time(snapshot)
            if creation_time <= expiration:
                expired_snapshots.append(snapshot)

        return expired_snapshots

    def _get_snapshot_creation_time(self, snapshot: str) -> datetime.datetime:
        """Gets the creation time of a snapshot as a Python datetime object

        Args:
            snapshot: the full ZFS path to the snapshot.

        Returns:
            The creation time of the snapshot.
        """
        command = ['zfs', 'get', '-H', '-o', 'value', 'creation', snapshot]
        stdout, unused_stderr = self.run_command(command, self.zfs_hostname)
        return datetime.datetime.strptime(stdout.strip(), '%a %b %d %H:%M %Y')

    def _destroy_expired_zfs_snapshots(
            self, days: int, error_case: bool) -> None:
        """Destroy snapshots older than the given numnber of days.

        Any snapshots in the target dataset with a name that starts with
        FLAGS.zfs_snapshot_prefix and a creation date older than days will be
        destroyed. Depending on the size of the snapshots and the performance
        of the disk subsystem, this operation could take a while.

        This method does nothing if error_case is True.

        Args:
            days: the max age of a snapshot in days.
            error_case: whether an error has occurred during the backup.
        """
        if not error_case:
            self.logger.info('Looking for expired ZFS snapshots...')
            snapshots = self._find_snapshots_older_than(days)
            # Sentinel value used to log if we destroyed no snapshots.
            snapshots_destroyed = False

            # Destroy expired snapshots.
            for snapshot in snapshots:
                command = ['zfs', 'destroy', snapshot]
                self.run_command(command, self.zfs_hostname)
                snapshots_destroyed = True
                self.logger.info(
                    '{snapshot} destroyed.'.format(snapshot=snapshot))

            if not snapshots_destroyed:
                self.logger.info('Found no expired ZFS snapshots.')
