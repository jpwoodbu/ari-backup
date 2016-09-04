import copy
import mock

import gflags


FLAGS = gflags.FLAGS


class FlagSaverMixIn(object):
    """A mix in class to preserve gflags values between tests.

    This class can be subclasses by test classes to permit tests to safely
    modify the values of gflags. The original value will be restored after the
    test completes.
    """
    def setUp(self):
        super(FlagSaverMixIn, self).setUp()
        self._save_flags()

    def tearDown(self):
        super(FlagSaverMixIn, self).tearDown()
        self._restore_flags()

    def _save_flags(self):
        self._flag_values = copy.deepcopy(FLAGS.__dict__)

    def _restore_flags(self):
        FLAGS.__dict__.update(self._flag_values)


def GetMockCommandRunner():
    """Creates a mock version of workflow.CommandRunner helpful for testing.

    This mock is useful for testing how the run() method of the CommandRunner
    is called. To avoid breaking the flow of code under test, it always returns
    an empty string for stdout and stderr and a returncode of 0 (success).

    Returns:
        A tuple with exactly this value: ('', '', 0) meant to represent the
        stdout, the stderr, and the return code of the executed command.
    """
    mock_command_runner = mock.MagicMock()
    mock_command_runner.run = mock.MagicMock()
    stdout = str()
    stderr = str()
    returncode = 0
    mock_command_runner.run.return_value = (stdout, stderr, returncode)

    # Attach the AssertCallsInOrder function as a function on the returned
    # object to make using the AssertCallsInOrder function more convenient (the
    # user won't have to pass in the mock object with the recorded calls).
    mock_command_runner.AssertCallsInOrder = GetAssertCallsInOrderWrapper(
        mock_command_runner.run)

    return mock_command_runner


def GetAssertCallsInOrderWrapper(mock_object):
    """Convenience wrapper around AssertCallsInOrder.

    This function returns a wrapper around AssertCallsInOrder which already
    has a reference to the mock object with the record of calls made on the
    mock.

    Args:
        mock_object: mock.Mock, the mock object which will contain the record
            of calls.

    Returns:
        A callable which acts like AssertCallsInOrder but only requires passing
        the calls argument.
    """
    def wrapper(calls):
        return AssertCallsInOrder(mock_object, calls)
    return wrapper


def AssertCallsInOrder(mock_object, calls):
    """Test whether calls on a mock object are called in a particular order.

    This test doesn't care whether all the calls recorded on the mock are
    present in the given "calls" argument. It does care that all calls in the
    "calls" argument are present in the calls recorded on the mock, and that
    the order of those calls matches the order in the "calls" argument.

    Args:
        mock_object: mock.Mock, a mock object with a recorded list of calls.
        calls: list, a list of mock.call objects

    Raises:
        AssertionError: When any single expected call object is missing from
            the recorded calls in the mock.
      AssertionError: When the expected calls are not in the expected order in
            the recorded calls in the mock.
    """
    call_indexes = list()
    recorded_calls = mock_object.mock_calls
    for call in calls:
        try:
            call_indexes.append(recorded_calls.index(call))
        except ValueError:
            raise AssertionError('{} missing from {}'.format(call,
                                                             recorded_calls))
    sorted_call_indexes = copy.copy(call_indexes)
    sorted_call_indexes.sort()
    if call_indexes != sorted_call_indexes:
        raise AssertionError(
            '{} are not in the expected order within {}.'.format(
                calls, recorded_calls))
