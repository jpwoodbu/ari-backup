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
from __future__ import with_statement
import subprocess
import shlex
import sys
import yaml

import gflags

from logger import Logger


SETTINGS_PATH = '/etc/ari-backup/ari-backup.conf.yaml'

FLAGS = gflags.FLAGS
gflags.DEFINE_boolean('debug', False, 'enable debug logging')
gflags.DEFINE_boolean('dry_run', False, 'log actions but do not execute them')
gflags.DEFINE_integer('max_retries', 3, 'number of times to retry a command')
gflags.DEFINE_string('remote_user', 'root', 'username used for SSH sessions')
gflags.DEFINE_string('ssh_path', '/usr/bin/ssh', 'path to ssh binary')


class WorkflowError(Exception):
  """Base error class for this module."""


class CommandNotFound(WorkflowError):
  """Raised when the given binary cannot be found."""


class NonZeroExitCode(WorkflowError):
  """Raises when subprocess returns a non-zero exitcode."""


class BaseWorkflow(object):
  """Base class with core workflow features."""

  def __init__(self, label):
    """Configure a workflow object.

    args:
    label -- a str to label the backup job 

    """
    # Override default flag values from user provided settings file.
    self._load_settings()
    # Initialize FLAGS. Normally this is done by the main() function but in the 
    # model where the config files are excutable it seems the best place to do
    # this is here in the BaseWorkflow constructor.
    FLAGS(sys.argv)
    # Setup logging.
    # TODO(jpwoodbu) Considering renaming the heading to this logging
    # statement.
    self.logger = Logger('ARIBackup ({label})'.format(label=label),FLAGS.debug)
    self.label = label

    # Assign flags to instance vars so they might be easily overridden in
    # workflow configs.
    self.dry_run = FLAGS.dry_run
    self.max_tries = FLAGS.max_retries
    self.remote_user = FLAGS.remote_user
    self.ssh_path = FLAGS.ssh_path

    # Initialize hook lists.
    self._pre_job_hooks = list()
    self._post_job_hooks = list()

    # Maintain backward compatibility with old hooks interface.
    self.pre_job_hook_list = self._pre_job_hooks
    self.post_job_hook_list = self._post_job_hooks
      
  def _load_settings(self):
    """Loads user-defined settings."""
    settings = dict()
    try:
      with open(SETTINGS_PATH) as settings_file:
        settings = yaml.load(settings_file)
    except IOError:
      print ('Unable to load {} file. Continuing with default '
             'settings.'.format(SETTINGS_PATH))
    for setting, value in settings.iteritems():
      try:
        FLAGS.SetDefault(setting, value)
      except AttributeError:
        pass

  def add_pre_hook(self, function, kwargs=None):
    """Adds a funtion to the list of hooks run before the main workflow.

    args:
    function -- callable to be called when hook is run

    kwargs:
    kwargs -- dictionary of key word arguments to pass to function

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

    args:
    index -- an int for the positional index at which the hook will be inserted
    function -- callable to be called when hook is run

    kwargs:
    kwargs -- dictionary of key word arguments to pass to function

    """
    if kwargs is None:
      kwargs = dict()
    self._pre_job_hooks.insert(index, (function, kwargs))

  def delete_pre_hook(self, index):
    """Removes, by index number, a hook run before the main workflow.

    args:
    index -- an int for the positional index at which the hook resides.

    """
    self._pre_job_hooks.pop(index)


  def add_post_hook(self, function, kwargs=None):
    """Adds a funtion to the list of hooks run after the main workflow.

    args:
    function -- callable to be called when hook is run

    kwargs:
    kwargs -- dictionary of key word arguments to pass to function

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

    args:
    index -- an int for the positional index at which the hook will be inserted
    function -- callable to be called when hook is run

    kwargs:
    kwargs -- dictionary of key word arguments to pass to function

    """
    if kwargs is None:
      kwargs = dict()
    self._post_job_hooks.insert(index, (function, kwargs))

  def delete_post_hook(self, index):
    """Removes, by index number, a hook run after the main workflow.

    args:
    index -- an int for the positional index at which the hook resides.

    """
    self._post_job_hooks.pop(index)

  def _process_pre_job_hooks(self):
    """Executes pre-job hook functions.

    The self.pre_job_hook_list is a list of tuples, each with two
    elements, the first of which is a reference to a hook function, the
    second is a dictionary of keyword arguments to pass to the hook
    function. We loop over this list and call each pre-job hook function
    with its corresponding arguments.

    """ 
    self.logger.info('processing pre-job hooks...')
    for task in self.pre_job_hook_list:
      # Let's do some assignments for readability.
      hook = task[0]
      kwargs = task[1]
      hook(**kwargs)

  def _process_post_job_hooks(self, error_case):
    """Executes post-job hook functions.

    args:
    error_case -- bool indicating if an error occured in pre-job hooks or
        in run()

    This method works almost identically to _process_pre_job_hooks(), with
    the additional functionality of handling error cases, usually used to
    perform a cleanup operation (e.g. deleting a snapshot).

    Each post-job function must accept a boolean error_case argument.
    However, it is entrirely up to the post-job function to decide what
    behavior to change when error_case is True. For example, if the
    post-job function deletes old backups it may want to skip that
    operation when error_case is True to avoid reducing the number of recovery
    points in the backup history.

    """
    if error_case:
      self.logger.error('processing post-job hooks for error case...')
    else:
      self.logger.info('processing post-job hooks...')

    for task in self.post_job_hook_list:
      # Let's do some assignments for readability.
      hook = task[0]
      kwargs = task[1]
      kwargs['error_case'] = error_case
      hook(**kwargs)

  def run_command(self, command, host='localhost'):
    """Runs an arbitrary command on a given host.

    args:
    command -- str or list representing a command line

    kwargs:
    host -- hostname for the host on which the command will be executed

    Given the command argument, which can be either a command line string
    or a list of command line arguments, we attempt to execute it on the
    host named in the host argument via SSH, or locally if host is
    "localhost".

    """
    # make args a list if it's not already so
    if isinstance(command, basestring):
      args = shlex.split(command)
    elif isinstance(command, list):
      args = command
    else:
      raise TypeError('run_command: command arg must be str or list')

    # Add SSH arguments if this is a remote command.
    if host != 'localhost':
      ssh_args = shlex.split('{ssh} {user}@%{host}'.format(
          ssh=self.ssh_path, user=self.remote_user, host=host))
      args = ssh_args + args

    self.logger.debug('run_command %r' % args)
    stdout = str()
    stderr = str()
    exitcode = 0
    if not self.dry_run:
      try:
        p = subprocess.Popen(args, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        # We really want to block until our subprocess exists or
        # KeyboardInterrupt. If we don't, clean-up tasks will likely fail.
        try:
          stdout, stderr = p.communicate()
        except KeyboardInterrupt:
          # Let's try to stop our subprocess if the user issues a
          # KeyboardInterrupt.
          # TODO(jpwoodbu) terminate() doesn't block, so we should be polling.
          p.terminate()
          # We should re-raise this exception so our caller knows the user
          # wants to stop the workflow.
          raise

        if stdout:
          self.logger.debug(stdout)
        if stderr:
          # Warning level should be fine here since we'll also look at
          # the exitcode.
          self.logger.warning(stderr)
        exitcode = p.returncode
      except IOError:
        raise CommandNotFound('Unable to execute/find {}'.format(args))

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
    self.run_command(*args, **kwargs)

  def run_command_with_retries(self, command, host='localhost', try_number=0):
    """Runs a command retrying on failure up to self.max_retries."""
    try:
      self.run_command(command, host)
    except Exception, e:
      if try_number > self.max_retries:
        raise e
      self.run_command_with_retries(command, host, try_number + 1)

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

    """
    error_case = False
    if self.dry_run:
      self.logger.info('Running in dry_run mode.')
    self.logger.info('started')
    try:
      self._process_pre_job_hooks()
      self.logger.info('data backup started...')
      self._run_custom_workflow()
      self.logger.info('data backup complete')
    except KeyboardInterrupt:
      error_case = True
      # using error level here so that these messages will
      # print to the console
      self.logger.error('backup job cancelled by user')
      self.logger.error("let's try to clean up...")
    except Exception, e:
      error_case = True
      self.logger.error(str(e))
      self.logger.error("let's try to clean up...")
    finally:
      self._process_post_job_hooks(error_case)
      self.logger.info('stopped')

  def run_backup(self):
    self.logger.warning('run_backup() is deprecated. '
                        'Please use run() instead.')
    self.run()
