"""Initialize the ari_backup package."""
import lvm
import rdiff_backup_wrapper
import zfs


# Put the main backup classes in this namespace for convenience.
RdiffBackup = rdiff_backup_wrapper.RdiffBackup
RdiffLVMBackup = lvm.RdiffLVMBackup
ZFSLVMBackup = zfs.ZFSLVMBackup
