import copy
import os
import unittest

import gflags
import mock

import lvm
import test_lib
import workflow


FLAGS = gflags.FLAGS
# Disable logging to stderr when running tests.
FLAGS.stderr_logging = False


class FakeBackup(lvm.LVMSourceMixIn, workflow.BaseWorkflow):
  """Fake class to help test the LVMSourceMixIn class."""
  def __init__(self, source_hostname, *args, **kwargs):
    """Initalizes the class.

    The source_hostname attribute is added to the instance as it is needed by
    the LVMSourceMixIn.

    args:
    source_hostname -- the name of the host with the source data to backup

    """
    super(FakeBackup, self).__init__(*args, **kwargs)
    self.source_hostname = source_hostname

  def _run_custom_workflow(self):
    pass


class LVMSourceMixInTest(test_lib.FlagSaverMixIn, unittest.TestCase):

  @mock.patch.object(FakeBackup, '_run_custom_workflow')
  @mock.patch.object(lvm.LVMSourceMixIn, '_delete_snapshots')
  @mock.patch.object(lvm.LVMSourceMixIn, '_umount_snapshots')
  @mock.patch.object(lvm.LVMSourceMixIn, '_mount_snapshots')
  @mock.patch.object(lvm.LVMSourceMixIn, '_create_snapshots')
  def testWorkflowRunsInCorrectOrder(
      self, mock_create_snapshots, mock_mount_snapshots, mock_umount_snapshots,
      mock_delete_snapshots, mock_run_custom_workflow):
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = FakeBackup(
        source_hostname='unused', label='unused', settings_path=None,
        command_runner=mock_command_runner)
    # Attach mocks to manager mock so we can track their call order.
    manager_mock = mock.MagicMock()
    manager_mock.attach_mock(mock_create_snapshots, '_create_snapshots')
    manager_mock.attach_mock(mock_mount_snapshots, '_mount_snapshots')
    manager_mock.attach_mock(mock_umount_snapshots, '_umount_snapshots')
    manager_mock.attach_mock(mock_delete_snapshots, '_delete_snapshots')
    manager_mock.attach_mock(mock_run_custom_workflow, '_run_custom_workflow')
    # Create mock.call objects and defined their expected call order.
    create_snapshots_call = mock.call._create_snapshots()
    mount_snapshots_call = mock.call._mount_snapshots()
    umount_snapshots_call = mock.call._umount_snapshots(error_case=False)
    delete_snapshots_call = mock.call._delete_snapshots(error_case=False)
    run_custom_workflow_call = mock.call._run_custom_workflow()
    expected_calls = [create_snapshots_call, mount_snapshots_call,
                      run_custom_workflow_call, umount_snapshots_call,
                      delete_snapshots_call]

    backup.add_volume('fake_volume_group/fake_volume1', '/unused')
    backup.run()

    test_lib.AssertCallsInOrder(manager_mock, expected_calls)

  def testAddVolume_noMountOptions_addsVolumeWithNoneAsMountOptions(self):
    backup = FakeBackup(source_hostname='unused', label='fake_backup',
                        settings_path=None)
    backup.add_volume('fake_volume_group/fake_volume', '/etc')
    self.assertEqual(backup._logical_volumes,
                     [('fake_volume_group/fake_volume', '/etc', None)])

  def testAddVolume_hasMountOptions_addsVolumeWithMountOptions(self):
    backup = FakeBackup(source_hostname='unused', label='fake_backup',
                        settings_path=None)
    backup.add_volume('fake_volume_group/fake_volume', '/etc', 'ro')
    self.assertEqual(backup._logical_volumes,
                     [('fake_volume_group/fake_volume', '/etc', 'ro')])

  def testCreateSnapshots_multipleSnapshots_createsSnapshots(self):
    FLAGS.snapshot_suffix = '-fake_backup'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = FakeBackup(
        source_hostname='localhost', label='unused', settings_path=None,
        command_runner=mock_command_runner)
    expected_call_fakevolume1 = mock.call(
        ['lvcreate', '-s', '-L', '1G', 'fake_volume_group/fake_volume1', '-n',
         'fake_volume1-fake_backup'], True)
    expected_call_fakevolume2 = mock.call(
        ['lvcreate', '-s', '-L', '1G', 'fake_volume_group/fake_volume2', '-n',
         'fake_volume2-fake_backup'], True)

    backup.add_volume('fake_volume_group/fake_volume1', '/etc')
    backup.add_volume('fake_volume_group/fake_volume2', '/var')
    backup.run()

    mock_command_runner.run.assert_has_calls(
        [expected_call_fakevolume1, expected_call_fakevolume2], any_order=True)

  @unittest.skipUnless(os.name == 'posix', 'test expects posix path separator')
  def testCreateSnapshots_multipleSnapshots_addsSnapshotsToTracker(self):
    FLAGS.snapshot_mount_root = '/fake_root'
    FLAGS.snapshot_suffix = '-fake_backup'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = FakeBackup(
        source_hostname='localhost', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    expected_value = [
        {
            'lv_path': 'fake_volume_group/fake_volume1-fake_backup',
            'mount_path': '/fake_root/fake_backup/etc',
            'mount_options': None,
            'created': True,
            'mount_point_created': False,
            'mounted': False,
        },
        {
            'lv_path': 'fake_volume_group/fake_volume2-fake_backup',
            'mount_path': '/fake_root/fake_backup/var',
            'mount_options': None,
            'created': True,
            'mount_point_created': False,
            'mounted': False,
        },
    ]

    backup.add_volume('fake_volume_group/fake_volume1', '/etc')
    backup.add_volume('fake_volume_group/fake_volume2', '/var')
    backup._create_snapshots()

    self.assertListEqual(expected_value, backup._lv_snapshots)

  def testDeleteSnapshots_multipleSnapshots_deletesSnapshots(self):
    FLAGS.snapshot_suffix = '-fake_backup'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = FakeBackup(
        source_hostname='localhost', label='unused', settings_path=None,
        command_runner=mock_command_runner)
    expected_call_fakevolume1 = mock.call(
        ['lvremove', '-f', 'fake_volume_group/fake_volume1-fake_backup'], True)
    expected_call_fakevolume2 = mock.call(
        ['lvremove', '-f', 'fake_volume_group/fake_volume2-fake_backup'], True)

    backup.add_volume('fake_volume_group/fake_volume1', '/unused1')
    backup.add_volume('fake_volume_group/fake_volume2', '/unused2')
    backup.run()

    mock_command_runner.run.assert_has_calls(
        [expected_call_fakevolume1, expected_call_fakevolume2], any_order=True)

  def testDeleteSnapshots_multipleSnapshots_marksSnapshotsAsDeleted(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = FakeBackup(
        source_hostname='unused', label='unused', settings_path=None,
        command_runner=mock_command_runner)
    backup.add_volume('fake_volume_group/fake_volume1', '/unused1')
    backup.add_volume('fake_volume_group/fake_volume2', '/unused2')
    backup.run()

    self.assertFalse(backup._lv_snapshots[0]['created'])
    self.assertFalse(backup._lv_snapshots[1]['created'])

  @unittest.skipUnless(os.name == 'posix', 'test expects posix path separator')
  def testMountSnapshots_multipleSnapshots_makesMountPointDirectories(self):
    FLAGS.snapshot_mount_root = '/fake_root'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = FakeBackup(
        source_hostname='localhost', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    expected_call_fakevolume1 = mock.call(
        ['mkdir', '-p', '/fake_root/fake_backup/etc'], True)
    expected_call_fakevolume2 = mock.call(
        ['mkdir', '-p', '/fake_root/fake_backup/var'], True)

    backup.add_volume('fake_volume_group/fake_volume1', '/etc')
    backup.add_volume('fake_volume_group/fake_volume2', '/var')
    backup.run()

    mock_command_runner.AssertCallsInOrder(
        [expected_call_fakevolume1, expected_call_fakevolume2])

  def testMountSnapshots_multipleSnapshots_marksMountPointAsCreated(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = FakeBackup(
        source_hostname='unused', label='unused', settings_path=None,
        command_runner=mock_command_runner)

    backup.add_volume('fake_volume_group/fake_volume1', '/unused1')
    backup.add_volume('fake_volume_group/fake_volume2', '/unused2')
    backup._create_snapshots()
    backup._mount_snapshots()

    self.assertTrue(backup._lv_snapshots[0]['mount_point_created'])
    self.assertTrue(backup._lv_snapshots[1]['mount_point_created'])

  @mock.patch.object(os.path, 'ismount')
  def testMountSnapshots_mountPointAlreadyExists_backupFails(
      self, mock_ismount):
    mock_ismount.return_value = True
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = FakeBackup(
        source_hostname='unused', label='unused', settings_path=None,
        command_runner=mock_command_runner)
    backup.add_volume('fake_volume_group/fake_volume1', '/unused')

    self.assertFalse(backup.run())

  @unittest.skipUnless(os.name == 'posix', 'test expects posix path separator')
  def testMountSnapshots_withMountOptions_mountsWithMountOptions(self):
    FLAGS.snapshot_mount_root = '/fake_root'
    FLAGS.snapshot_suffix = '-fake_backup'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = FakeBackup(
        source_hostname='localhost', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    expected_call_fakevolume1 = mock.call(
        ['mount', '-o', 'ro',
         '/dev/fake_volume_group/fake_volume1-fake_backup',
         '/fake_root/fake_backup/etc'], True)
    expected_call_fakevolume2 = mock.call(
        ['mount', '-o', 'noexec',
        '/dev/fake_volume_group/fake_volume2-fake_backup',
         '/fake_root/fake_backup/var'], True)

    backup.add_volume('fake_volume_group/fake_volume1', '/etc', 'ro')
    backup.add_volume('fake_volume_group/fake_volume2', '/var', 'noexec')
    backup.run()

    mock_command_runner.AssertCallsInOrder(
        [expected_call_fakevolume1, expected_call_fakevolume2])

  @unittest.skipUnless(os.name == 'posix', 'test expects posix path separator')
  def testMountSnapshots_withoutMountOptions_mountsWithoutMountOptions(self):
    FLAGS.snapshot_mount_root = '/fake_root'
    FLAGS.snapshot_suffix = '-fake_backup'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = FakeBackup(
        source_hostname='localhost', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    expected_call_fakevolume1 = mock.call(
        ['mount', '/dev/fake_volume_group/fake_volume1-fake_backup',
         '/fake_root/fake_backup/etc'], True)
    expected_call_fakevolume2 = mock.call(
        ['mount', '/dev/fake_volume_group/fake_volume2-fake_backup',
         '/fake_root/fake_backup/var'], True)

    backup.add_volume('fake_volume_group/fake_volume1', '/etc')
    backup.add_volume('fake_volume_group/fake_volume2', '/var')
    backup.run()

    mock_command_runner.AssertCallsInOrder(
        [expected_call_fakevolume1, expected_call_fakevolume2])

  def testMountSnapshots_multipleSnapshots_marksSnapshotsAsMounted(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = FakeBackup(
        source_hostname='unused', label='unused', settings_path=None,
        command_runner=mock_command_runner)
    backup.add_volume('fake_volume_group/fake_volume1', '/unused1')
    backup.add_volume('fake_volume_group/fake_volume2', '/unused2')
    backup._create_snapshots()
    backup._mount_snapshots()

    self.assertTrue(backup._lv_snapshots[0]['mounted'])
    self.assertTrue(backup._lv_snapshots[1]['mounted'])

  @unittest.skipUnless(os.name == 'posix', 'test expects posix path separator')
  def testUnmountSnapshots_snapshotsMounted_snapshotsUnmounted(self):
    FLAGS.snapshot_suffix = '-fake_backup'
    FLAGS.snapshot_mount_root = '/fake_root'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = FakeBackup(
        source_hostname='localhost', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    expected_call_fakevolume1 = mock.call(
        ['umount', '/fake_root/fake_backup/etc'], True)
    expected_call_fakevolume2 = mock.call(
        ['umount', '/fake_root/fake_backup/var'], True)

    backup.add_volume('fake_volume_group/fake_volume1', '/etc')
    backup.add_volume('fake_volume_group/fake_volume2', '/var')
    backup.run()

    # Note that snapshots are unmounted in reverse order.
    mock_command_runner.AssertCallsInOrder(
        [expected_call_fakevolume2, expected_call_fakevolume1])

  @unittest.skipUnless(os.name == 'posix', 'test expects posix path separator')
  def testUnmountSnapshots_mountPointsCreated_mountPointsRemoved(self):
    FLAGS.snapshot_suffix = '-fake_backup'
    FLAGS.snapshot_mount_root = '/fake_root'
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Note that setting source_hostname to 'localhost' prevents the command
    # that is run from being prefixed with an ssh command.
    backup = FakeBackup(
        source_hostname='localhost', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    expected_call_fakevolume1 = mock.call(
        ['rmdir', '/fake_root/fake_backup/etc'], True)
    expected_call_fakevolume2 = mock.call(
        ['rmdir', '/fake_root/fake_backup/var'], True)

    backup.add_volume('fake_volume_group/fake_volume1', '/etc')
    backup.add_volume('fake_volume_group/fake_volume2', '/var')
    backup._create_snapshots()
    backup._mount_snapshots()
    backup._umount_snapshots()

    # Note that mountpoints are removed in reverse order.
    mock_command_runner.AssertCallsInOrder(
        [expected_call_fakevolume2, expected_call_fakevolume1])


class RdiffLVMBackupTest(test_lib.FlagSaverMixIn, unittest.TestCase):

  def setUp(self):
    super(RdiffLVMBackupTest, self).setUp()
    FLAGS.backup_store_path = '/unused'

  def testRunCustomWorkflow_prefixesIncludeDirs(self):
    FLAGS.snapshot_mount_root = '/fake_root'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = lvm.RdiffLVMBackup(
        source_hostname='unused', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    
    backup.add_volume('fake_volume_group/fake_volume', '/var')
    backup.include_dir('/var')
    backup.run()

    self.assertEqual(backup._include_dirs, ['/fake_root/fake_backup/var'])

  def testRunCustomWorkflow_prefixesExcludeDirs(self):
    FLAGS.snapshot_mount_root = '/fake_root'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = lvm.RdiffLVMBackup(
        source_hostname='unused', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    
    backup.add_volume('fake_volume_group/fake_volume', '/var')
    backup.include_dir('/var')
    backup.exclude_dir('/var/cache')
    backup.run()

    self.assertEqual(
        backup._exclude_dirs, ['/fake_root/fake_backup/var/cache'])

  def testRunCustomWorkflow_updatesTopLevelSrcDirToSnapshotMountPointBasePath(
      self):
    FLAGS.snapshot_mount_root = '/fake_root'
    mock_command_runner = test_lib.GetMockCommandRunner()
    backup = lvm.RdiffLVMBackup(
        source_hostname='unused', label='fake_backup', settings_path=None,
        command_runner=mock_command_runner)
    
    backup.run()

    self.assertEqual(backup.top_level_src_dir, '/fake_root/fake_backup')


if __name__ == '__main__':
  unittest.main()
