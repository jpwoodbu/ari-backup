load("@rules_python//python:defs.bzl", "py_test")
load("@test_requirements//:requirements.bzl", "entry_point")

filegroup(
    name = "src_files",
    srcs = glob(["*.py"]),
)

py_test(
    name = "style_test",
    main = "rules_python_wheel_entry_point_flake8.py",
    srcs = [entry_point("flake8")],
    args = [
      '$(locations :src_files)',
      '$(locations //ari_backup:src_files)'],
    deps = ["@test_requirements_flake8//:pkg"],
    data = [
      ":src_files",
      "//ari_backup:src_files",
    ],
    timeout = "short",
)
