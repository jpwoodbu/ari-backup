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
    patcher = mock.patch.object(
        rdiff_backup_wrapper.RdiffBackup, '_check_required_binaries')
    self.addCleanup(patcher.stop)
    patcher.start()

  @mock.patch.object(rdiff_backup_wrapper.RdiffBackup, '_remove_older_than')
  def testRemoveOlderThan_timespecIsNone_backupsNotTrimmed(
      self, mock_remove_older_than):
    FLAGS.remove_older_than_timespec = None
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        remove_older_than_timespec=None, label='unused',
        source_hostname='unused', settings_path=None,
        command_runner=mock_command_runner)

    backup.include('/unused')
    backup.run()

    self.assertFalse(mock_remove_older_than.called)

  @mock.patch.object(rdiff_backup_wrapper.RdiffBackup, '_remove_older_than')
  def testRemoveOlderThan_timespecArgIsNone_timespecFlagUsed(
      self, mock_remove_older_than):
    FLAGS.remove_older_than_timespec = '13D' 
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        remove_older_than_timespec=None, label='unused',
        source_hostname='unused', settings_path=None,
        command_runner=mock_command_runner)

    backup.include('/unused')
    backup.run()

    mock_remove_older_than.assert_called_once_with(
        timespec='13D', error_case=False)

  def testRemoveOlderThan_timespecIsNotNone_backupsTrimmed(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        remove_older_than_timespec='60D', label='fake_backup',
        source_hostname='unused', settings_path=None,
        command_runner=mock_command_runner)

    backup.include('/unused')
    backup.run()

    mock_command_runner.run.assert_called_with(
        ['/fake/rdiff-backup', '--force', '--remove-older-than', '60D',
         '/fake/backup-store/fake_backup'], False)

  def testCheckRequiredFlags_backupStorePathNotSet_raisesException(self):
    FLAGS.backup_store_path = None
    with self.assertRaises(Exception):
      backup = rdiff_backup_wrapper.RdiffBackup(
          label='unused', source_hostname='unused', settings_path=None)
      
  def testInclude_pathAddedToIncludesTracker(self):
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='unused', source_hostname='unused', settings_path=None)

    backup.include('/etc')
    backup.include('/var')

    self.assertEqual(backup._includes, ['/etc', '/var'])

  def testInclude_backupIncludesPaths(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include('/etc')
    backup.include('/var')
    backup.run()

    mock_command_runner.run.assert_called_once_with(
        ['/fake/rdiff-backup', '--include', '/etc', '--include', '/var',
         '--exclude', '**', '/', '/fake/backup-store/fake_backup'], False)

  def testExclude_backupExcludesPaths(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include('/var')
    backup.exclude('/var/cache')
    backup.run()

    mock_command_runner.run.assert_called_once_with(
        ['/fake/rdiff-backup', '--exclude', '/var/cache', '--include', '/var',
         '--exclude', '**', '/', '/fake/backup-store/fake_backup'], False)

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

    mock_command_runner.run.assert_called_once_with(
        ['/fake/rdiff-backup', '--force', '--remove-older-than', '60D',
         '/fake/backup-store/fake_backup'], False)

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

    backup.include('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(
        ['/fake/rdiff-backup', '--ssh-no-compression', '--include',
         '/fake_dir', '--exclude', '**', 'fake_user@fake_host::/',
         '/fake/backup-store/fake_backup'], False)

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

    backup.include('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(
        ['/fake/rdiff-backup', '--include', '/fake_dir', '--exclude', '**',
         'fake_user@fake_host::/', '/fake/backup-store/fake_backup'], False)

  def testRunCustomWorkflow_sourceHostnameIsLocalhost_sourceIsPath(self):
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(
        ['/fake/rdiff-backup', '--include', '/fake_dir', '--exclude', '**',
         '/', '/fake/backup-store/fake_backup'], False)

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

    backup.include('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(
        ['/fake/rdiff-backup',
         '--include', '/fake_dir', '--exclude', '**', 'fake_user@fake_host::/',
         '/fake/backup-store/fake_backup'], False)

  def testRunCustomWorkflow_rdiffBackupOptionsGiven_addsOptionsToCommand(self):
    FLAGS.rdiff_backup_options = '--fake-extra-option1 --fake-extra-option2'
    FLAGS.rdiff_backup_path = '/fake/rdiff-backup'
    FLAGS.backup_store_path = '/fake/backup-store'
    FLAGS.top_level_src_dir = '/'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = rdiff_backup_wrapper.RdiffBackup(
        label='fake_backup', source_hostname='localhost', settings_path=None,
        command_runner=mock_command_runner)

    backup.include('/fake_dir')
    backup.run()

    mock_command_runner.run.assert_called_once_with(
        ['/fake/rdiff-backup', '--fake-extra-option1', '--fake-extra-option2',
         '--include', '/fake_dir', '--exclude', '**', '/',
         '/fake/backup-store/fake_backup'], False)


class ZRdiffBackupCheckRequiredBinariesTest(
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
