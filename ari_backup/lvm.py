"""LVM based backup workflows and MixIn classes."""
import os

import gflags

import rdiff_backup_wrapper
import workflow


FLAGS = gflags.FLAGS
gflags.DEFINE_string('snapshot_mount_root', '/tmp',
    'root path for creating temporary directories for mounting LVM snapshots')
gflags.DEFINE_string('snapshot_suffix', '-ari_backup',
                     'suffix for LVM snapshots')


class LVMSourceMixIn(object):
  """MixIn class to work with LVM based backup sources.

  This class registers pre-job and post-job hooks to create and mount LVM
  snapshots before and after a backup job.

  """
  def __init__(self, *args, **kwargs):
    super(LVMSourceMixIn, self).__init__(*args, **kwargs)

    # Assign flags to instance vars so they might be easily overridden in
    # workflow configs.
    self.snapshot_mount_root = FLAGS.snapshot_mount_root
    self.snapshot_suffix = FLAGS.snapshot_suffix

    # This is a list of 2-tuples, where each inner 2-tuple expresses the LV to
    # back up, the mount point for that LV any mount options necessary. For
    # example: [('hostname/root, '/', 'noatime'),]
    # TODO(jpwoodbu) I wonder if noatime being used all the time makes sense to
    # improve read performance and reduce writes to the snapshots.
    self.lv_list = []

    # A list of dicts with the snapshot paths and where they should be mounted.
    self.lv_snapshots = []
    # Mount the snapshots in a directory named for this job's label.
    self.snapshot_mount_point_base_path = os.path.join(
        self.snapshot_mount_root, self.label)

    # Setup pre and post job hooks to manage snapshot work flow.
    self.pre_job_hook_list.append((self._create_snapshots, {}))
    self.pre_job_hook_list.append((self._mount_snapshots, {}))
    self.post_job_hook_list.append((self._umount_snapshots, {}))
    self.post_job_hook_list.append((self._delete_snapshots, {}))

  def _create_snapshots(self):
    """Creates snapshots of all the volumns listed in self.lv_list."""
    self.logger.info('creating LVM snapshots...')
    for volume in self.lv_list:
      try:
        lv_path, src_mount_path, mount_options = volume
      except ValueError:
        lv_path, src_mount_path = volume
        mount_options = None

      vg_name, lv_name = lv_path.split('/')
      new_lv_name = lv_name + self.snapshot_suffix
      mount_path = ('{snapshot_mount_point_base_path}'
                    '{src_mount_path}'.format(
          snapshot_mount_point_base_path=self.snapshot_mount_point_base_path,
          src_mount_path=src_mount_path))

      # TODO(jpwoodbu) Is it really OK to always make a 1GB exception table?
      command = 'lvcreate -s -L 1G {lv_path} -n {new_lv_name}'.format(
          lv_path=lv_path, new_lv_name=new_lv_name)
      self._run_command(command, self.source_hostname)

      self.lv_snapshots.append({
          'lv_path': vg_name + '/' + new_lv_name,
          'mount_path': mount_path,
          'mount_options': mount_options,
          'created': True,
          'mount_point_created': False,
          'mounted': False,
      })

  def _delete_snapshots(self, error_case=None):
    """Deletes snapshots in self.lv_snapshots.

    kwargs:
    error_case -- bool indicating if we're being called after a failure

    This method behaves the same in the normal and error cases.

    """ 
    self.logger.info('deleting LVM snapshots...')
    for snapshot in self.lv_snapshots:
      if snapshot['created']:
        lv_path = snapshot['lv_path']
        # -f makes lvremove not interactive
        self._run_command_with_retries('lvremove -f {lv_path}'.format(
            lv_path=lv_path), self.source_hostname)
        snapshot['created'] = False

  def _mount_snapshots(self):
    """Creates mountpoints as well as mounts the snapshots.

    If the mountpoint directory already has a file system mounted then we
    raise Exception. Metadata is updated whenever a snapshot is
    successfully mounted so that _umount_snapshots() knows which
    snapshots to try to umount.

    TODO add mount_options to documentation for backup config files

    """
    self.logger.info('mounting LVM snapshots...')
    for snapshot in self.lv_snapshots:
      lv_path = snapshot['lv_path']
      device_path = '/dev/' + lv_path
      mount_path = snapshot['mount_path']
      mount_options = snapshot['mount_options']

      # mkdir the mount point
      self._run_command('mkdir -p %s' % mount_path, self.source_hostname)
      snapshot['mount_point_created'] = True

      # If where we want to mount our LV is already a mount point then
      # let's back out.
      if os.path.ismount(mount_path):
        raise Exception('{mount_path} is already a mount point'.format(
            mount_path=mount_path))

      # mount the LV, possibly with mount options
      if mount_options:
        command = ('mount -o {mount_options} {device_path} '
                   '{mount_path}'.format(
            mount_options=mount_options,
            device_path=device_path,
            mount_path=mount_path))
      else:
        command = 'mount {device_path} {mount_path}'.format(
            device_path=device_path,
            mount_path=mount_path)

      self._run_command(command, self.source_hostname)
      snapshot['mounted'] = True

  def _umount_snapshots(self, error_case=None):
    """Umounts mounted snapshots in self.lv_snapshots.

    kwargs:
    error_case -- bool indicating if we're being called after a failure

    This method behaves the same in the normal and error cases.

    """ 
    # TODO(jpwoodbu) If the user doesn't put '/' in their include_dir_list,
    # then we'll end up with directories around where the snapshots are mounted
    # that will not get cleaned up. We should probably add functionality to
    # make sure the "label" directory is recursively removed. Check out
    # shutil.rmtree() to help resolve this issue.

    self.logger.info('umounting LVM snapshots...')
    # We need a local copy of the lv_snapshots list to muck with in this
    # method.
    local_lv_snapshots = self.lv_snapshots
    # We want to umount these LVs in reverse order as this should ensure that
    # we umount the deepest paths first.
    local_lv_snapshots.reverse()
    for snapshot in local_lv_snapshots:
      mount_path = snapshot['mount_path']
      if snapshot['mounted']:
        self._run_command_with_retries('umount {}'.format(mount_path),
            self.source_hostname)
        snapshot['mounted'] = False
      if snapshot['mount_point_created']:
        self._run_command_with_retries('rmdir {}'.format(mount_path),
            self.source_hostname)
        snapshot['mount_point_created'] = False


