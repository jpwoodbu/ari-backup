"""rdiff-backup based backup workflows."""
import os

import gflags

import workflow


FLAGS = gflags.FLAGS
gflags.DEFINE_string('backup_store_path', None,
                     'base path to which to write backups')
gflags.DEFINE_string('rdiff_backup_path', '/usr/bin/rdiff-backup',
                     'path to rdiff-backup binary')
gflags.DEFINE_boolean('ssh_compression', False,
                      'compress rdiff-backup SSH streams')
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
gflags.DEFINE_string('top_level_src_dir', '/',
    'top level source directory from which to begin the backup mirror')


class RdiffBackup(workflow.BaseWorkflow):
  """Workflow to backup machines using rdiff-backup."""

  def __init__(self, label, source_hostname,
               remove_older_than_timespec=None):
    """Configure an RdiffBackup object.

    args:
    label -- a str to label the backup job 
    source_hostname -- the name of the host with the source data to backup

    kwargs:
    remove_older_than_timespec -- a string representing the maximum age of
        a backup recovery point (uses the same format as the
        --remove-older-than argument for rdiff-backup)

    """
    super(RdiffBackup, self).__init__(label)
    self.source_hostname = source_hostname

    # Assign flags to instance vars so they might be easily overridden in
    # workflow configs.
    self.backup_store_path = FLAGS.backup_store_path
    self.rdiff_backup_path = FLAGS.rdiff_backup_path
    self.ssh_compression = FLAGS.ssh_compression
    self.top_level_src_dir = FLAGS.top_level_src_dir

    # Include nothing by default.
    self.include_dir_list = []
    self.include_file_list = []
    # Exclude nothing by default.
    # We'll put the '**' exclude on the end of the arg_list later.
    self.exclude_dir_list = []
    self.exclude_file_list = []

    if remove_older_than_timespec is not None:
      self.post_job_hook_list.append((
          self._remove_older_than,
          {'timespec': remove_older_than_timespec}))

  def _run_custom_workflow(self):
    """Run rdiff-backup job.

    Builds an argument list for a full rdiff-backup command line based on the
    configuration in the RdiffBackup instance.

    """ 
    self.logger.debug('_run_custom_workflow started')

    # TODO(jpwoodbu) Move this sanity check into a pre-hook so we can avoid
    # doing other pre-hook work if we're missing a critical setting. Also of
    # note, it's too bad we can't use the gflags.MarkFlagAsRequired() function
    # for this. But since we're not actually passing in flags using sys.argv
    # most of the time, our hands are a bit tied.
    if self.backup_store_path is None:
      raise Exception('backup_store_path setting is not set')
    if not os.access(self.rdiff_backup_path, os.X_OK):
      raise Exception('rdiff-backup does not appear to be installed or '
                      'is not executable')

    # Init our arguments list with the path to rdiff-backup.
    # This will be in the format we'd normally pass to the command-line
    # e.g. [ '--include', '/dir/to/include', '--exclude',
    # '/dir/to/exclude']
    arg_list = [self.rdiff_backup_path]

    # setup some default rdiff-backup options
    # TODO provide a way to override these
    arg_list.append('--exclude-device-files')
    arg_list.append('--exclude-fifos')
    arg_list.append('--exclude-sockets')

    # Bring the terminal verbosity down so that we only see errors
    arg_list += ['--terminal-verbosity', '1']

    # This conditional reads strangely, but that's because rdiff-backup not
    # only defaults to having SSH compression enabled, it also doesn't have an
    # option to explicitly enable it -- only one to disable it.
    if not self.ssh_compression:
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
      arg_list.append(self.top_level_src_dir)
    else:
      arg_list.append(
          '{remote_user}@{source_hostname}::{top_level_src_dir}'.format(
              remote_user=self.remote_user,
              source_hostname=self.source_hostname,
              top_level_src_dir=self.top_level_src_dir))

    # Add a destination argument
    arg_list.append(
        '{backup_store_path}/{label}'.format(
            backup_store_path=self.backup_store_path, label=self.label))

    # Rdiff-backup GO!
    self.run_command(arg_list)
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
          self.rdiff_backup_path,
          '--force',
          '--remove-older-than',
          timespec,
          '{}/{}'.format(self.backup_store_path, self.label),
      ]

      self.run_command(arg_list)
      self.logger.info('remove_older_than %s completed' % timespec)
