import os
import settings
import subprocess
import shlex

from logger import Logger

"""Wrapper around rdiff-backup

This module provides facilites for centrally managing a large set of
rdiff-backup backup jobs.  Backup job management is built around common tools
like cron, run-parts, and xargs.  The base features include:
* centralzed configuration
* support for backing up local and remote hosts
* configurable job parallelization
* ability to run arbitrary commands locally or remotely before and/or after
  backup jobs (something especially handy for preparing databases pre-backup)
* logging to syslog

The base features are designed to be extended and we include an extension to
manage the setup and tear down of LVM snapshots for backup.

"""

class ARIBackup(object):
    """Base class with core features and basic rdiff-backup functionality.

    This class can be used if all that is needed is to leverage the basic
    rdiff-backup features.  The pre and post hook functionality as well as
    command execution is also part of this class.

    """ 
    def __init__(self, label, source_hostname, remove_older_than_timespec=None):
        """Configure an ARIBackup object.
 
        args:
        label -- a str to label the backup job 
        source_hostname -- the name of the host with the source data to backup

        kwargs:
        remove_older_than_timespec -- a string representing the maximum age of
            a backup datapoint (uses the same format as the --remove-older-than
            argument for rdiff-backup)

        """
        # The name of the backup job (this will be the name of the directory in the backup store
        # that has the data).
        self.label = label

        # This is the host that has the source data.
        self.source_hostname = source_hostname

        # We'll bring in the remote_user from our settings, but it is a var
        # that the end-user is welcome to override.
        self.remote_user = settings.remote_user

        # setup logging
        self.logger = Logger('ARIBackup ({label})'.format(label=label), settings.debug_logging)

        # Include nothing by default
        self.include_dir_list = []
        self.include_file_list = []
        # Exclude nothing by default
        # We'll put the '**' exclude on the end of the arg_list later
        self.exclude_dir_list = []
        self.exclude_file_list = []

        # initialize hook lists
        self.pre_job_hook_list = []
        self.post_job_hook_list = []

        if remove_older_than_timespec is not None:
            self.post_job_hook_list.append((
                self._remove_older_than,
                {'timespec': remove_older_than_timespec}))

    def _process_pre_job_hooks(self):
        """Executes pre-job hook functions.

        The self.pre_job_hook_list is a list of tuples, each with two
        elements, the first of which is a reference to a hook function, the
        second is a dictionary of keyword arguments to pass to the hook
        function. We loop over this list and call each pre-job hook function
        with its corresponding arguments.

        """ 
        self.logger.info('processing pre-job hooks...')
        for task in self.pre_job_hook_list:
            # Let's do some assignments for readability
            hook = task[0]
            kwargs = task[1]
            hook(**kwargs)

    def _process_post_job_hooks(self, error_case):
        """Executes post-job hook functions.

        args:
        error_case -- bool indicating if an error occured in pre-job hooks or
            in _run_backup()

        This method works almost identically to _process_pre_job_hooks(), with
        the additional functionality of handling error cases, usually used to
        perform a cleanup operation (e.g. deleting a snapshot).

        Each post-job function must accept a boolean error_case argument.
        However, it is entrirely up to the post-job function to decide what
        behavior to change when error_case is True. For example, if the
        post-job function deletes old backups it may want to skip that
        operation when error_case is True to avoid reducing the number of data
        points in the backup history.
        
        """
        if error_case:
            self.logger.error('processing post-job hooks for error case...')
        else:
            self.logger.info('processing post-job hooks...')

        for task in self.post_job_hook_list:
            # Let's do some assignments for readability
            hook = task[0]
            kwargs = task[1]
            kwargs['error_case'] = error_case
            hook(**kwargs)

    def _run_command(self, command, host='localhost'):
        """Runs an arbitrary command on host.

        args:
        command -- str or list representing a command line

        kwargs:
        host -- hostname for the host on which the command will be executed

        Given the command argument, which can be either a command line string
        or a list of command line arguments, we attempt to execute it on the host
        named in the host argument via SSH, or locally if host is "localhost".

        Returns a tuple with (stdout, stderr) if the exitcode is zero,
        otherwise Exception is raised.

        """
        # make args a list if it's not already so
        if isinstance(command, basestring):
            args = shlex.split(command)
        elif isinstance(command, list):
            args = command
        else:
            raise TypeError('_run_command: command arg must be str or list')

        # add SSH arguments if this is a remote command
        if host != 'localhost':
            ssh_args = shlex.split('%s %s@%s' % (settings.ssh_path, self.remote_user, host))
            args = ssh_args + args

        try:
            self.logger.debug('_run_command %r' % args)
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # We really want to block until our subprocess exists or
            # KeyboardInterrupt. If we don't, clean-up tasks will likely fail.
            try:
                stdout, stderr = p.communicate()
            except KeyboardInterrupt:
                # Let's try to stop our subprocess if the user issues a
                # KeyboardInterrupt.
                # TODO terminate() doesn't block, so we'll need to poll
                p.terminate()
                # We should re-raise this exception so our caller knows the
                # user wants to stop the workflow.
                raise

            if stdout:
                self.logger.debug(stdout)
            if stderr:
                # Warning level should be fine here since we'll also look at
                # the exitcode.
                self.logger.warning(stderr)
            exitcode = p.returncode
        except IOError:
            raise Exception('Unable to execute/find {args}'.format(args=args))

        if exitcode > 0:
            error_message = ('[{host}] A command terminated with errors and likely requires intervention. The '
                'command attempted was "{command}".').format(
                    host=host, command=command)
            raise Exception(error_message)

        return (stdout, stderr)

    def _run_command_with_retries(self, command, host='localhost', try_number=0):
        """Calls _run_command up to MAX_RETRIES times, with RETRY_TIMEOUT seconds between tries."""
        try:
            self._run_command(command, host)
        except Exception, e:
            if try_number > settings.max_retries:
                raise e
            self._run_command_with_retries(command, host, try_number + 1)

    def run_backup(self):
        """Excutes the complete workflow for a single backup job.

        The backup workflow consists of running pre-job hooks in order,
        calling the _run_backup() method to perform the actual data backup,
        and then running the post-job hooks, also in order. 

        Under healthy operation, the error_case argument passed to all
        post-job functions will be set to False. If Exception or
        KeyboardInterrupt is raised during either the pre-job hook processing or
        during _run_backup(), then the error_case argument will be set to True.

        """
        self.logger.info('started')
        try:
            error_case = False
            self._process_pre_job_hooks()
            self.logger.info('data backup started...')
            self._run_backup()
            self.logger.info('data backup complete')
        except KeyboardInterrupt:
            error_case = True
            # using error level here so that these messages will
            # print to the console
            self.logger.error('backup job cancelled by user')
            self.logger.error("let's try to clean up...")
        except Exception, e:
            error_case = True
            self.logger.error(str(e))
            self.logger.error("let's try to clean up...")
        finally:
            self._process_post_job_hooks(error_case)
            self.logger.info('stopped')

    def _run_backup(self, top_level_src_dir='/'):
        """Run rdiff-backup job.

        kwargs:
        top_level_src_dir -- a path on the source host that acts as a mask
            for writing paths to the backup destination

        Builds an argument list for a full rdiff-backup command line based on
        the settings in the instance and optionally the top_level_src_dir
        argument. Said argument is used to define the context for the backup
        mirror. This is especially handy when backing up mounted spanshots so
        that the mirror doesn't also include the directory in which the
        snapshot is mounted.

        For example, if our source data is /tmp/database-server1_snapshot and
        our destination directory is /backup-store/database-server1, then
        setting the top_level_src_dir to '/' would build your backup mirror at
        /backup-store/database-server1/tmp/database-server1_snapshot. If you
        instead set the top_level_src_dir to '/tmp/database-server1_snapshot'
        then your backup mirror would be built at
        /backup-store/database-server1, which is probably what you want.

        """ 
        self.logger.debug('_run_backup started')

        if settings.backup_store_path is None:
            raise Exception('backup_store_path setting is not set')
        if not os.access(settings.rdiff_backup_path, os.X_OK):
            raise Exception('rdiff-backup does not appear to be installed or is not executable')

        # Init our arguments list with the path to rdiff-backup.
        # This will be in the format we'd normally pass to the command-line
        # e.g. [ '--include', '/dir/to/include', '--exclude', '/dir/to/exclude']
        arg_list = [settings.rdiff_backup_path]

        # setup some default rdiff-backup options
        # TODO provide a way to override these
        arg_list.append('--exclude-device-files')
        arg_list.append('--exclude-fifos')
        arg_list.append('--exclude-sockets')

        # Bring the terminal verbosity down so that we only see errors
        arg_list += ['--terminal-verbosity', '1']

        # This conditional reads strangely, but that's because rdiff-backup
        # not only defaults to having SSH compression enabled, it also doesn't
        # have an option to explicitly enable it -- only one to disable it.
        if not settings.ssh_compression:
            arg_list.append('--ssh-no-compression')

        # Add exclude and includes to our arguments
        for exclude_dir in self.exclude_dir_list:
            arg_list.append('--exclude')
            arg_list.append(exclude_dir)

        for exclude_file in self.exclude_file_list:
            arg_list.append('--exclude-filelist')
            arg_list.append(exclude_file)

        for include_dir in self.include_dir_list:
            arg_list.append('--include')
            arg_list.append(include_dir)

        for include_file in self.include_file_list:
            arg_list.append('--include-filelist')
            arg_list.append(include_file)

        # Exclude everything else
        arg_list += ['--exclude', '**']

        # Add a source argument
        if self.source_hostname == 'localhost':
            arg_list.append(top_level_src_dir)
        else:
            arg_list.append(
                '{remote_user}@{source_hostname}::{top_level_src_dir}'.format(
                    remote_user=self.remote_user,
                    source_hostname=self.source_hostname,
                    top_level_src_dir=top_level_src_dir
                )
            )

        # Add a destination argument
        arg_list.append(
            '{backup_store_path}/{label}'.format(
                backup_store_path=settings.backup_store_path,
                label=self.label
            )
        )

        # Rdiff-backup GO!
        self._run_command(arg_list)
        self.logger.debug('_run_backup completed')

    def _remove_older_than(self, timespec, error_case):
        """Trims increments older than timespec.

        args:
        timespec -- a string representing the maximum age of
            a backup datapoint (uses the same format as the --remove-older-than
            argument for rdiff-backup [e.g. 30D, 10W, 6M])
        error_case -- bool indicating if we're being called after a failure

        Post-job hook that uses rdiff-backup's --remove-older-than feature to
        trim old increments from the backup history. This method does nothing
        when error_case is True.

        """ 
        if not error_case:
            self.logger.info('remove_older_than %s started' % timespec)

            arg_list = [
                settings.rdiff_backup_path,
                '--force',
                '--remove-older-than',
                timespec,
                '%s/%s' % (settings.backup_store_path, self.label),
            ]

            self._run_command(arg_list)
            self.logger.info('remove_older_than %s completed' % timespec)


