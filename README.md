# This is seriously forked
This repo is forked from the [AmericanResearchInstitute/ari-backup](https://github.com/AmericanResearchInstitute/ari-backup)
repo, but it should be considered the canonical repo for ari-backup.
ARI open-sourced the original codebase long ago and went out of business soon
thereafter. There will not likely be any further development on this project
under the [AmericanResearchInstitute organization](https://github.com/AmericanResearchInstitute)
but development on ari-backup within this repo is still active and ongoing.
For more ari-backup history, see the last section in this README.

# ari-backup

ari-backup is a lightweight generic workflow engine designed specifically
for running automated backups. It includes modules with support for running
backups using [rdiff-backup](http://www.nongnu.org/rdiff-backup/), rdiff-backup
with LVM snapshots, and syncing files to [ZFS](http://en.wikipedia.org/wiki/ZFS)
datasets using rsync. Features include:
* Centralzed configuration
* Support for backing up local and remote hosts
* Configurable job parallelization
* Ability to run arbitrary commands locally or remotely before and/or after backup jobs (something especially handy for preparing databases pre-backup)
* Logging to syslog

ari-backup was originally written to automate rdiff-backup jobs. That's been
its main focus; but overtime it became interesting to add support for other
backup types. The architecture of the workflow engine is designed to be easily
extended so that adding new backup types can be done easily.

This application is lightweight thanks mostly to leveraging common system
tools to provide most of the facility necessary to run a backup system.
[cron]([http://en.wikipedia.org/wiki/Cron) is used to schedule the backup jobs,
[xargs](http://en.wikipedia.org/wiki/Xargs) is used to optionally run jobs in
parallel, [run-parts](http://man.cx/run-parts(8)) is used to execute individual
backup jobs, and [ssh](http://en.wikipedia.org/wiki/Secure_shell) is used for
authentication and secure data transport.

## Audience

This README and the ari-backup documentation expect that the reader has a
basic understanding of Linux, file system semantics, how to install a system
package, and how to install a Python package. The typical audience for this
software is the system administrator that wants to backup several systems with
rdiff-backup.

ari-backup was developed on and written for Linux. But there have been reports
of its use on Windows using [cygwin](http://www.cygwin.com/).

## Getting Started

Before you install ari-backup, you should install the following packages from
your Linux distribution.
* [python-gflags](https://pypi.python.org/pypi/python-gflags/)
* [PyYAML](https://pypi.python.org/pypi/PyYAML)
* [rdiff-backup](http://www.nongnu.org/rdiff-backup/)

ari-backup requires [PyYAML](http://pyyaml.org/) which is not a pure Python
library, so you may prefer providing that dependency with a system package
(python-yaml on Debian/Ubuntu).

To install the ari\_backup package to your system, run this as `root`:
```
pip install git+git://github.com/jpwoodbu/ari-backup.git
```

Before you can execute a backup job, there are a few files and directories that
need to be setup. At this time, the configuration file for ari-backup is always
read from `/etc/ari-backup/ari-backup.conf.yaml`. For this demo put this into
the `ari-backup.conf.yaml` file:
```
backup_store_path: /backup-store
```
Now create the `/backup-store` directory.

Our demo will use the most basic example of a backup job. Our backup job will
backup our `/music` directory to `/backup-store/my_backup`. Put the following
into a file named `ari-backup-local-demo`:
```
#!/usr/bin/env python
import ari_backup

backup = ari_backup.RdiffBackup(label='my_backup', source_hostname='localhost')
backup.include_dir('/music')
backup.run()
```

Make sure you're logged in as a user with permission to read the
`/etc/ari-backup/ari-backup.conf.yaml` file. Make `ari-backup-local-demo`
executable and run it with some debug flags.
```
$ ./ari-backup-local-demo --debug --dry_run
```
The ouputput should look something like this:
```
ari_backup (my_backup) [INFO] workflow.py:392 Running in dry_run mode.
ari_backup (my_backup) [INFO] workflow.py:393 started                          
ari_backup (my_backup) [INFO] workflow.py:254 processing pre-job hooks...      
ari_backup (my_backup) [INFO] workflow.py:396 data backup started...           
ari_backup (my_backup) [DEBUG] rdiff_backup_wrapper.py:152 _run_custom_workflow started
ari_backup (my_backup) [DEBUG] workflow.py:321 run_command ['/usr/bin/rdiff-backup', '--exclude-device-files', '--exclude-fifos', '--exclude-sockets', '--terminal-verbosity', '1', '--include', '/music', '--exclude', '**', '/', '/srv/backup-store/my_backup']
ari_backup (my_backup) [DEBUG] rdiff_backup_wrapper.py:205 _run_backup completed
ari_backup (my_backup) [INFO] workflow.py:398 data backup complete
ari_backup (my_backup) [INFO] workflow.py:283 processing post-job hooks...     
ari_backup (my_backup) [INFO] workflow.py:411 stopped
```
You'll notice similar output in your syslog as all ari_backup are logged there
too. For all the available flags to ari_backup job files use the --help flag.
```
$ ./ari-backup-local-demo --help
```

Now let's run the demo for real. Make sure the user you're logged in as also
has permission to read the `/music` directory and has permission to write to
the `/backup-store/my_backup` directory. If all goes well, you should see no
output to the console but you can find logging in your syslog.

Your `/backup-store` directory should now have a `my_backup` directory.
And inside that directory you should see a mirror of your `/music/` directory
as well as a `rdiff-backup-data` directory. The `rdiff-backup-data` is where
rdiff-backup stores its own data like the reverse increments, statistics, and
file metadata.

### Backing up Remote Hosts

For a more exciting demo, let's backup a remote host. We'll be using ssh to
authenticate to the remote host and public key authentication is the only
method supported by ari-backup. Be sure to have your keys setup for both the
user that will run ari-backup and the user that we'll use to connect to the
remote host. For this demo, we're going to use the user `backups`.

The remote system requires very little setup. Once you've got your SSH key
installed, the only other step is to install rdiff-backup. ari-backup does not
need to be installed on the remote system. Isn't that great!

Make sure that the user that's running your backup script has the remote host's
host key in its known_hosts file. The best way to ensure that it is, is to test
your public key authentication works by logging in to the remote system
manually.

We'll need to add the remote_user setting to our
`/etc/ari-backup/ari-backup.conf.yaml` file. It should now look like:
```
backup_store_path: /backup-store
remote_user: backups
```

Let's assume that your remote host is named kif. Make a new backup job file
named `ari-backup-remote-demo` with this content:
```
#!/usr/bin/env python
import ari_backup

backup = ari_backup.RdiffBackup(label='kif_backup', source_hostname='kif')
backup.include_dir('/music')
backup.run()
```

Make `ari-backup-remote-demo` executable and run it first with the debug
flags to see what it will be doing.
```
$ ./ari-backup-remote-demo --debug --dry_run
```
If everything looks good, run it without any flags. Again, no output to the
console means everthing worked. Check the syslog and your
`/backup-store/kif_backup` directory to see the results. Once you've got
your ssh keys setup, the only thing different about remote backups is the value
you put in the source_hostname parameter.

## Settings and flags

Once you've got a workable backup script, you can use it to see what command
line flags are available. Using the <i>ari-backup-local-demo</i> we made
before, run this command line:
```
$ ./ari-backup-local-demo --help
```
That will display a list of all available flags, a description for each, their
default value, and in which module they're defined. See
[python-gflags](https://code.google.com/p/python-gflags/) for more on how to
use flags.

The default flags values can be overridden by entries in the
`/etc/ari-backup/ari-backup.conf.yaml` config file, on the command line at
runtime, or by assigning new flag values to the backup object before run() is
called. By convention, flags are assigned as public atttributes of backup
objects.

If, for example, you wanted to override the value of the `remote_user` flag
defined in the `ari_backup.workflow module`, you could define `remote_user` in
the `/etc/ari-backup/ari-backup.conf.yaml` config like so:
```
remote_user: backup_user
```
You can also override it on the command line:
```
$ ./my_backup_script --remote_user backup_user
```
Finally, you can override it within the backup config file:
```
!/usr/bin/env python
import ari_backup
backup = ari_backup.RdiffBackup(label='mybackup', source_hostname='localhost')
backup.include_dir('/home')
backup.remote_user = 'backup_user'
backup.run()
```

## Using ari-backup with cron

See `include/cron/ari-backup` for an example script you can use with cron.
By default, this script will look for backup jobs in
`/etc/ari-backup/jobs.d`. And by default, this script will only execute one
backup job at a time. You can edit the `JOBS_DIR` and `CONCURRENT_JOBS`
variables in the script to tweak those settings to taste.

To put this altogether with an example, let's use the two backup job scripts
you made from before, `ari-backup-local-demo` and `ari-backup-remote-demo`.
Place them into the `/etc/ari-backup/jobs.d` directory. Now copy
`include/cron/ari-backup` to `/etc/cron.daily` (or an equivalent directory on
your system). You can now wait for cron to run the script in
`/etc/cron.daily`, or better yet, execute it yourself to test it out.

You can again look at your syslog to see that the backups ran. But you'll
also notice that when running our cron script you will actually get some
console output as it reports how long the entire selection of jobs took to
run. You may see something like
this:
```
real    3m44.318s
user    0m45.595s
sys     0m8.253s
```

If you have cron setup to email you when there's output like this, then you'll
have a handy (or annoying) email reporting whether your backups ran
successfully each time.

Be sure that the names of your backup job scripts are compatible with what
run-parts expects. See the [run-parts man page](http://man.cx/run-parts(8)) for
more on their filename restrictions.

**Pro tip:** since run-parts will ignore file names with dots, a simple way to
disable a backup job is to prefix a dot to its filename.

## Other modules

### lvm

Let's add LVM into the mix so that we can achieve crash-consistent backups.
This is done using the lvm module.  We'll need to add the
`snapshot_mount_root` and `snapshot_suffix` settings to our existing
`/etc/ari-backup/ari-backup.conf.yaml` file:
```
snapshot_mount_root: /tmp
snapshot_suffix: -ari-backup
```
`snapshot_mount_root` defines where the temporary snapshots are mounted
during the backup (snapshots are automatically removed after the backup is
completed). `snapshot_suffix` determines the suffix of the name of the
snapshot. This is useful when debugging so that it's clear where the snapshot
came from.

Let's assume that your remote host is named db-server. You want rdiff-backup to
remove increments older than one month, so you set
`remove_older_than_timespec='1M'`. You specify the LVM volumes and their
mountpoints on the remote system (you may add more than one LVM volume by
adding multiple `backup.add_volume()` statements). Finally, specify the
directories to be backed up with `backup.include_dir()`.  Make a new backup job
file named `ari-backup-remote-lvm-demo` with this content:
```
#!/usr/bin/env python
import ari_backup

backup = ari_backup.RdiffLVMBackup(
    label='mybackup',
    source_hostname='db-server',
    remove_older_than_timespec='1M'
)

backup.add_volume('vg0/root', '/')
backup.include_dir('/etc')
backup.run()
```

### zfs

The zfs module provides a way to backup hosts to a machine which uses
[ZFS](http://en.wikipedia.org/wiki/ZFS) for its backup-store. Rather than use
rdiff-backup to keep historical datapoints, history is kept in the form of ZFS
snapshots. [rsync](http://en.wikipedia.org/wiki/Rsync) is used to sync files on
the source host to the ZFS-based host.

This module was built for a very specific use case which involved first making
LVM snapshots on the source host before running the backup. Currently, that is
the only use case supported by the zfs module.

An example config using the zfs module:
```
#!/usr/bin/env python
import ari_backup

backup = ari_backup.ZFSLVMBackup(
    label='mybackup',
    source_hostname='db-server',
    rsync_dst='zfs-backup-server:/zpool-0/backups/ari-backup/mybackup',
    zfs_hostname='zfs-backup-server',
    dataset_name='zpool-0/backups/ari-backup/mybackup',
    snapshot_expiration_days=60
)

backup.add_volume('vg0/root', '/')
backup.run()
```
There's a lof of familiar arguments here and a few new ones.
* **rsync_dst:** destination argument passed to the rsync command in *\<hostname\>:\</path/to/backup/dir\>* format.
* **zfs_hostname:** hostname of the machine storing the backups to ZFS. When using ZFSLVMBackup, the backups are not necessarily stored on the machine running ari-backup.
* **dataset_name:** ZFS path to the dataset in *\<pool\>/\<path/to/dataset\>* format.
* **snapshot_expiration_days:** the number of days at which a snapshot expires and will be destroyed. This is similar to the RdiffBackup classes's `remove_older_than_timespec` argument, but in this case the value is simply an integer respresenting a number of days.

Notice that `include_dir()` was not called. Backing up the entire source file
system is implicit. The effect is as if `include_dir('/')` was was called. This
limitation is due to this feature being made specifically to meet the needs of
its author. Contributions to enhance this module are strongly encouraged! :)

## Running commands before or after a backup

Each workflow object has a `run_command` method that can be used to run
commands locally or remotely before or after the backup is run.

Let's say, for example, you want to dump a database to disk before your backup.
We can expand on our previous example using the lvm module.
```
#!/usr/bin/env python
import ari_backup

backup = ari_backup.RdiffLVMBackup(
    label='mybackup',
    source_hostname='db-server',
    remove_older_than_timespec='1M'
)

backup.add_volume('vg0/root', '/')
backup.include_dir('/etc')

# Dump database to disk to get a consistent copy.
backup.run_command(
    'mysqldump --all-databases > /var/backups/mysql.sql', host='db-server')

backup.run()
```
In the above example we're using file redirection to dump the database backup
to a particular path. That's a shell feature; but that's OK because the command
will be run through a shell on the remote host via SSH. When running commands
locally, if you require the command to be run through shell, you **must**
pass the command argument to `run_command` as a string.
```
# This snippet will be run locally in a shell and will successfully create a
# /tmp/delme file with 'test' inside.
backup.run_command('echo test > /tmp/delme', host='localhost')

# run_command() will also accept a list for the command argument, but will not
# run the command through a shell explicitly. However, remote commands are run
# through a shell implicitly because SSH is uses to execute the command.  This
# snippet will silently fail to create the /tmp/delme file.
backup.run_command(['echo', 'test', '>', '/tmp/delme'], host='localhost')
```
In the latter example everything after 'echo' is passed as an argument to echo
and there was no shell to recognize the file redirection token and actually
make the file.

ari-backup internally always passes a list as the command argument to
`run_command()`. This is done for exlicitness. And `run_command()` accepting
commands as lists could also be useful in some backup configurations.  But if
what you're running uses shell features, be sure to pass in your command as a
string.

If running a command locally, you can either pass 'localhost' as the host
argument or leave out the host argument entirely.


## History and Namesake

ari-backup gets its name from the [American Research
Institute](http://americanri.com) where it was originally written in bash. As
[rdiff-backup](http://www.nongnu.org/rdiff-backup/) was our software of choice
to backup our Linux systems, we needed some sort of scripting around running
rdiff-backup on a schedule. We could write a script that performed all our
backups and just place it in */etc/cron.daily*, but that didn't seem scalable
and was especially monolithic since we were backing up about 50 machines.

We liked the idea of seperate backup scripts for each backup job. In our case,
each job was backing up a host. But we didn't want to overcrowd the
`/etc/cron.daily` directory. So we put all our backup scripts in their own
directory and put a single file in `/etc/cron.daily` that called our backups
using [run-parts](http://man.cx/run-parts(8)). We later cooked in the
[xargs http://en.wikipedia.org/wiki/Xargs) part that made it easy to run backup
jobs concurrently.

When we started to add the LVM snapshot features we decided that porting it to
Python was going to make working on this project much easier.

In 2011, ARI graciously open-sourced this software.
