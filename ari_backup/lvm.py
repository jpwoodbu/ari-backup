"""LVM based backup workflows and MixIn classes."""
import copy
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

  This class depends on the source_hostname instance variable which should be
  defined by any subclass of workflow.BaseWorkFlow that also uses this mixin.
  """
  def __init__(self, *args, **kwargs):
    super(LVMSourceMixIn, self).__init__(*args, **kwargs)

    # Assign flags to instance vars so they might be easily overridden in
    # workflow configs.
    self.snapshot_mount_root = FLAGS.snapshot_mount_root
    self.snapshot_suffix = FLAGS.snapshot_suffix

    # This is a list of 3-tuples, where each inner 3-tuple expresses the LV to
    # back up, the mount point for that LV, and any mount options necessary.
    # For example: [('hostname/root, '/', 'noatime'),] TODO(jpwoodbu) I wonder
    # if noatime being used all the time makes sense to improve read
    # performance and reduce writes to the snapshots.
    self._logical_volumes = list()

    # Provide backward compatibility for config files using attributes
    # directly.
    self.lv_list = self._logical_volumes

    # A list of dicts with the snapshot paths and where they should be mounted.
    self._lv_snapshots = list()
    # Mount the snapshots in a directory named for this job's label.
    self._snapshot_mount_point_base_path = os.path.join(
        self.snapshot_mount_root, self.label)

    # Set up pre and post job hooks to manage snapshot workflow.
    self.add_pre_hook(self._create_snapshots)
    self.add_pre_hook(self._mount_snapshots)
    self.add_post_hook(self._umount_snapshots)
    self.add_post_hook(self._delete_snapshots)

  def add_volume(self, name, mount_point, mount_options=None):
    """Adds logical volume to list of volumes to be backed up.

    Args:
      name: str, full logical volume path (with volume group) in
        group/volume_name format.
      mount_point: str, path where the volume should be mounted during the
        backup. This is normally the same path where the volume is normally
        mounted. For example, if the volume is normally mounted at /var/www,
        the value passed here should be /var/www if you want this data to be in
        the /var/www directory in the backup.
      mount_options: str or None, mount options to be applied when mounting the
        snapshot. For example, "noatime,ro". Defaults to None which applies no
        mount options.
    """
    volume = (name, mount_point, mount_options)
    self._logical_volumes.append(volume)

  def _create_snapshots(self):
    """Creates snapshots of all the volumns added with add_volume()."""
    self.logger.info('creating LVM snapshots...')
    for volume in self._logical_volumes:
      # TODO(jpwoodbu) This try/except won't ne necessary when the deprecated
      # interface to the self.lv_list is removed.
      try:
        lv_path, src_mount_path, mount_options = volume
      except ValueError:
        lv_path, src_mount_path = volume
        mount_options = None

      vg_name, lv_name = lv_path.split('/')
      new_lv_name = lv_name + self.snapshot_suffix
      mount_path = ('{snapshot_mount_point_base_path}'
                    '{src_mount_path}'.format(
          snapshot_mount_point_base_path=self._snapshot_mount_point_base_path,
          src_mount_path=src_mount_path))

      # TODO(jpwoodbu) Is it really OK to always make a 1GB exception table?
      command = ['lvcreate', '-s', '-L', '1G', lv_path, '-n', new_lv_name]
      self.run_command(command, self.source_hostname)

      self._lv_snapshots.append({
          'lv_path': vg_name + '/' + new_lv_name,
          'mount_path': mount_path,
          'mount_options': mount_options,
          'created': True,
          'mount_point_created': False,
          'mounted': False,
      })

  def _delete_snapshots(self, error_case=None):
    """Deletes tracked snapshots.

    Args:
      error_case: bool or None, whether an error has occurred during the
        backup. Default is None. This method does not use this arg but must
        accept it as part of the post hook API.
    """ 
    self.logger.info('deleting LVM snapshots...')
    for snapshot in self._lv_snapshots:
      if snapshot['created']:
        lv_path = snapshot['lv_path']
        # -f makes lvremove not interactive
        command = ['lvremove', '-f', lv_path]
        self.run_command_with_retries(command, self.source_hostname)
        snapshot['created'] = False

  def _mount_snapshots(self):
    """Creates mountpoints as well as mounts the snapshots.

    If the mountpoint directory already has a file system mounted then we
    raise Exception. Metadata is updated whenever a snapshot is
    successfully mounted so that _umount_snapshots() knows which
    snapshots to try to umount.

    TODO(jpwoodbu) Add mount_options to documentation for backup config files.
    """
    self.logger.info('mounting LVM snapshots...')
    for snapshot in self._lv_snapshots:
      lv_path = snapshot['lv_path']
      device_path = '/dev/' + lv_path
      mount_path = snapshot['mount_path']
      mount_options = snapshot['mount_options']

      # mkdir the mount point
      command = ['mkdir', '-p', mount_path]
      self.run_command(command, self.source_hostname)
      snapshot['mount_point_created'] = True

      # If where we want to mount our LV is already a mount point then
      # let's back out.
      if os.path.ismount(mount_path):
        raise Exception('{mount_path} is already a mount point'.format(
            mount_path=mount_path))

      # mount the LV, possibly with mount options
      if mount_options:
        command = ['mount', '-o', mount_options, device_path, mount_path]
      else:
        command = ['mount', device_path, mount_path]
      self.run_command(command, self.source_hostname)
      snapshot['mounted'] = True

  def _umount_snapshots(self, error_case=None):
    """Umounts mounted snapshots in self._lv_snapshots.

    Args:
      error_case: bool or None, whether an error has occurred during the
        backup. Default is None. This method does not use this arg but must
        accept it as part of the post hook API.
    """ 
    # TODO(jpwoodbu) If the user doesn't put '/' in their _include_dirs,
    # then we'll end up with directories around where the snapshots are mounted
    # that will not get cleaned up. We should probably add functionality to
    # make sure the "label" directory is recursively removed. Check out
    # shutil.rmtree() to help resolve this issue.

    self.logger.info('umounting LVM snapshots...')
    # We need a local copy of the _lv_snapshots list to muck with in this
    # method.
    local_lv_snapshots = copy.copy(self._lv_snapshots)
    # We want to umount these logical volumes in reverse order as this should
    # ensure that we umount the deepest paths first.
    local_lv_snapshots.reverse()
    for snapshot in local_lv_snapshots:
      mount_path = snapshot['mount_path']
      if snapshot['mounted']:
        command = ['umount', mount_path]
        self.run_command_with_retries(command, self.source_hostname)
        snapshot['mounted'] = False
      if snapshot['mount_point_created']:
        command = ['rmdir', mount_path]
        self.run_command_with_retries(command, self.source_hostname)
        snapshot['mount_point_created'] = False


class RdiffLVMBackup(LVMSourceMixIn, rdiff_backup_wrapper.RdiffBackup):
  """Subclass to add LVM snapshot management to RdiffBackup."""

  def __init__(self, *args, **kwargs):
    super(RdiffLVMBackup, self).__init__(*args, **kwargs)

  def _prefix_mount_point_to_paths(self, paths):
    """Prefixes the snapshot_mount_point_base_path to each path in paths.

    Args:
      paths: list, list of strings representing paths for the backup config.

    Returns:
      List of strings with the given paths prefixed with the base path where
      the snapshots are mounted.
    """
    new_paths = list()
    for path in paths:
      new_path = '{snapshot_mount_point_base_path}{path}'.format(
          snapshot_mount_point_base_path=self._snapshot_mount_point_base_path,
          path=path)
      new_paths.append(new_path)
    return new_paths

  def _run_custom_workflow(self):
    """Run backup of LVM snapshots.
        
    This method overrides the base class's _run_custom_workflow() so that we
    can modify the include_dir_list and exclude_dir_list to have the
    _snapshot_mount_point_base_path prefixed to their paths. This allows the
    user to configure what to backup from the perspective of the file system
    on the snapshot itself.
    """
    self.logger.debug('RdiffLVMBackup._run_custom_workflow started')
    # Cook the self._include_dirs and self._exclude_dirs so that the src paths
    # include the mount path for the logical volumes.
    self._include_dirs = self._prefix_mount_point_to_paths(self._include_dirs)
    self._exclude_dirs = self._prefix_mount_point_to_paths(self._exclude_dirs)

    # We don't support include_file_list and exclude_file_list in this class as
    # it would take extra effort and it's not likely to be used.

    # After changing the top-level src dir to where the snapshots are mounted,
    # have the base class perform an rdiff-backup.
    self.top_level_src_dir = self._snapshot_mount_point_base_path
    super(RdiffLVMBackup, self)._run_custom_workflow()

    self.logger.debug('RdiffLVMBackup._run_custom_workflow completed')
