import os
import unittest

import gflags
import mock

import rdiff_backup_wrapper
import test_lib


FLAGS = gflags.FLAGS
# Disable logging to stderr when running tests.
FLAGS.stderr_logging = False


class RdiffBackupTest(test_lib.FlagSaverMixIn, unittest.TestCase):
  
  def setUp(self):
    super(RdiffBackupTest, self).setUp()
    FLAGS.backup_store_path = '/unused'
    FLAGS.rdiff_backup_options = str()
    self.mock_check_required_binaries = mock.patch.object(
        rdiff_backup_wrapper.RdiffBackup, '_check_required_binaries').start()

  def tearDown(self):
    super(RdiffBackupTest, self).tearDown()
    self.mock_check_required_binaries.stop()

  @mock.patch.object(rdiff_backup_wrapper.RdiffBackup, '_remove_older_than')
  def testRemoveOlderThan_timespecIsNone_backupsNotTrimmed(
      self, mock_remove_older_than):
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        remove_older_than_timespec=None, label='unused',
        source_hostname='unused', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/unused')
    backup.run()

    self.assertFalse(mock_remove_older_than.called)

  def testRemoveOlderThan_timespecIsNotNone_backupsTrimmed(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        remove_older_than_timespec='60D', label='fake_backup',
        source_hostname='unused', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/unused')
    backup.run()

    mock_command_runner.run.assert_called_with(
        ['/fake/rdiff-backup', '--force', '--remove-older-than', '60D',
         '/fake/backup-store/fake_backup'])

  def testCheckRequiredFlags_backupStorePathNotSet_raisesException(self):
    FLAGS.backup_store_path = None
    with self.assertRaises(Exception):
      backup = rdiff_backup_wrapper.RdiffBackup(
          label='unused', source_hostname='unused', settings_path=None)
      
  def testIncludeDir_pathAddedToIncludeDirTracker(self):
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='unused', source_hostname='unused', settings_path=None)

    backup.include_dir('/etc')
    backup.include_dir('/var')

    self.assertEqual(backup._include_dirs, ['/etc', '/var'])

  def testIncludeDir_backupIncludesDirs(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/etc')
    backup.include_dir('/var')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--include', '/etc', '--include', '/var', '--exclude', '**', '/',
        '/fake/backup-store/fake_backup'])

  def testExcludeDir_backupExcludesDirs(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/var')
    backup.exclude_dir('/var/cache')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--exclude', '/var/cache', '--include', '/var', '--exclude', '**', '/',
        '/fake/backup-store/fake_backup'])

  def testIncludeFile_backupIncludesFiles(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_file('/really_important_file1')
    backup.include_file('/really_important_file2')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--include-filelist', '/really_important_file1', '--include-filelist',
        '/really_important_file2', '--exclude', '**', '/',
        '/fake/backup-store/fake_backup'])

  def testExcludeFile_backupExcludesFiles(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/etc')
    backup.exclude_file('/etc/huge_useless_file')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--exclude-filelist', '/etc/huge_useless_file', '--include', '/etc',
        '--exclude', '**', '/', '/fake/backup-store/fake_backup'])

  def testRemoveOlderThan_errorCaseIsTrue_doesNotTrimBackups(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='unused', source_hostname='unused', settings_path=None,
        command_runner=mock_command_runner)

    backup._remove_older_than('60D', error_case=True)

    self.assertFalse(mock_command_runner.run.called)

  def testRemoveOlderThan_errorCaseIsFalse_trimsBackups(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='unused', settings_path=None,
        command_runner=mock_command_runner)

    backup._remove_older_than('60D', error_case=False)

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--force', '--remove-older-than', '60D',
        '/fake/backup-store/fake_backup'])

  def testRunCustomWorkflow_sshCompressionFlagIsFalse_sshCompressionDisabled(
      self):
    FLAGS.ssh_compression = False
    FLAGS.remote_user = 'fake_user'
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='fake_host', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--ssh-no-compression', '--include', '/fake_dir', '--exclude', '**',
        'fake_user@fake_host::/', '/fake/backup-store/fake_backup'])

  def testRunCustomWorkflow_sshCompressionFlagIsTrue_sshCompressionNotDisabled(
      self):
    FLAGS.ssh_compression = True
    FLAGS.remote_user = 'fake_user'
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='fake_host', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--include', '/fake_dir', '--exclude', '**', 'fake_user@fake_host::/',
        '/fake/backup-store/fake_backup'])

  def testRunCustomWorkflow_sourceHostnameIsLocalhost_sourceIsPath(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--include', '/fake_dir', '--exclude', '**', '/', 
        '/fake/backup-store/fake_backup'])

  def testRunCustomWorkflow_sourceHostnameIsNotLocalhost_sourceIsHost(self):
    FLAGS.ssh_compression = True
    FLAGS.remote_user = 'fake_user'
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='fake_host', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--include', '/fake_dir', '--exclude', '**', 'fake_user@fake_host::/',
        '/fake/backup-store/fake_backup'])

  def testRunCustomWorkflow_rdiffBackupOptionsGiven_addsOptionsToCommand(self):
    FLAGS.rdiff_backup_options = '--fake-extra-option1 --fake-extra-option2'
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include_dir('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(['/fake/rdiff-backup',
        '--fake-extra-option1', '--fake-extra-option2', '--include',
        '/fake_dir', '--exclude', '**', '/', '/fake/backup-store/fake_backup'])


class RdiffBackupCheckRequiredBinariesTest(
    test_lib.FlagSaverMixIn, unittest.TestCase):
  """Class for testing methods that were mocked out in RdiffBackupTest."""

  @mock.patch.object(os, 'access')
  def testCheckRequiredBinaries_rdiffBackupNotInstalled_raisesException(
      self, mock_os_access):
    FLAGS.backup_store_path = '/unused'
    mock_os_access.return_value = False

    with self.assertRaises(Exception):
      backup = rdiff_backup_wrapper.RdiffBackup(
          label='unused', source_hostname='unused', settings_path=None)


if __name__ == '__main__':
  unittest.main()