class RdiffLVMBackup(LVMSourceMixIn, rdiff_backup_wrapper.RdiffBackup):
  """Subclass to add LVM snapshot management to RdiffBackup."""

  def __init__(self, *args, **kwargs):
    super(RdiffLVMBackup, self).__init__(*args, **kwargs)

  def _run_custom_workflow(self):
    """Run backup of LVM snapshots.
        
    This method overrides the base class's _run_custom_workflow() so that we
    can modify the include_dir_list and exclude_dir_list to have the
    snapshot_mount_point_base_path prefixed to their paths. This allows the
    user to configure what to backup from the perspective of the file system
    on the snapshot itself.

    """
    # TODO(jpwoodbu) Cooking the paths should be done in its own function.
    self.logger.debug('LVMBackup._run_custom_workflow started')

    # Cook the self.include_dir_list and self.exclude_dir_list so that the src
    # paths include the mount path for the LV(s).
    local_include_dir_list = []
    for include_dir in self.include_dir_list:
      include_path = '{snapshot_mount_point_base_path}{include_dir}'.format(
          snapshot_mount_point_base_path=self.snapshot_mount_point_base_path,
          include_dir=include_dir)
      local_include_dir_list.append(include_path)

    local_exclude_dir_list = []
    for exclude_dir in self.exclude_dir_list:
      exclude_path = '{snapshot_mount_point_base_path}{exclude_dir}'.format(
          snapshot_mount_point_base_path=self.snapshot_mount_point_base_path,
          exclude_dir=exclude_dir)
      local_exclude_dir_list.append(exlude_path)

    self.include_dir_list = local_include_dir_list
    self.exclude_dir_list = local_exclude_dir_list

    # We don't support include_file_list and exclude_file_list in this class as
    # it would take extra effort and it's not likely to be used.

    # Have the base class perform an rdiff-backup.
    self.top_level_src_dir = self.snapshot_mount_point_base_path
    super(RdiffLVMBackup, self)._run_custom_workflow()

    self.logger.debug('LVMBackup._run_custom_workflow completed')
