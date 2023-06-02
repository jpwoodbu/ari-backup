import datetime
import os
import unittest
from unittest import mock

from absl import flags
from absl.testing import flagsaver

from ari_backup import test_lib
from ari_backup import zfs


FLAGS = flags.FLAGS
# Disable logging to stderr when running tests.
FLAGS.stderr_logging = False


class ZFSLVMBackupTest(unittest.TestCase):

    @mock.patch.object(zfs.ZFSLVMBackup, '_destroy_expired_zfs_snapshots')
    @mock.patch.object(zfs.ZFSLVMBackup, '_create_zfs_snapshot')
    def testWorkflowRunsInCorrectOrder(
            self, mock_create_zfs_snapshot,
            mock_destroy_expired_zfs_snapshots):
        mock_command_runner = test_lib.GetMockCommandRunner()
        mock_run_custom_workflow = mock.MagicMock()
        backup = zfs.ZFSLVMBackup(
            label='unused', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='unused_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])
        backup._run_custom_workflow = mock_run_custom_workflow
        # Attach mocks to manager mock so we can track their call order.
        manager_mock = mock.MagicMock()
        manager_mock.attach_mock(mock_run_custom_workflow,
                                 '_run_custom_workflow')
        manager_mock.attach_mock(mock_create_zfs_snapshot,
                                 '_create_zfs_snapshot')
        manager_mock.attach_mock(
            mock_destroy_expired_zfs_snapshots,
            '_destroy_expired_zfs_snapshots')
        # Create mock.call objects and defined their expected call order.
        run_custom_workflow_call = mock.call._run_custom_workflow()
        create_zfs_snapshot_call = mock.call._create_zfs_snapshot(
            error_case=False)
        destroy_expired_zfs_snapshots_call = (
            mock.call._destroy_expired_zfs_snapshots(
                days=30, error_case=False))
        expected_calls = [run_custom_workflow_call, create_zfs_snapshot_call,
                          destroy_expired_zfs_snapshots_call]

        backup.add_volume('unused_volume_group/unused_volume1', '/unused')
        backup.run()

        test_lib.AssertCallsInOrder(manager_mock, expected_calls)

    @flagsaver.flagsaver
    @unittest.skipUnless(os.name == 'posix',
                         'test expects posix path separator')
    def testRunCustomWorkflow(self):
        FLAGS.rsync_path = '/fake/rsync'
        FLAGS.rsync_options = '--fake-options'
        FLAGS.snapshot_mount_root = '/fake_root'

        mock_command_runner = test_lib.GetMockCommandRunner()
        # Note that setting source_hostname to 'localhost' prevents the command
        # that is run from being prefixed with an ssh command.
        backup = zfs.ZFSLVMBackup(
            label='fake_label', source_hostname='localhost',
            rsync_dst='fake_dst_host:/fake_dst',
            zfs_hostname='unused_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        backup._run_custom_workflow()

        mock_command_runner.run.assert_called_once_with(
            ['/fake/rsync', '--fake-options', '--exclude', '/.zfs',
             '/fake_root/fake_label/', 'fake_dst_host:/fake_dst'], False)

    @flagsaver.flagsaver
    @mock.patch.object(zfs.ZFSLVMBackup, '_get_current_datetime')
    def testCreateZFSSnapshot_errorCaseIsFalse_createsSnapshot(
            self, mock_get_current_datetime):
        FLAGS.zfs_snapshot_timestamp_format = '%Y-%m-%d--%H%M'
        FLAGS.zfs_snapshot_prefix = 'fake-prefix-'
        FLAGS.remote_user = 'fake_user'
        FLAGS.ssh_path = '/fake/ssh'
        FLAGS.ssh_port = 1234
        mock_get_current_datetime.return_value = datetime.datetime(
            2015, 1, 2, 3, 4)
        mock_command_runner = test_lib.GetMockCommandRunner()
        # Note that setting source_hostname to 'localhost' prevents the command
        # that is run from being prefixed with an ssh command.
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='localhost',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='fake_zfs_host',
            dataset_name='fake_pool/fake_dataset', snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        backup._create_zfs_snapshot(error_case=False)

        mock_command_runner.run.assert_called_once_with(
            ['/fake/ssh', '-p', '1234', 'fake_user@fake_zfs_host', 'zfs',
             'snapshot',
             'fake_pool/fake_dataset@fake-prefix-2015-01-02--0304'],
            False)

    def testCreateZFSSnapshot_errorCaseIsTrue_doesNothing(self):
        mock_command_runner = test_lib.GetMockCommandRunner()
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='unused_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        backup._create_zfs_snapshot(error_case=True)

        self.assertFalse(mock_command_runner.run.called)

    @flagsaver.flagsaver
    def testFindSnapshotsOlderThan_runsCorrectZFSCommand(self):
        FLAGS.remote_user = 'fake_user'
        FLAGS.ssh_path = '/fake/ssh'
        FLAGS.ssh_port = 1234
        mock_command_runner = test_lib.GetMockCommandRunner()
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='fake_zfs_host',
            dataset_name='fake_pool/fake_dataset', snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        backup._find_snapshots_older_than(30)

        mock_command_runner.run.assert_called_once_with(
            ['/fake/ssh', '-p', '1234', 'fake_user@fake_zfs_host', 'zfs',
             'get', '-rH', '-o', 'name,value', 'type',
             'fake_pool/fake_dataset'],
            False)

    @flagsaver.flagsaver
    @mock.patch.object(zfs.ZFSLVMBackup, '_get_current_datetime')
    @mock.patch.object(zfs.ZFSLVMBackup, '_get_snapshot_creation_time')
    def testFindSnapshotsOlderThan_returnsOnlySnapshots(
            self, mock_get_snapshot_creation_time, mock_get_current_datetime):
        FLAGS.zfs_snapshot_prefix = 'fake-prefix-'
        FLAGS.zfs_snapshot_timestamp_format = '%Y-%m-%d--%H%M'
        mock_get_snapshot_creation_time.side_effect = (
            [datetime.datetime(2014, 1, 5), datetime.datetime(2014, 1, 6)])
        mock_get_current_datetime.return_value = datetime.datetime(2014, 4, 1)
        fake_stdout = ('zfs/homedirs\tfilesystem\n'
                       'zfs/homedirs@fake-prefix-2014-01-05--0630\tsnapshot\n'
                       'zfs/homedirs@fake-prefix-2014-01-06--0648\tsnapshot\n')
        mock_command_runner = test_lib.GetMockCommandRunner()
        mock_command_runner.run.return_value = (fake_stdout, str(), 0)
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='unused_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        snapshots = backup._find_snapshots_older_than(30)

        self.assertEqual(snapshots,
                         ['zfs/homedirs@fake-prefix-2014-01-05--0630',
                          'zfs/homedirs@fake-prefix-2014-01-06--0648'])

    @flagsaver.flagsaver
    @mock.patch.object(zfs.ZFSLVMBackup, '_get_current_datetime')
    @mock.patch.object(zfs.ZFSLVMBackup, '_get_snapshot_creation_time')
    def testFindSnapshotsOlderThan_returnsOnlyPrefixedSnapshots(
            self, mock_get_snapshot_creation_time, mock_get_current_datetime):
        FLAGS.zfs_snapshot_prefix = 'fake-prefix-'
        FLAGS.zfs_snapshot_timestamp_format = '%Y-%m-%d--%H%M'
        mock_get_snapshot_creation_time.side_effect = (
            [datetime.datetime(2014, 1, 5), datetime.datetime(2014, 1, 6)])
        mock_get_current_datetime.return_value = datetime.datetime(2014, 4, 1)
        fake_stdout = ('zfs/homedirs@fake-prefix-2014-01-05--0630\tsnapshot\n'
                       'zfs/homedirs@2014-01-06--0648\tsnapshot\n')
        mock_command_runner = test_lib.GetMockCommandRunner()
        mock_command_runner.run.return_value = (fake_stdout, str(), 0)
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='unused_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        snapshots = backup._find_snapshots_older_than(30)

        self.assertEqual(snapshots,
                         ['zfs/homedirs@fake-prefix-2014-01-05--0630'])

    @flagsaver.flagsaver
    @mock.patch.object(zfs.ZFSLVMBackup, '_get_current_datetime')
    @mock.patch.object(zfs.ZFSLVMBackup, '_get_snapshot_creation_time')
    def testFindSnapshotsOlderThan_returnsOnlySnapshotsOlderThanX(
            self, mock_get_snapshot_creation_time, mock_get_current_datetime):
        FLAGS.zfs_snapshot_prefix = 'fake-prefix-'
        FLAGS.zfs_snapshot_timestamp_format = '%Y-%m-%d--%H%M'
        mock_get_snapshot_creation_time.side_effect = (
            [datetime.datetime(2014, 1, 5), datetime.datetime(2014, 3, 6)])
        mock_get_current_datetime.return_value = datetime.datetime(2014, 4, 1)
        fake_stdout = ('zfs/homedirs\tfilesystem\n'
                       'zfs/homedirs@fake-prefix-2014-01-05--0630\tsnapshot\n'
                       'zfs/homedirs@fake-prefix-2014-03-06--0648\tsnapshot\n')
        mock_command_runner = test_lib.GetMockCommandRunner()
        mock_command_runner.run.return_value = (fake_stdout, str(), 0)
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='unused_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        snapshots = backup._find_snapshots_older_than(30)

        self.assertEqual(snapshots,
                         ['zfs/homedirs@fake-prefix-2014-01-05--0630'])

    def testGetSnapshotCreationTime_parsesCreationTime(self):
        mock_command_runner = test_lib.GetMockCommandRunner()
        mock_command_runner.run.return_value = ('Sat Jan  3  6:48 2015', str(),
                                                0)
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='fake_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])
        expected_creation_time = datetime.datetime(2015, 1, 3, 6, 48)

        creation_time = backup._get_snapshot_creation_time(
            'unused_pool/unused_snapshot')

        self.assertEqual(creation_time, expected_creation_time)

    @flagsaver.flagsaver
    def testGetSnapshotCreationTime_runsCorrectZFSCommand(self):
        FLAGS.ssh_path = '/fake/ssh'
        FLAGS.ssh_port = 1234
        FLAGS.remote_user = 'fake_user'
        mock_command_runner = test_lib.GetMockCommandRunner()
        mock_command_runner.run.return_value = ('Sat Jan  3  6:48 2015', str(),
                                                0)
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='fake_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        backup._get_snapshot_creation_time('fake_pool/fake_snapshot')

        mock_command_runner.run.assert_called_once_with(
            ['/fake/ssh', '-p', '1234', 'fake_user@fake_zfs_host', 'zfs',
             'get', '-H', '-o', 'value', 'creation',
             'fake_pool/fake_snapshot'],
            False)

    @flagsaver.flagsaver
    @mock.patch.object(zfs.ZFSLVMBackup, '_get_current_datetime')
    @mock.patch.object(zfs.ZFSLVMBackup, '_find_snapshots_older_than')
    def testDestroyExpiredZFSSnapshots_errorCaseIsFalse_destroysSnapshots(
            self, mock_find_snapshots_older_than, mock_get_current_datetime):
        FLAGS.ssh_path = '/fake/ssh'
        FLAGS.ssh_port = 1234
        FLAGS.remote_user = 'fake_user'
        mock_find_snapshots_older_than.return_value = [
            'zfs/homedirs@fake-prefix-2014-01-05--0630',
            'zfs/homedirs@fake-prefix-2014-01-06--0648']
        mock_get_current_datetime.return_value = datetime.datetime(2014, 4, 1)
        mock_command_runner = test_lib.GetMockCommandRunner()
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='fake_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])
        expected_call1 = mock.call(
            ['/fake/ssh', '-p', '1234', 'fake_user@fake_zfs_host', 'zfs',
             'destroy', 'zfs/homedirs@fake-prefix-2014-01-05--0630'], False)
        expected_call2 = mock.call(
            ['/fake/ssh', '-p', '1234', 'fake_user@fake_zfs_host', 'zfs',
             'destroy', 'zfs/homedirs@fake-prefix-2014-01-06--0648'], False)

        backup._destroy_expired_zfs_snapshots(30, error_case=False)

        self.assertEqual(
            mock_command_runner.run.mock_calls,
            [expected_call1, expected_call2])

    def testDestroyExpiredZFSSnapshots_errorCaseIsTrue_doesNothing(self):
        mock_command_runner = test_lib.GetMockCommandRunner()
        backup = zfs.ZFSLVMBackup(
            label='unused_label', source_hostname='unused',
            rsync_dst='unused_dst_host:/unused_dst',
            zfs_hostname='unused_zfs_host',
            dataset_name='unused_pool/unused_dataset',
            snapshot_expiration_days=30,
            settings_path=None, command_runner=mock_command_runner,
            argv=['fake_program'])

        backup._destroy_expired_zfs_snapshots(30, error_case=True)

        self.assertFalse(mock_command_runner.run.called)


if __name__ == '__main__':
    unittest.main()
