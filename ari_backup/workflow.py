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
from typing import Any, Callable, Optional, Union

import copy
import subprocess
import shlex
import sys
import time
import yaml

from absl import app
from absl import flags

from ari_backup.logger import Logger


SETTINGS_PATH = '/etc/ari-backup/ari-backup.conf.yaml'

FLAGS = flags.FLAGS
flags.DEFINE_boolean('debug', False, 'enable debug logging')
flags.DEFINE_boolean('dry_run', False, 'log actions but do not execute them')
flags.DEFINE_integer('max_retries', 3, 'number of times to retry a command')
flags.DEFINE_integer('retry_interval', 5,
                     'number of seconds between command retries')
flags.DEFINE_string('remote_user', 'root', 'username used for SSH sessions')
flags.DEFINE_string('ssh_path', '/usr/bin/ssh', 'path to ssh binary')
flags.DEFINE_integer('ssh_port', 22, 'SSH destination port')
flags.DEFINE_boolean('stderr_logging', True, 'enable error logging to stderr')


class WorkflowError(Exception):
    """Base error class for this module."""


class CommandNotFound(WorkflowError):
    """Raised when the given binary cannot be found."""


class NonZeroExitCode(WorkflowError):
    """Raises when subprocess returns a non-zero exitcode."""


class CommandRunner:
    """This class is a simple abstration layer to the subprocess module."""

    def run(self, args: list, shell: bool) -> tuple[str, str, int]:
        """Runs a command as a subprocess.

        Args:
            args: command line arguments to be executed.
            shell: whether to run the command within a shell.

        Returns:
            A 3-tuple containing a str with the stdout, a str with the stderr,
            and an int with the return code of the executed process.

        Raises:
            CommandNotFound: when the executable is not found on the file
                system.
        """
        try:
            self._process = subprocess.Popen(
                args, shell=shell, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except IOError:
            raise CommandNotFound('Unable to execute/find {}.'.format(args))

        stdout, stderr = self._process.communicate()
        return stdout.decode(), stderr.decode(), self._process.returncode

    def terminate(self):
        """Sends a SIGTERM to the executed subprocess."""
        # TODO(jpwoodbu) terminate() doesn't block but it would be nice if it
        # did, so we should be polling.
        self._process.terminate()


class BaseWorkflow:
    """Base class with core workflow features."""

    def __init__(self,
                 label: str,
                 settings_path: Optional[str] = SETTINGS_PATH,
                 command_runner: Optional[CommandRunner] = None,
                 argv: list[str] = sys.argv):
        """Configure a workflow object.

        Args:
            label: label for the the backup job.
            settings_path: the path to the global settings file. If not set,
                then loading global settings is skipped.
            command_runner: an instantiated object that provides the
                CommandRunner interface or None. If None, the CommandRunner
                class will be used by default.
            argv: Passed to FLAGS for flags parsing. By default, it's set to
                sys.argv, but can be overridden for testing. When a test runner
                is used, there are many flags passed into the interpreter which
                are invalid according to absl flags.
        """
        self._settings_path = settings_path
        # Override default flag values from user provided settings file.
        self._load_settings()
        # Since we're not using app.run(), flags like --help won't work unless
        # we explicitly call define_help_flags() before parsing flags.
        app.define_help_flags()
        # Initialize FLAGS. Normally this is done by the main() function but in
        # the model where the config files are excutable it seems the best
        # place to do this is here in the BaseWorkflow constructor.
        FLAGS(argv)
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
        self._pre_job_hooks: list[tuple[Callable, dict | Callable]] = list()
        self._post_job_hooks: list[tuple[Callable, dict | Callable]] = list()

        # Initialize the command runner object.
        self._command_runner = command_runner or CommandRunner()

    def _get_settings_from_file(self) -> dict:
        """Returns settings stored as YAML in the configuration file as a dict.
        """
        settings: dict[str, Any] = dict()
        if self._settings_path is None:
            return settings
        try:
            with open(self._settings_path, 'r') as settings_file:
                settings = yaml.safe_load(settings_file)
        except IOError:
            # We can't log anything yet because self.logger isn't set up yet.
            print('Unable to load {} file. Continuing with default '
                  'settings.'.format(self._settings_path))
        finally:
            return settings

    def _load_settings(self) -> None:
        """Loads user-defined settings."""
        settings = self._get_settings_from_file()
        for setting, value in settings.items():
            try:
                FLAGS.set_default(setting, value)
            except AttributeError as e:
                # We can't log anything yet because self.logger isn't set up
                # yet.
                print('WARNING: Skipping unknown setting in {}: {}'.format(
                      SETTINGS_PATH, e))

    def add_pre_hook(
            self, function: Callable, kwargs: Optional[dict] = None) -> None:
        """Adds a funtion to the list of hooks run before the main workflow.

        Args:
            function: called when hook is run.
            kwargs: key word arguments to pass to function.
        """
        if kwargs is None:
            kwargs = dict()
        self._pre_job_hooks.append((function, kwargs))

    def insert_pre_hook(
            self,
            index: int,
            function: Callable,
            kwargs: Optional[dict | Callable] = None) -> None:
        """Inserts a funtion to the list of hooks run before the main workflow.

        Inserting is most useful if you want to ensure that your hook runs
        first in the list. To do so, pass 0 as the value of index. You can
        technically insert a hook at any position, but it can be difficult to
        know what other hooks have been inserted by the workflow class being
        used.

        Args:
            index: the positional index at which the hook will be inserted.
            function: called when hook is run.
            kwargs: key word arguments to pass to function or a callable which
               returns them for late evaluation.
        """
        if kwargs is None:
            kwargs = dict()
        self._pre_job_hooks.insert(index, (function, kwargs))

    def delete_pre_hook(self, index: int) -> None:
        """Removes, by index number, a hook run before the main workflow.

        Args:
            index: the positional index at which the hook will be deleted.
        """
        self._pre_job_hooks.pop(index)

    def add_post_hook(
            self,
            function: Callable,
            kwargs: Optional[dict | Callable] = None) -> None:
        """Adds a funtion to the list of hooks run after the main workflow.

        Args:
            function: called when hook is run.
            kwargs: key word arguments to pass to function.
        """
        if kwargs is None:
            kwargs = dict()
        self._post_job_hooks.append((function, kwargs))

    def insert_post_hook(
            self,
            index: int,
            function: Callable,
            kwargs: Optional[dict] = None) -> None:
        """Inserts a funtion to the list of hooks run after the main workflow.

        Inserting is most useful if you want to ensure that your hook runs
        first in the list. To do so, pass 0 as the value of index. You can
        technically insert a hook at any position, but it can be difficult to
        know what other hooks have been inserted by the workflow class being
        used.

        Args:
            index: the positional index at which the hook will be inserted.
            function: called when hook is run.
            kwargs: key word arguments to pass to function.
        """
        if kwargs is None:
            kwargs = dict()
        self._post_job_hooks.insert(index, (function, kwargs))

    def delete_post_hook(self, index: int) -> None:
        """Removes, by index number, a hook run after the main workflow.

        Args:
            index: the positional index at which the hook will be deleted.
        """
        self._post_job_hooks.pop(index)

    def _process_pre_job_hooks(self) -> None:
        """Executes pre-job hook functions."""
        self.logger.info('Processing pre-job hooks...')
        for task in self._pre_job_hooks:
            hook = task[0]
            kwargs = task[1]
            # Support callbacks for late evaluation of kwargs in hooks.
            if callable(kwargs):
                kwargs = kwargs()
            hook(**kwargs)

    def _process_post_job_hooks(
            self, error_case: Optional[bool] = None) -> None:
        """Executes post-job hook functions.

        This method works almost identically to _process_pre_job_hooks(), with
        the additional functionality of handling error cases, usually used to
        perform a cleanup operation (e.g. deleting a snapshot).

        Each post-job function must accept a boolean error_case argument.
        However, it is entrirely up to the post-job function to decide what
        behavior to change when error_case is True. For example, if the
        post-job function deletes old backups it may want to skip that
        operation when error_case is True to avoid reducing the number of
        recovery points in the backup history.

        Args:
            error_case: whether an error has occurred during the backup.
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

    def run_command(
            self,
            command: Optional[Union[str, list]],
            host: str = 'localhost') -> tuple[str, str]:
        """Runs an arbitrary command on a given host.

        Given a command line, attempt to execute it on the host named in the
        host argument via SSH, or locally if host is "localhost".

        Remote commands are always run through a shell on the remote host.
        Local commands will be run through a shell only when the command arg is
        a string. This is partly due to the subprocess.Popen interface
        recommending passing it args as a string when running a new process
        within a shell.

        Args:
            command: a command line or list of command line arguments to run.
            host: the host on which the command will be executed.

        Returns:
            A 2-tuple containing the stdout and stderr from the executed
            process.

        Raises:
            TypeError: when command arg is not a str or a list.
            CommandNotFound: when the executable is not found on the file
                system.
            NonZeroExitCode: when the executable returns a non-zero exit code.
        """
        # Let's avoid mutating the user provided command as it may be a mutable
        # type.
        args = copy.copy(command)
        if isinstance(command, str):
            shell = True
            # For remote commands, we want args as a list so it's easier to
            # prepend the SSH command to it.
            if host != 'localhost':
                args = shlex.split(command)
        elif isinstance(command, list):
            shell = False
        else:
            raise TypeError(
                'run_command: command arg must be of type str or list.')

        # Add SSH arguments if this is a remote command.
        if host != 'localhost':
            shell = False
            ssh_args = shlex.split('{ssh} -p {port} {user}@{host}'.format(
                ssh=self.ssh_path, port=self.ssh_port, user=self.remote_user,
                host=host))
            args = ssh_args + args  # type: ignore

        self.logger.debug('run_command %r' % args)
        stdout = str()
        stderr = str()
        exitcode = 0
        if not self.dry_run:
            # We really want to block until our subprocess exists or
            # KeyboardInterrupt. If we don't, clean-up tasks will likely fail.
            try:
                stdout, stderr, exitcode = self._command_runner.run(
                    args, shell)  # type: ignore
            except KeyboardInterrupt:
                # Let's try to stop our subprocess if the user issues a
                # KeyboardInterrupt.
                self._command_runner.terminate()
                # We should re-raise this exception so our caller knows the
                # user wants to stop the workflow.
                raise

        if exitcode > 0:
            error_message = ('[{host}] A command terminated with errors and '
                             'likely requires intervention. '
                             'The command attempted was: {command}.').format(
                                 host=host, command=' '.join(command))

            # Since this is an error, let's make sure the error message gets
            # written at the error log level so that the user can find it
            # without too much digging.
            if stdout:
                self.logger.error(stdout)
            if stderr:
                self.logger.error(stderr)

            raise NonZeroExitCode(error_message)

        if stdout:
            self.logger.debug(stdout)
        if stderr:
            # Warning level should be fine here since we're also looking at
            # the exitcode.
            self.logger.warning(stderr)

        return stdout, stderr

    def run_command_with_retries(self, command, host='localhost',
                                 try_number=1):
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
        except Exception as e:
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
