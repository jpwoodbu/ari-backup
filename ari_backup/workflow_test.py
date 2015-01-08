import unittest
import time

import gflags
import mock

import workflow
import test_lib


FLAGS = gflags.FLAGS
# Disable logging to stderr when running tests.
FLAGS.stderr_logging = False


class BaseWorkflowTest(test_lib.FlagSaverMixIn, unittest.TestCase):

  @mock.patch.object(workflow.BaseWorkflow, '_get_settings_from_file')
  def testInit_userSettingsOverridesFlagDefaults(self,
      mock_get_settings_from_file):
    FLAGS.remote_user = 'not_overridden_username'
    mock_get_settings_from_file.return_value = {'remote_user':
                                                'overridden_username'}

    test_workflow = workflow.BaseWorkflow(
        label='unused',
        settings_path='/path/which/is/not/None/so/settings/are/loaded')

    self.assertEqual(FLAGS.remote_user, 'overridden_username')

  def testAddPreHook_functionWithKwargs_addsHook(self):
    test_func = lambda x: x
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)
    test_workflow.add_pre_hook(test_func, {'kwarg': 'kwarg_value'})
    self.assertEqual(test_workflow._pre_job_hooks[0],
                     (test_func, {'kwarg': 'kwarg_value'}))

  def testAddPreHook_functionWithOutKwargs_addsHookWithEmptyKwargs(self):
    test_func = lambda x: x
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)
    test_workflow.add_pre_hook(test_func)
    self.assertEqual(test_workflow._pre_job_hooks[0], (test_func, {}))

  def testInsertPreHook_functionWithKwargs_insertsHookAtIndex(self):
    test_func1 = lambda x: x
    test_func2 = lambda y: y
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)

    test_workflow.add_pre_hook(test_func1)
    test_workflow.insert_pre_hook(0, test_func2, {'kwarg': 'kwarg_value'})

    self.assertEqual(test_workflow._pre_job_hooks[0],
                     (test_func2, {'kwarg': 'kwarg_value'}))

  def testInsertPreHook_functionWithOutKwargs_insertsHookWithEmptyKwargs(self):
    test_func1 = lambda x: x
    test_func2 = lambda y: y
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)

    test_workflow.add_pre_hook(test_func1)
    test_workflow.insert_pre_hook(0, test_func2)

    self.assertEqual(test_workflow._pre_job_hooks[0], (test_func2, {}))

  def testDeletePreHook(self):
    test_func1 = lambda x: x
    test_func2 = lambda y: y
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)

    test_workflow.add_pre_hook(test_func1)
    test_workflow.add_pre_hook(test_func2)
    test_workflow.delete_pre_hook(0)

    self.assertEqual(test_workflow._pre_job_hooks, [(test_func2, {})])

  def testAddPostHook_functionWithKwargs_addsHook(self):
    test_func = lambda x: x
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)
    test_workflow.add_post_hook(test_func, {'kwarg': 'kwarg_value'})
    self.assertEqual(test_workflow._post_job_hooks[0],
                     (test_func, {'kwarg': 'kwarg_value'}))

  def testAddPostHook_functionWithOutKwargs_addsHookWithEmptyKwargs(self):
    test_func = lambda x: x
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)
    test_workflow.add_post_hook(test_func)
    self.assertEqual(test_workflow._post_job_hooks[0], (test_func, {}))

  def testInsertPostHook_functionWithKwargs_insertsHook(self):
    test_func1 = lambda x: x
    test_func2 = lambda y: y
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)

    test_workflow.add_pre_hook(test_func1)
    test_workflow.insert_pre_hook(0, test_func2, {'kwarg': 'kwarg_value'})

    self.assertEqual(test_workflow._pre_job_hooks[0],
                     (test_func2, {'kwarg': 'kwarg_value'}))

  def testInsertPostHook_functionWithOutKwargs_addsHookWithEmptyKwargs(self):
    test_func1 = lambda x: x
    test_func2 = lambda y: y
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)

    test_workflow.add_post_hook(test_func1)
    test_workflow.insert_post_hook(0, test_func2)

    self.assertEqual(test_workflow._post_job_hooks[0], (test_func2, {}))

  def testDeletePostHook(self):
    test_func1 = lambda x: x
    test_func2 = lambda y: y
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)

    test_workflow.add_post_hook(test_func1)
    test_workflow.add_post_hook(test_func2)
    test_workflow.delete_post_hook(0)

    self.assertEqual(test_workflow._post_job_hooks, [(test_func2, {})])

  def testProcessPreJobHooks(self):
    mock_pre_hook1 = mock.MagicMock()
    mock_pre_hook2 = mock.MagicMock()
    mock_run_custom_workflow = mock.MagicMock()
    # Attach mocks to manager mock so we can track their call order.
    manager_mock = mock.MagicMock()
    manager_mock.attach_mock(mock_pre_hook1, 'pre_hook1')
    manager_mock.attach_mock(mock_pre_hook2, 'pre_hook2')
    manager_mock.attach_mock(mock_run_custom_workflow, '_run_custom_workflow')
    # Create mock.call objects and defined their expected call order.
    pre_hook1_call = mock.call.pre_hook1(kwarg='kwarg_value1')
    pre_hook2_call = mock.call.pre_hook2(kwarg='kwarg_value2')
    run_custom_workflow_call = mock.call._run_custom_workflow()
    expected_calls = [pre_hook1_call, pre_hook2_call, run_custom_workflow_call]
    # Create BaseWorkflow object and "override" its _run_custom_workflow method
    # to simulate what a BaseWorkflow subclass would do.
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)
    test_workflow._run_custom_workflow = mock_run_custom_workflow

    test_workflow.add_pre_hook(mock_pre_hook1, {'kwarg': 'kwarg_value1'})
    test_workflow.add_pre_hook(mock_pre_hook2, {'kwarg': 'kwarg_value2'})
    test_workflow.run()

    test_lib.AssertCallsInOrder(manager_mock, expected_calls)

  def testProcessPostJobHook_errorCaseKwargSetFromErrorCaseArg(self):
    mock_post_hook1 = mock.MagicMock()
    mock_post_hook2 = mock.MagicMock()
    mock_run_custom_workflow = mock.MagicMock()
    # Attach mocks to manager mock so we can track their call order.
    manager_mock = mock.MagicMock()
    manager_mock.attach_mock(mock_post_hook1, 'post_hook1')
    manager_mock.attach_mock(mock_post_hook2, 'post_hook2')
    manager_mock.attach_mock(mock_run_custom_workflow, '_run_custom_workflow')
    # Create mock.call objects and defined their expected call order.
    post_hook1_call = mock.call.post_hook1(kwarg='kwarg_value1',
                                           error_case=False)
    post_hook2_call = mock.call.post_hook2(kwarg='kwarg_value2',
                                           error_case=False)
    run_custom_workflow_call = mock.call._run_custom_workflow()
    expected_calls = [run_custom_workflow_call, post_hook1_call,
                      post_hook2_call]
    # Create BaseWorkflow object and "override" its _run_custom_workflow method
    # to simulate what a BaseWorkflow subclass would do.
    test_workflow = workflow.BaseWorkflow(label='unused', settings_path=None)
    test_workflow._run_custom_workflow = mock_run_custom_workflow

    test_workflow.add_post_hook(mock_post_hook1, {'kwarg': 'kwarg_value1'})
    test_workflow.add_post_hook(mock_post_hook2, {'kwarg': 'kwarg_value2'})
    test_workflow.run()

    test_lib.AssertCallsInOrder(manager_mock, expected_calls)

  def testRunCommand_commandIsString_commandIsRun(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    test_workflow.run_command(
        'test_command --test_flag test_arg', host='localhost')

    mock_command_runner.run.assert_called_once_with(
        ['test_command', '--test_flag', 'test_arg'])

  def testRunCommand_commandIsList_commandIsRun(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    test_workflow.run_command(
        ['test_command', '--test_flag', 'test_arg'], host='localhost')

    mock_command_runner.run.assert_called_once_with(
        ['test_command', '--test_flag', 'test_arg'])

  def testRunCommand_commandIsNotStringOrList_raisesException(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    with self.assertRaises(TypeError):
      test_workflow.run_command(None)

  def testRunCommand_hostIsNotLocalhost_sshArgumentsAdded(self):
    FLAGS.remote_user = 'test_user'
    FLAGS.ssh_path = '/fake/ssh'
    FLAGS.ssh_port = 1234
    mock_command_runner = test_lib.GetMockCommandRunner()
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    test_workflow.run_command(
        'test_command --test_flag test_arg', host='fake_host')

    mock_command_runner.run.assert_called_once_with(
        ['/fake/ssh', '-p', '1234', 'test_user@fake_host', 'test_command',
         '--test_flag', 'test_arg'])

  def testRunCommand_commandHasNonZeroExitCode_rasiesException(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Return empty strings for stdout and stderr and 1 for the exit code.
    mock_command_runner.run.return_value = (str(), str(), 1)
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    with self.assertRaises(workflow.NonZeroExitCode):
      test_workflow.run_command('test_command')

  def testRunCommand_returnsStdoutAndStdErr(self):
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Return fake strings for stdout and stderr and 0 for the exit code.
    mock_command_runner.run.return_value = ('fake_stdout', 'fake_stderr',  0)
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    stdout, stderr = test_workflow.run_command('test_command')

    self.assertEqual(stdout, 'fake_stdout')
    self.assertEqual(stderr, 'fake_stderr')

  @mock.patch.object(time, 'sleep')
  def testRunCommandWithRetries_firstTrySucceeds_commandNotRetried(
      self, unused_mock_sleep):
    mock_command_runner = test_lib.GetMockCommandRunner()
    # Return empty strings for stdout and stderr and 0 (success) for the exit
    # code.
    mock_command_runner.run.return_value = (str(), str(), 0)
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    test_workflow.run_command_with_retries('test_command')

    self.assertEqual(mock_command_runner.run.call_count, 1)

  @mock.patch.object(time, 'sleep')
  def testRunCommandWithRetries_firstTryFails_commandRetried(
      self, unused_mock_sleep):
    FLAGS.max_retries = 1
    mock_command_runner = test_lib.GetMockCommandRunner()
    return1 = (str(), str(), 1)  # command failed
    return2 = (str(), str(), 0)  # command succeeded
    mock_command_runner.run.side_effect = [return1, return2]
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    test_workflow.run_command_with_retries('test_command')

    self.assertEqual(mock_command_runner.run.call_count, 2)

  @mock.patch.object(time, 'sleep')
  def testRunCommandWithRetries_maxRetriesReached_raisesException(
      self, unused_mock_sleep):
    FLAGS.max_retries = 1
    mock_command_runner = test_lib.GetMockCommandRunner()
    return1 = (str(), str(), 1)  # command failed
    return2 = (str(), str(), 1)  # command failed
    return3 = (str(), str(), 0)  # command succeeded
    mock_command_runner.run.side_effect = [return1, return2, return3]
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    with self.assertRaises(workflow.NonZeroExitCode):
      test_workflow.run_command_with_retries('test_command')

  @mock.patch.object(time, 'sleep')
  def testRunCommandWithRetries_firstTryFails_sleepsBetweenRetries(
      self, mock_sleep):
    FLAGS.max_retries = 1
    FLAGS.retry_interval = 7
    mock_command_runner = test_lib.GetMockCommandRunner()
    return1 = (str(), str(), 1)  # command failed
    return2 = (str(), str(), 0)  # command succeeded
    mock_command_runner.run.side_effect = [return1, return2]
    test_workflow = workflow.BaseWorkflow(
        label='unused', settings_path=None, command_runner=mock_command_runner)

    test_workflow.run_command_with_retries('test_command')

    mock_sleep.assert_called_once_with(7)


if __name__ == '__main__':
    unittest.main()
