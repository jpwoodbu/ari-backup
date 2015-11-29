"""This module provides core workflow management features.

In this module are facilites for centrally managing a large set of arbitrary
jobs. Job management is built around common tools like cron, run-parts, and
xargs. The base features include:
* centralzed configuration
* configurable job parallelization
* ability to run arbitrary commands locally or remotely before and/or after
  jobs
* logging to syslog
"""
import copy
import subprocess
import shlex
import sys
import time
import yaml

import gflags

from logger import Logger


SETTINGS_PATH = '/etc/ari-backup/ari-backup.conf.yaml'

FLAGS = gflags.FLAGS
gflags.DEFINE_boolean('debug', False, 'enable debug logging')
gflags.DEFINE_boolean('dry_run', False, 'log actions but do not execute them')
gflags.DEFINE_integer('max_retries', 3, 'number of times to retry a command')
gflags.DEFINE_integer('retry_interval', 5,
                      'number of seconds between command retries')
gflags.DEFINE_string('remote_user', 'root', 'username used for SSH sessions')
gflags.DEFINE_string('ssh_path', '/usr/bin/ssh', 'path to ssh binary')
gflags.DEFINE_integer('ssh_port', 22, 'SSH destination port')
gflags.DEFINE_boolean('stderr_logging', True, 'enable error logging to stderr')


class WorkflowError(Exception):
  """Base error class for this module."""


class CommandNotFound(WorkflowError):
  """Raised when the given binary cannot be found."""


class NonZeroExitCode(WorkflowError):
  """Raises when subprocess returns a non-zero exitcode."""