class LVMBackup(ARIBackup):
    """Subclass to add LVM snapshot management.

    This class registers pre-job and post-job hooks to create and mount LVM
    snapshots before and after a backup job. It also overrides the
    _run_backup() method to fix the include and exclude dirs to use the
    snapshot mountpoint paths.

    This class requires adding snapshot_mount_root and snapshot_suffix to the
    settings module. See include/etc/ari-backup/ari-backup.conf.yaml for more
    on these settings.

    """
    def __init__(self, label, source_hostname, remove_older_than_timespec=None):
        """Configure an LVMBackup object.

        args:
        label -- a str to label the backup job 
        source_hostname -- the name of the host with the source data to backup

        kwargs:
        remove_older_than_timespec -- a string representing the maximum age of
            a backup datapoint (uses the same format as the --remove-older-than
            argument for rdiff-backup)

        """
        super(LVMBackup, self).__init__(label, source_hostname, remove_older_than_timespec)

        # This is a list of 2-tuples, where each inner 2-tuple expresses the LV
        # to back up, the mount point for that LV any mount options necessary.
        # For example: [('hostname/root, '/', 'noatime'),]
        # TODO I wonder if noatime being used all the time makes sense to
        # improve read performance and reduce writes to the snapshots.
        self.lv_list = []

        # a list of dicts with the snapshot paths and where they should be
        # mounted
        self.lv_snapshots = []
        # mount the snapshots in a directory named for this job's label
        self.snapshot_mount_point_base_path = os.path.join(settings.snapshot_mount_root, self.label)

        # setup pre and post job hooks to manage snapshot work flow
        self.pre_job_hook_list.append((self._create_snapshots, {}))
        self.pre_job_hook_list.append((self._mount_snapshots, {}))
        self.post_job_hook_list.append((self._umount_snapshots, {}))
        self.post_job_hook_list.append((self._delete_snapshots, {}))

    def _create_snapshots(self):
        """Creates snapshots of all the volumns listed in self.lv_list."""
        self.logger.info('creating LVM snapshots...')
        for volume in self.lv_list:
            try:
                lv_path, src_mount_path, mount_options = volume
            except ValueError:
                lv_path, src_mount_path = volume
                mount_options = None

            vg_name, lv_name = lv_path.split('/')
            new_lv_name = lv_name + settings.snapshot_suffix
            mount_path = '{snapshot_mount_point_base_path}{src_mount_path}'.format(
                snapshot_mount_point_base_path=self.snapshot_mount_point_base_path,
                src_mount_path=src_mount_path
            )

            # TODO Is it really OK to always make a 1GB exception table?
            self._run_command('lvcreate -s -L 1G %s -n %s' % (lv_path, new_lv_name), self.source_hostname)

            self.lv_snapshots.append({
                'lv_path': vg_name + '/' + new_lv_name,
                'mount_path': mount_path,
                'mount_options': mount_options,
                'created': True,
                'mount_point_created': False,
                'mounted': False,
            })

    def _delete_snapshots(self, error_case=None):
        """Deletes snapshots in self.lv_snapshots.

        kwargs:
        error_case -- bool indicating if we're being called after a failure

        This method behaves the same in the normal and error cases.

        """ 
        self.logger.info('deleting LVM snapshots...')
        for snapshot in self.lv_snapshots:
            if snapshot['created']:
                lv_path = snapshot['lv_path']
                # -f makes lvremove not interactive
                self._run_command_with_retries('lvremove -f %s' % lv_path, self.source_hostname)
                snapshot['created'] = False

    def _mount_snapshots(self):
        """Creates mountpoints as well as mounts the snapshots.

        If the mountpoint directory already has a file system mounted then we
        raise Exception. Metadata is updated whenever a snapshot is
        successfully mounted so that _umount_snapshots() knows which
        snapshots to try to umount.

        TODO add mount_options to documentation for backup config files

        """
        self.logger.info('mounting LVM snapshots...')
        for snapshot in self.lv_snapshots:
            lv_path = snapshot['lv_path']
            device_path = '/dev/' + lv_path
            mount_path = snapshot['mount_path']
            mount_options = snapshot['mount_options']

            # mkdir the mount point
            self._run_command('mkdir -p %s' % mount_path, self.source_hostname)
            snapshot['mount_point_created'] = True

            # If where we want to mount our LV is already a mount point then
            # let's back out.
            if os.path.ismount(mount_path):
                raise Exception("{mount_path} is already a mount point".format(mount_path=mount_path))

            # mount the LV, possibly with mount options
            if mount_options:
                command = 'mount -o {mount_options} {device_path} {mount_path}'.format(
                    mount_options=mount_options,
                    device_path=device_path,
                    mount_path=mount_path
                )
            else:
                command = 'mount {device_path} {mount_path}'.format(
                    device_path=device_path,
                    mount_path=mount_path
                )

            self._run_command(command, self.source_hostname)
            snapshot['mounted'] = True

    def _umount_snapshots(self, error_case=None):
        """Umounts mounted snapshots in self.lv_snapshots.

        kwargs:
        error_case -- bool indicating if we're being called after a failure

        This method behaves the same in the normal and error cases.

        """ 
        # TODO If the user doesn't put '/' in their include_dir_list, then
        # we'll end up with directories around where the snapshots are mounted
        # that will not get cleaned up.  We should probably add functionality
        # to make sure the "label" directory is recursively removed.
        # Check out shutil.rmtree() to help resolve this issue.

        self.logger.info('umounting LVM snapshots...')
        # We need a local copy of the lv_snapshots list to muck with in
        # this method.
        local_lv_snapshots = self.lv_snapshots
        # We want to umount these LVs in reverse order as this should ensure
        # that we umount the deepest paths first.
        local_lv_snapshots.reverse()
        for snapshot in local_lv_snapshots:
            mount_path = snapshot['mount_path']
            if snapshot['mounted']:
                self._run_command_with_retries('umount %s' % mount_path, self.source_hostname)
                snapshot['mounted'] = False
            if snapshot['mount_point_created']:
                self._run_command_with_retries('rmdir %s' % mount_path, self.source_hostname)
                snapshot['mount_point_created'] = False

    def _run_backup(self):
        """Run backup of LVM snapshots.
            
        This method overrides the base class's _run_backup() so that we can
        modify the include_dir_list and exclude_dir_list to have the
        snapshot_mount_point_base_path prefixed to their paths. This allows the
        user to configure what to backup from the perspective of the file
        system on the snapshot itself.

        """

        self.logger.debug('LVMBackup._run_backup started')

        # Cook the self.include_dir_list and self.exclude_dir_list so that the
        # src paths include the mount path for the LV(s).
        local_include_dir_list = []
        for include_dir in self.include_dir_list:
            local_include_dir_list.append('{snapshot_mount_point_base_path}{include_dir}'.format(
                snapshot_mount_point_base_path=self.snapshot_mount_point_base_path,
                include_dir=include_dir
            ))

        local_exclude_dir_list = []
        for exclude_dir in self.exclude_dir_list:
            local_exclude_dir_list.append('{snapshot_mount_point_base_path}{exclude_dir}'.format(
                snapshot_mount_point_base_path=self.snapshot_mount_point_base_path,
                exclude_dir=exclude_dir
            ))

        self.include_dir_list = local_include_dir_list
        self.exclude_dir_list = local_exclude_dir_list

        # We don't support include_file_list and exclude_file_list in this
        # class as it would take extra effort and it's not likely to be used.

        # Have the base class perform an rdiff-backup
        super(LVMBackup, self)._run_backup(self.snapshot_mount_point_base_path)

        self.logger.debug('LVMBackup._run_backup completed')

class CustomTopLevelSrcDir(ARIBackup):
    """Subclass for special backup scenarios.

    This class will allow you to set a custom top_level_src_dir
    attribute per backup object.  This is useful when backing up various sources
    with mountpoints that you'd prefer not show up at the rdiff-backup destination.

    """
    def __init__(self, top_level_src_dir, *args, **kwargs):
        super(CustomTopLevelSrcDir, self).__init__(*args, **kwargs)
        self.top_level_src_dir = top_level_src_dir

    def _run_backup(self):
        """Run backup for special cases.

        Similar to LVMBackup._run_backup, but instead allows the user to
        customize the mountpoint path that will be excluded at the mirror.
        """
        self.logger.debug('CustomTopLevelSrcDir._run_backup started')
        super(CustomTopLevelSrcDir, self)._run_backup(self.top_level_src_dir)
