"""rdiff-backup based backup workflows."""
import os
import shlex

from absl import flags

import workflow


FLAGS = flags.FLAGS
flags.DEFINE_string('backup_store_path', None,
                    'base path to which to write backups')
flags.DEFINE_string('rdiff_backup_path', '/usr/bin/rdiff-backup',
                    'path to rdiff-backup binary')
flags.DEFINE_boolean('ssh_compression', False,
                     'compress rdiff-backup SSH streams')
# terminal-verbosity=1 brings the terminal verbosity down so that we only see
# errors.
flags.DEFINE_string('rdiff_backup_options',
                    ('--exclude-device-files --exclude-fifos '
                     '--exclude-sockets --terminal-verbosity 1'),
                    'default rdiff-backup options')
flags.DEFINE_string(
    'remove_older_than_timespec', None,
    ('Global timespec for timming rdiff-backup recovery points. Default is '
     'None, which means no previous recovery points will be trimmed. '
     'This setting can be overriden per backup config.'))

# The top_level_src_dir flag is used to define the context for the backup
# mirror. This is especially handy when backing up mounted spanshots so that
# the mirror doesn't also include the directory in which the snapshot is
# mounted.
#
# For example, if our source data is /tmp/database-server1_snapshot and our
# destination directory is /backup-store/database-server1, then setting the
# top_level_src_dir to '/' would build your backup mirror at
# /backup-store/database-server1/tmp/database-server1_snapshot. If you instead
# set the top_level_src_dir to '/tmp/database-server1_snapshot' then your
# backup mirror would be built at /backup-store/database-server1, which is
# probably what you want.
flags.DEFINE_string(
    'top_level_src_dir', '/',
    'top level source directory from which to begin the backup mirror')


