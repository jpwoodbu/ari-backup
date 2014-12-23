import copy
import mock
import os
import subprocess
import unittest

import gflags

import lvm
import workflow


FLAGS = gflags.FLAGS



def only_if_posix(func):
  """Decorator to only run a test in a POSIX environment.
    
  If the test is executed in an environment other than POSIX, it will simply
  return rather than running the actual test code. This will make the test
  appear to pass, but it will actually not run at all. This prevents the test
  from being brittle while permitting ideal test code for POSIX environments.
  """
  def wrapper(self):
    if os.name == 'posix':
      return func(self)
    else:
      return
  return wrapper


class FakeBackupClass(lvm.LVMSourceMixIn, workflow.BaseWorkflow):
  """Fake class to help test the LVMSourceMixIn class."""
  def _run_custom_workflow(self):
    pass


class LVMSourceMixInTest(unittest.TestCase):

  def setUp(self):
    super(LVMSourceMixInTest, self).setUp()
    self._save_flags()

  def tearDown(self):
    super(LVMSourceMixInTest, self).tearDown()
    self._restore_flags()

  def _save_flags(self):
    self._flag_values = copy.deepcopy(FLAGS.__dict__)

  def _restore_flags(self):
    FLAGS.__dict__.update(self._flag_values)

  # TODO(jpwoodbu) Replace this test with other "front door" tests.
  @only_if_posix
  def testInit_setsSnapshotMountPointBasePath(self):
    FLAGS.snapshot_mount_root = '/fake_root'
    backup = FakeBackupClass(label='fake_backup', settings_path=None)
    self.assertEqual(backup._snapshot_mount_point_base_path,
                     '/fake_root/fake_backup')

  @mock.patch.object(subprocess, 'Popen')
  def testWorkflowCreatesSnapshotsBeforeBackup(self, mock_popen):
    FLAGS.snapshot_mount_root = '/fake_root'
    FLAGS.snapshot_suffix = '-fake_backup'
    backup = FakeBackupClass(label='fake_backup', settings_path=None)
    
    backup.add_volume('fake_volume_group/fake_volume', '/etc')
    backup.run()

  def testWorkflowMountsSnapshotsBeforeBackup(self):
    command_runner = workflow.CommandRunner()
    command_runner.run = mock.MagicMock()

    backup = FakeBackupClass(label='fake_backup')


  def testWorkflowUnmountsSnapshotsAfterBackup(self):
    pass

  def testWorkflowDeletesSnapshotsAfterBackup(self):
    pass


if __name__ == '__main__':
  unittest.main()
