load("@rules_python//python:defs.bzl", "py_test")

filegroup(
    name = "src_files",
    srcs = glob(["*.py"]),
)

py_test(
    name = "style_test",
    size = "small",
    srcs = ["style_test.py"],
    args = [
        "$(locations :src_files)",
        "$(locations //ari_backup:src_files)",
    ],
    data = [
        ":src_files",
        "//ari_backup:src_files",
    ],
    deps = ["@test_requirements_flake8//:pkg"],
)