class CommandRunner(object):
  """This class is a simple abstration layer to the subprocess module."""

  def run(self, args, shell):
    """Runs a command as a subprocess.

    Args:
      args: list, command line arguments to be executed.
      shell: bool, whether to run the command within a shell.

    Returns:
      A 3-tuple containing a str with the stdout, a str with the stderr, and an
      int with the return code of the executed process.

    Raises:
      CommandNotFound: when the executable is not found on the file system.
    """
    try:
      self._process = subprocess.Popen(args, shell=shell,
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
    except IOError:
      raise CommandNotFound('Unable to execute/find {}.'.format(args))

    stdout, stderr = self._process.communicate()
    return stdout, stderr, self._process.returncode

  def terminate(self):
    """Sends a SIGTERM to the executed subprocess."""
    # TODO(jpwoodbu) terminate() doesn't block but it would be nice if it did,
    # so we should be polling.
    self._process.terminate()


class BaseWorkflow(object):
  """Base class with core workflow features."""

  def __init__(self, label, settings_path=SETTINGS_PATH, command_runner=None):
    """Configure a workflow object.

    Args:
      label: str, label for the the backup job.
      settings_path: str or None, the path to the global settings file. If
        None, then loading global settings is skipped.
      command_runner: CommandRunner, an instantiated object that provides the
        CommandRunner interface or None. If None, the CommandRunner class will
        be used by default. 
    """
    self._settings_path = settings_path
    # Override default flag values from user provided settings file.
    self._load_settings()
    # Initialize FLAGS. Normally this is done by the main() function but in the 
    # model where the config files are excutable it seems the best place to do
    # this is here in the BaseWorkflow constructor.
    FLAGS(sys.argv)
    # Setup logging.
    self.logger = Logger('ari_backup ({label})'.format(label=label),
        FLAGS.debug, FLAGS.stderr_logging)
    self.label = label

    # Assign flags to instance vars so they might be easily overridden in
    # workflow configs.
    self.dry_run = FLAGS.dry_run
    self.max_retries = FLAGS.max_retries
    self.remote_user = FLAGS.remote_user
    self.retry_interval = FLAGS.retry_interval
    self.ssh_path = FLAGS.ssh_path
    self.ssh_port = FLAGS.ssh_port

    # Initialize hook lists.
    self._pre_job_hooks = list()
    self._post_job_hooks = list()

    # Initialize the command runner object.
    if command_runner is None:
      self._command_runner = CommandRunner()
    else:
      self._command_runner = command_runner
      
  # Maintain backward compatibility with old hooks interface.
  @property
  def pre_job_hook_list(self):
    self.logger.warning(
        'pre_job_hook_list is deprecated. Please use add_pre_hook(), '
        'insert_pre_hook(), and delete_pre_hook() instead.')
    return self._pre_job_hooks

  @pre_job_hook_list.setter
  def pre_job_hook_list(self, value):
    self.logger.warning(
        'pre_job_hook_list is deprecated. Please use add_pre_hook(), '
        'insert_pre_hook(), and delete_pre_hook() instead.')
    self._pre_job_hooks = value

  @property
  def post_job_hook_list(self):
    self.logger.warning(
        'post_job_hook_list is depostcated. Please use add_post_hook(), '
        'insert_post_hook(), and delete_post_hook() instead.')
    return self._post_job_hooks

  @post_job_hook_list.setter
  def post_job_hook_list(self, value):
    self.logger.warning(
        'post_job_hook_list is depostcated. Please use add_post_hook(), '
        'insert_post_hook(), and delete_post_hook() instead.')
    self._post_job_hooks = value

  def _get_settings_from_file(self):
    """Returns settings stored as YAML in the configuration file as a dict."""
    settings = dict()
    if self._settings_path is None:
      return settings
    try:
      with open(self._settings_path, 'r') as settings_file:
        settings = yaml.load(settings_file)
    except IOError:
      # We can't log anything yet because self.logger isn't set up yet.
      print ('Unable to load {} file. Continuing with default '
             'settings.'.format(self._settings_path))
    finally:
      return settings

  def _load_settings(self):
    """Loads user-defined settings."""
    settings = self._get_settings_from_file()
    for setting, value in settings.iteritems():
      try:
        FLAGS.SetDefault(setting, value)
      except AttributeError as e:
        # We can't log anything yet because self.logger isn't set up yet.
        print('WARNING: Skipping unknown setting in {}: {}'.format(
              SETTINGS_PATH, e))

  def add_pre_hook(self, function, kwargs=None):
    """Adds a funtion to the list of hooks run before the main workflow.

    Args:
      function: callable, called when hook is run.
      kwargs: dict or None, key word arguments to pass to function. Default is
        None. If None, an empty dict is used.
    """
    if kwargs is None:
      kwargs = dict()
    self._pre_job_hooks.append((function, kwargs))

  def insert_pre_hook(self, index, function, kwargs=None):
    """Inserts a funtion to the list of hooks run before the main workflow.

    Inserting is most useful if you want to ensure that your hook runs first in
    the list. To do so, pass 0 as the value of index. You can technically
    insert a hook at any position, but it can be difficult to know what other
    hooks have been inserted by the workflow class being used.

    Args:
      index: int, the positional index at which the hook will be inserted.
      function: callable, called when hook is run.
      kwargs: dict or None, key word arguments to pass to function. Default is
        None. If None, an empty dict is used.
    """
    if kwargs is None:
      kwargs = dict()
    self._pre_job_hooks.insert(index, (function, kwargs))

  def delete_pre_hook(self, index):
    """Removes, by index number, a hook run before the main workflow.

    Args:
      index: int, the positional index at which the hook will be deleted.
    """
    self._pre_job_hooks.pop(index)

  def add_post_hook(self, function, kwargs=None):
    """Adds a funtion to the list of hooks run after the main workflow.

    Args:
      function: callable, called when hook is run.
      kwargs: dict or None, key word arguments to pass to function. Default is
        None. If None, an empty dict is used.
    """
    if kwargs is None:
      kwargs = dict()
    self._post_job_hooks.append((function, kwargs))


  def insert_post_hook(self, index, function, kwargs=None):
    """Inserts a funtion to the list of hooks run after the main workflow.

    Inserting is most useful if you want to ensure that your hook runs first in
    the list. To do so, pass 0 as the value of index. You can technically
    insert a hook at any position, but it can be difficult to know what other
    hooks have been inserted by the workflow class being used.

    Args:
      index: int, the positional index at which the hook will be inserted.
      function: callable, called when hook is run.
      kwargs: dict or None, key word arguments to pass to function. Default is
        None. If None, an empty dict is used.
    """
    if kwargs is None:
      kwargs = dict()
    self._post_job_hooks.insert(index, (function, kwargs))

  def delete_post_hook(self, index):
    """Removes, by index number, a hook run after the main workflow.

    Args:
      index: int, the positional index at which the hook will be deleted.
    """
    self._post_job_hooks.pop(index)

  def _process_pre_job_hooks(self):
    """Executes pre-job hook functions.""" 
    self.logger.info('Processing pre-job hooks...')
    for task in self._pre_job_hooks:
      hook = task[0]
      kwargs = task[1]
      # Support callbacks for late evaluation of kwargs in hooks.
      if callable(kwargs):
        kwargs = kwargs()
      hook(**kwargs)

  def _process_post_job_hooks(self, error_case):
    """Executes post-job hook functions.

    This method works almost identically to _process_pre_job_hooks(), with
    the additional functionality of handling error cases, usually used to
    perform a cleanup operation (e.g. deleting a snapshot).

    Each post-job function must accept a boolean error_case argument.
    However, it is entrirely up to the post-job function to decide what
    behavior to change when error_case is True. For example, if the
    post-job function deletes old backups it may want to skip that
    operation when error_case is True to avoid reducing the number of recovery
    points in the backup history.

    Args:
      error_case: bool or None, whether an error has occurred during the
        backup.
    """
    if error_case:
      self.logger.error('Processing post-job hooks for error case...')
    else:
      self.logger.info('Processing post-job hooks...')

    for task in self._post_job_hooks:
      hook = task[0]
      kwargs = task[1]
      # Support callbacks for late evaluation of kwargs in hooks.
      if callable(kwargs):
        kwargs = kwargs()
      kwargs['error_case'] = error_case
      hook(**kwargs)

  def run_command(self, command, host='localhost'):
    """Runs an arbitrary command on a given host.

    Given a command line, attempt to execute it on the host named in the host
    argument via SSH, or locally if host is "localhost".

    Remote commands are always run through a shell on the remote host. Local
    commands will be run through a shell only when the command arg is a string.
    This is partly due to the subprocess.Popen interface recommending passing
    it args as a string when running a new process within a shell.

    Args:
      command: str or list, a command line or list of command line arguments to
        run.
      host: str, the host on which the command will be executed.

    Returns:
      A 2-typle containing the stdout and stderr from the executed process.

    Raises:
      TypeError: when command arg is not a str or a list.
      CommandNotFound: when the executable is not found on the file system.
      NonZeroExitCode: when the executable returns a non-zero exit code.
    """
    # Let's avoid mutating the user provided command as it may be a mutable
    # type.
    args = copy.copy(command)
    if isinstance(command, basestring):
      shell = True
      # For remote commands, we want args as a list so it's easier to prepend
      # the SSH command to it.
      if host != 'localhost':
        args = shlex.split(command)
    elif isinstance(command, list):
      shell = False
    else:
      raise TypeError('run_command: command arg must be of type str or list.')

    # Add SSH arguments if this is a remote command.
    if host != 'localhost':
      shell = False
      ssh_args = shlex.split('{ssh} -p {port} {user}@{host}'.format(
          ssh=self.ssh_path, port=self.ssh_port, user=self.remote_user,
          host=host))
      args = ssh_args + args

    self.logger.debug('run_command %r' % args)
    stdout = str()
    stderr = str()
    exitcode = 0
    if not self.dry_run:
      # We really want to block until our subprocess exists or
      # KeyboardInterrupt. If we don't, clean-up tasks will likely fail.
      try:
        stdout, stderr, exitcode = self._command_runner.run(args, shell)
      except KeyboardInterrupt:
        # Let's try to stop our subprocess if the user issues a
        # KeyboardInterrupt.
        self._command_runner.terminate()
        # We should re-raise this exception so our caller knows the user
        # wants to stop the workflow.
        raise

      if stdout:
        self.logger.debug(stdout)
      if stderr:
        # Warning level should be fine here since we'll also look at
        # the exitcode.
        self.logger.warning(stderr)

    if exitcode > 0:
      error_message = ('[{host}] A command terminated with errors and '
                       'likely requires intervention. '
                       'The command attempted was "{command}".').format(
                           host=host, command=command)
      raise NonZeroExitCode(error_message)

    return stdout, stderr

  def _run_command(self, *args, **kwargs):
    """Alias for run_command() to provide backward compatibility."""
    self.logger.warning(
        '_run_command() is deprecated. Please use run_command().')
    return self.run_command(*args, **kwargs)

  def run_command_with_retries(self, command, host='localhost', try_number=1):
    """Runs a command retrying on failure up to self.max_retries."""
    try:
      return self.run_command(command, host)
    except Exception as e:
      if try_number > self.max_retries:
        raise e
      time.sleep(self.retry_interval)
      return self.run_command_with_retries(command, host, try_number + 1)

  def _run_custom_workflow(self):
    """Override this method to run the desired workflow."""
    raise NotImplementedError

  def run(self):
    """Excutes the complete workflow for a single job.

    The workflow consists of running pre-job hooks in order, calling the
    _run_custom_workflow() method to perform the actual workflow steps,
    followed by running the post-job hooks, also in order. 

    Under healthy operation, the error_case argument passed to all post-job
    functions will be set to False. If Exception or KeyboardInterrupt is
    raised during either the pre-job hook processing or during
    _run_customer_workflow(), then the error_case argument will be set to
    True.

    Returns:
      A bool for whether the job ran successfully or not.
    """
    error_case = False
    self.logger.info('ari-backup started.')
    if self.dry_run:
      self.logger.info('Running in dry_run mode.')
    try:
      self._process_pre_job_hooks()
      self.logger.info('Data backup started.')
      self._run_custom_workflow()
      self.logger.info('Data backup complete.')
    except KeyboardInterrupt:
      error_case = True
      # using error level here so that these messages will
      # print to the console
      self.logger.error('Backup job cancelled by user.')
      self.logger.error("Trying to clean up...")
    except Exception, e:
      error_case = True
      self.logger.error(str(e))
      self.logger.error("Trying to clean up...")
    finally:
      self._process_post_job_hooks(error_case)
      self.logger.info('ari-backup stopped.')
      if error_case:
        return False
      else:
        return True

  def run_backup(self):
    self.logger.warning('run_backup() is deprecated. '
                        'Please use run() instead.')
    self.run()
