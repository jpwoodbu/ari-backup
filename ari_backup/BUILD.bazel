load("@rules_python//python:defs.bzl", "py_library", "py_test")

py_library(
    name = "logger",
    srcs = ["logger.py"],
)

py_library(
    name = "workflow",
    srcs = ["workflow.py"],
    deps = [
        ":logger",
        "@requirements_pyyaml//:pkg",
    ],
)

py_test(
    name = "workflow_test",
    size = "small",
    srcs = ["workflow_test.py"],
    deps = [
        ":test_lib",
        ":workflow",
        "@requirements_absl_py//:pkg",
    ],
)

py_library(
    name = "rdiff_backup_wrapper",
    srcs = ["rdiff_backup_wrapper.py"],
    deps = [
        ":workflow",
        "@requirements_absl_py//:pkg",
    ],
)

py_test(
    name = "rdiff_backup_wrapper_test",
    size = "small",
    srcs = ["rdiff_backup_wrapper_test.py"],
    deps = [
        ":rdiff_backup_wrapper",
        ":test_lib",
        "@requirements_absl_py//:pkg",
    ],
)

py_library(
    name = "lvm",
    srcs = ["lvm.py"],
    deps = [
        ":rdiff_backup_wrapper",
        "@requirements_absl_py//:pkg",
    ],
)

py_test(
    name = "lvm_test",
    size = "small",
    srcs = ["lvm_test.py"],
    deps = [
        ":lvm",
        ":test_lib",
        ":workflow",
        "@requirements_absl_py//:pkg",
    ],
)

py_library(
    name = "zfs",
    srcs = ["zfs.py"],
    deps = [
        ":lvm",
        ":workflow",
        "@requirements_absl_py//:pkg",
    ],
)

py_test(
    name = "zfs_test",
    size = "small",
    srcs = ["zfs_test.py"],
    deps = [
        ":test_lib",
        ":zfs",
        "@requirements_absl_py//:pkg",
    ],
)

py_library(
    name = "test_lib",
    srcs = ["test_lib.py"],
    deps = ["@requirements_absl_py//:pkg"],
)

filegroup(
    name = "src_files",
    srcs = glob(["*.py"]),
    visibility = ["//:__pkg__"],
)