class RdiffBackup(workflow.BaseWorkflow):
    """Workflow to backup machines using rdiff-backup."""

    def __init__(self, label, source_hostname,
                 remove_older_than_timespec=None,
                 check_for_required_binaries=True, **kwargs):
        """Configure an RdiffBackup object.

        Args:
            label: str, label for the backup job.
            source_hostname: str, the name of the host with the source data to
                backup.
            remove_older_than_timespec: str or None, the maximum age of a
                backup recovery point (uses the same format as the
                --remove-older-than argument for rdiff-backup). Defaults to
                None which will use the value of the remove_older_than_timespec
                flag.
        """
        super(RdiffBackup, self).__init__(label, **kwargs)
        self.source_hostname = source_hostname

        # Assign flags to instance vars so they might be easily overridden in
        # workflow configs.
        self.backup_store_path = FLAGS.backup_store_path
        self.rdiff_backup_path = FLAGS.rdiff_backup_path
        self.ssh_compression = FLAGS.ssh_compression
        self.top_level_src_dir = FLAGS.top_level_src_dir
        if remove_older_than_timespec is None:
            self.remove_older_than_timespec = FLAGS.remove_older_than_timespec
        else:
            self.remove_older_than_timespec = remove_older_than_timespec
        self._check_for_required_binaries = check_for_required_binaries

        # Initialize include and exclude lists.
        self._includes = list()
        self._excludes = list()

        self._check_required_flags()
        self._check_required_binaries()

        if self.remove_older_than_timespec is not None:
            # Using a lambda for late evaluation in case the user overrides the
            # value of self.remove_older_than_timespec before calling run().
            def return_timespec():
                return {'timespec': self.remove_older_than_timespec}

            self.add_post_hook(self._remove_older_than, return_timespec)

    # Provide backward compatibility for config files using attributes
    # directly.
    @property
    def include_dir_list(self):
        self.logger.warning(
            'include_dir_list is deprecated. Please use include() instead.')
        return self._includes

    @include_dir_list.setter
    def include_dir_list(self, value):
        self.logger.warning(
            'include_dir_list is deprecated. Please use include() instead.')
        self._includes = value

    @property
    def exclude_dir_list(self):
        self.logger.warning(
            'exclude_dir_list is deprecated. Please use exclude() instead.')
        return self._excludes

    @exclude_dir_list.setter
    def exclude_dir_list(self, value):
        self.logger.warning(
            'exclude_dir_list is deprecated. Please use exclude() instead.')
        self._excludes = value

    def include_dir(self, path):
        self.logger.warning(
            'include_dir() is deprecated. Please use include() instead.')
        self.include(path)

    def exclude_dir(self, path):
        self.logger.warning(
            'exclude_dir() is deprecated. Please use exclude() instead.')
        self.exclude(path)

    def _check_required_flags(self):
        if self.backup_store_path is None:
            raise Exception('backup_store_path setting is not set.')

    def _check_required_binaries(self):
        if self._check_for_required_binaries and not os.access(
          self.rdiff_backup_path, os.X_OK):
            raise Exception('rdiff-backup does not appear to be installed or '
                            'is not executable.')

    def include(self, path):
        """Add a path to be included in the backup.

        Args:
            path: str, path to include in the backup.
        """
        self._includes.append(path)

    def exclude(self, path):
        """Add a path to be excluded from the backup.

        Args:
            path: str, path to exclude from the backup.
        """
        self._excludes.append(path)

    def _run_custom_workflow(self):
        """Run rdiff-backup job.

        Builds an argument list for a full rdiff-backup command line based on
        the configuration in the RdiffBackup instance.
        """
        self.logger.debug('_run_custom_workflow started.')
        # Init our arguments list with the path to rdiff-backup.
        # This will be in the format we'd normally pass to the command-line
        # e.g. [ '--include', '/dir/to/include', '--exclude',
        # '/dir/to/exclude']
        args = [self.rdiff_backup_path]

        # Add default options to arguments.
        default_options = shlex.split(FLAGS.rdiff_backup_options)
        args.extend(default_options)

        # This conditional reads strangely, but that's because rdiff-backup not
        # only defaults to having SSH compression enabled, it also doesn't have
        # an option to explicitly enable it -- only the option to disable it.
        if not self.source_hostname == 'localhost' and not \
                self.ssh_compression:
            args.append('--ssh-no-compression')

        # Add exclude and includes to our arguments...
        for path in self._excludes:
            args.append('--exclude')
            args.append(path)

        for path in self._includes:
            args.append('--include')
            args.append(path)

        # Exclude everything else
        args += ['--exclude', '**']

        # Add a source argument
        if self.source_hostname == 'localhost':
            args.append(self.top_level_src_dir)
        else:
            args.append(
                '{remote_user}@{source_hostname}::{top_level_src_dir}'.format(
                    remote_user=self.remote_user,
                    source_hostname=self.source_hostname,
                    top_level_src_dir=self.top_level_src_dir))

        # Add a destination argument
        args.append('{backup_store_path}/{label}'.format(
            backup_store_path=self.backup_store_path, label=self.label))

        # Rdiff-backup GO!
        self.run_command(args)
        self.logger.debug('_run_backup completed.')

    def _remove_older_than(self, timespec, error_case):
        """Trims increments older than timespec.

        Post-job hook that uses rdiff-backup's --remove-older-than feature to
        trim old increments from the backup history. This method does nothing
        when error_case is True.

        Args:
            timespec: str, the maximum age of a backup datapoint (uses the same
                format as the --remove-older-than argument for rdiff-backup
                [e.g. 30D, 10W, 6M]).
            error_case: bool, whether an error has occurred during the backup.
        """
        if not error_case:
            self.logger.info('remove_older_than %s started.' % timespec)

            args = [
                self.rdiff_backup_path,
                '--force',
                '--remove-older-than',
                timespec,
                '{}/{}'.format(self.backup_store_path, self.label),
            ]

            self.run_command(args)
            self.logger.info('remove_older_than %s completed.' % timespec)
