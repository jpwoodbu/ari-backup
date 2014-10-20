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
import subprocess
import shlex

from logger import Logger
import settings


class BaseWorkflow(object):
  """Base class with core workflow features."""

  def __init__(self, label):
    """Configure a workflow object.

    args:
    label -- a str to label the backup job 
    """
    # setup logging
    # TODO(jpwoodbu) Considering renaming the heading to this logging
    # statement.
    self.logger = Logger('ARIBackup ({label})'.format(label=label),
                         settings.debug_logging)

    self.label = label
    self.dry_run = settings.dry_run
    # initialize hook lists
    self.pre_job_hook_list = []
    self.post_job_hook_list = []
      
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
      # Let's do some assignments for readability
      hook = task[0]
      kwargs = task[1]
      hook(**kwargs)

  def _process_post_job_hooks(self, error_case):
    """Executes post-job hook functions.

    args:
    error_case -- bool indicating if an error occured in pre-job hooks or
        in _run_backup()

    This method works almost identically to _process_pre_job_hooks(), with
    the additional functionality of handling error cases, usually used to
    perform a cleanup operation (e.g. deleting a snapshot).

    Each post-job function must accept a boolean error_case argument.
    However, it is entrirely up to the post-job function to decide what
    behavior to change when error_case is True. For example, if the
    post-job function deletes old backups it may want to skip that
    operation when error_case is True to avoid reducing the number of data
    points in the backup history.
    
    """
    if error_case:
      self.logger.error('processing post-job hooks for error case...')
    else:
      self.logger.info('processing post-job hooks...')

    for task in self.post_job_hook_list:
      # Let's do some assignments for readability
      hook = task[0]
      kwargs = task[1]
      kwargs['error_case'] = error_case
      hook(**kwargs)

  def _run_command(self, command, host='localhost'):
    """Runs an arbitrary command on host.

    args:
    command -- str or list representing a command line

    kwargs:
    host -- hostname for the host on which the command will be executed

    Given the command argument, which can be either a command line string
    or a list of command line arguments, we attempt to execute it on the
    host named in the host argument via SSH, or locally if host is
    "localhost".

    TODO(jpwoodbu) Consider writing a custom exception class for this.
    Returns a tuple with (stdout, stderr) if the exitcode is zero,
    otherwise Exception is raised.

    """
    # make args a list if it's not already so
    if isinstance(command, basestring):
      args = shlex.split(command)
    elif isinstance(command, list):
      args = command
    else:
      raise TypeError('_run_command: command arg must be str or list')

    # add SSH arguments if this is a remote command
    if host != 'localhost':
      ssh_args = shlex.split('{ssh} {user}@%{host}'.format(
          ssh=settings.ssh_path, user=self.remote_user, host=host))
      args = ssh_args + args

    self.logger.debug('_run_command %r' % args)
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
        raise Exception('Unable to execute/find {args}'.format(args=args))

      if exitcode > 0:
        error_message = ('[{host}] A command terminated with errors and '
                         'likely requires intervention. '
                         'The command attempted was "{command}".').format(
                             host=host, command=command)
        raise Exception(error_message)

    return (stdout, stderr)

  def _run_command_with_retries(self, command, host='localhost',
                                try_number=0):
    """Runs a command with fixed number of retries.

    With max_retries defined in settings, calls _run_command up to
    max_retries.

    """
    try:
      self._run_command(command, host)
    except Exception, e:
      if try_number > settings.max_retries:
        raise e
      self._run_command_with_retries(command, host, try_number + 1)

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
