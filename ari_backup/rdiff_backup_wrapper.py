"""rdiff-backup based backup workflows."""
import os
import shlex

import gflags

import workflow


FLAGS = gflags.FLAGS
gflags.DEFINE_string('backup_store_path', None,
                     'base path to which to write backups')
gflags.DEFINE_string('rdiff_backup_path', '/usr/bin/rdiff-backup',
                     'path to rdiff-backup binary')
gflags.DEFINE_boolean('ssh_compression', False,
                      'compress rdiff-backup SSH streams')
# terminal-verbosity=1 brings the terminal verbosity down so that we only see
# errors.
gflags.DEFINE_string('rdiff_backup_options',
                     ('--exclude-device-files --exclude-fifos '
                      '--exclude-sockets --terminal-verbosity 1'),
                     'default rdiff-backup options')
gflags.DEFINE_string(
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
gflags.DEFINE_string('top_level_src_dir', '/',
    'top level source directory from which to begin the backup mirror')


class RdiffBackup(workflow.BaseWorkflow):
  """Workflow to backup machines using rdiff-backup."""

  def __init__(self, label, source_hostname,
               remove_older_than_timespec=None, **kwargs):
    """Configure an RdiffBackup object.

    Args:
      label: str, label for the backup job.
      source_hostname: str, the name of the host with the source data to
        backup.
      remove_older_than_timespec: str or None, the maximum age of a backup
        recovery point (uses the same format as the
        --remove-older-than argument for rdiff-backup). Defaults to None which
        will use the value of the remove_older_than_timespec flag.
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

    # Initialize include and exclude lists.
    self._include_dirs = list()
    self._include_files = list()
    self._exclude_dirs = list()
    self._exclude_files = list()

    self._check_required_flags()
    self._check_required_binaries()

    if self.remove_older_than_timespec is not None:
      self.post_job_hook_list.append((
          self._remove_older_than,
          {'timespec': self.remove_older_than_timespec}))

  # Provide backward compatibility for config files using attributes directly.
  @property
  def include_dir_list(self):
    self.logger.warning(
        'include_dir_list is deprecated. Please use include_dir() instead.')
    return self._include_dirs

  @include_dir_list.setter
  def include_dir_list(self, value):
    self.logger.warning(
        'include_dir_list is deprecated. Please use include_dir() instead.')
    self._include_dirs = value

  @property
  def include_file_list(self):
    self.logger.warning(
        'include_file_list is deprecated. Please use include_file() instead.')
    return self._include_files

  @include_file_list.setter
  def include_file_list(self, value):
    self.logger.warning(
        'include_file_list is deprecated. Please use include_file() instead.')
    self._include_files = value

  @property
  def exclude_dir_list(self):
    self.logger.warning(
        'exclude_dir_list is deprecated. Please use exclude_dir() instead.')
    return self._exclude_dirs

  @exclude_dir_list.setter
  def exclude_dir_list(self, value):
    self.logger.warning(
        'exclude_dir_list is deprecated. Please use exclude_dir() instead.')
    self._exclude_dirs = value

  @property
  def exclude_file_list(self):
    self.logger.warning(
        'exclude_file_list is deprecated. Please use exclude_file() instead.')
    return self._exclude_files

  @exclude_file_list.setter
  def exclude_file_list(self, value):
    self.logger.warning(
        'exclude_file_list is deprecated. Please use exclude_file() instead.')
    self._exclude_files = value

  def _check_required_flags(self):
    if self.backup_store_path is None:
      raise Exception('backup_store_path setting is not set')

  def _check_required_binaries(self):
    if not os.access(self.rdiff_backup_path, os.X_OK):
      raise Exception('rdiff-backup does not appear to be installed or '
                      'is not executable')

  def include_dir(self, path):
    """Add a directory to be included in the backup.

    The provided path is added to the top_level_src_dir when considering
    whether files should be included in the backup.

    Args:
      path: str, directory path to include in the backup.
    """
    self._include_dirs.append(path)

  def include_file(self, path):
    """Add a file to be included in the backup.

    The provided path is added to the top_level_src_dir when considering
    whether files should be included in the backup.

    Args:
      path: str, file path to include in the backup.
    """
    self._include_files.append(path)

  def exclude_dir(self, path):
    """Add a directory to be excluded in the backup.

    The provided path is added to the top_level_src_dir when considering
    whether files should be included in the backup.

    Args:
      path: str, directory path to exclude from the backup.
    """
    self._exclude_dirs.append(path)

  def exclude_file(self, path):
    """Add a file to be excluded in the backup.

    The provided path is added to the top_level_src_dir when considering
    whether files should be included in the backup.

    Args:
      path: str, file path to exclude from the backup.
    """
    self._exclude_files.append(path)

  def _run_custom_workflow(self):
    """Run rdiff-backup job.

    Builds an argument list for a full rdiff-backup command line based on the
    configuration in the RdiffBackup instance.
    """ 
    self.logger.debug('_run_custom_workflow started')
    # Init our arguments list with the path to rdiff-backup.
    # This will be in the format we'd normally pass to the command-line
    # e.g. [ '--include', '/dir/to/include', '--exclude',
    # '/dir/to/exclude']
    args = [self.rdiff_backup_path]

    # Add default options to arguments.
    default_options = shlex.split(FLAGS.rdiff_backup_options)
    args.extend(default_options)

    # This conditional reads strangely, but that's because rdiff-backup not
    # only defaults to having SSH compression enabled, it also doesn't have an
    # option to explicitly enable it -- only the option to disable it.
    if not self.source_hostname == 'localhost' and not self.ssh_compression:
      args.append('--ssh-no-compression')

    # Add exclude and includes to our arguments
    for exclude_dir in self._exclude_dirs:
      args.append('--exclude')
      args.append(exclude_dir)

    for exclude_file in self._exclude_files:
      args.append('--exclude-filelist')
      args.append(exclude_file)

    for include_dir in self._include_dirs:
      args.append('--include')
      args.append(include_dir)

    for include_file in self._include_files:
      args.append('--include-filelist')
      args.append(include_file)

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
    self.logger.debug('_run_backup completed')

  def _remove_older_than(self, timespec, error_case):
    """Trims increments older than timespec.

    Post-job hook that uses rdiff-backup's --remove-older-than feature to
    trim old increments from the backup history. This method does nothing
    when error_case is True.

    Args:
      timespec: str, the maximum age of a backup datapoint (uses the same
        format as the --remove-older-than argument for rdiff-backup [e.g. 30D,
        10W, 6M]).
      error_case: bool, whether an error has occurred during the backup.
    """ 
    if not error_case:
      self.logger.info('remove_older_than %s started' % timespec)

      args = [
          self.rdiff_backup_path,
          '--force',
          '--remove-older-than',
          timespec,
          '{}/{}'.format(self.backup_store_path, self.label),
      ]

      self.run_command(args)
      self.logger.info('remove_older_than %s completed' % timespec)
