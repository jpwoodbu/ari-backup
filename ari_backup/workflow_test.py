import unittest

import workflow


class BaseWorkflowTest(unittest.TestCase):

  def testInit_userSettingsOverridesFlagDefaults(self):
    pass

  def testAddPreHook_addFunctionWithKwargs_addsHook(self):
    pass

  def testAddPreHook_addFunctionWithOutKwargs_addsHookWithEmptyKwargs(self):
    pass

  def testInsertPreHook_addFunctionWithKwargs_addsHook(self):
    pass

  def testInsertPreHook_addFunctionWithOutKwargs_addsHookWithEmptyKwargs(self):
    pass

  def testDeletePreHook(self):
    pass

  def testAddPostHook_addFunctionWithKwargs_addsHook(self):
    pass

  def testAddPostHook_addFunctionWithOutKwargs_addsHookWithEmptyKwargs(self):
    pass

  def testInsertPostHook_addFunctionWithKwargs_addsHook(self):
    pass

  def testInsertPostHook_addFunctionWithOutKwargs_addsHookWithEmptyKwargs(
      self):
    pass

  def testDeletePostHook(self):
    pass

  def testProcessPreJobHooks(self):
    pass

  def testProcessPostJobHook_errorCaseIsTrue_errorCaseTrueInKwargs(self):
    pass

  def testProcessPostJobHook_errorCaseKwargSetFromErrorCaseArg(self):
    pass

  def testRunCommand_commandIsString_commandIsRun(self):
    pass

  def testRunCommand_commandIsList_commandIsRun(self):
    pass

  def testRunCommand_commandIsNotStringOrList_raisesException(self):
    pass

  def testRunCommand_hostIsNotLocalhost_sshArgumentsAdded(self):
    pass

  def testRunCommand_commandNotFound_raisesException(self):
    pass

  def testRunCommand_commandHasNonZeroExitCode_rasiesException(self):
    pass

  def testRunCommand_returnsStdoutAndStdErr(self):
    pass

  def testRunCommandWithRetries(self):
    pass


if __name__ == '__main__':
    unittest.main()
