"""Initialize the ari_backup package."""
from ari_backup import lvm
from ari_backup import rdiff_backup_wrapper
from ari_backup import zfs


# Put the main backup classes in this namespace for convenience.
RdiffBackup = rdiff_backup_wrapper.RdiffBackup
RdiffLVMBackup = lvm.RdiffLVMBackup
ZFSLVMBackup = zfs.ZFSLVMBackup
