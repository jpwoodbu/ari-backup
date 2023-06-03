workspace(name = "ari_backup")

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

http_archive(
    name = "rules_python",
    sha256 = "863ba0fa944319f7e3d695711427d9ad80ba92c6edd0b7c7443b84e904689539",
    strip_prefix = "rules_python-0.22.0",
    url = "https://github.com/bazelbuild/rules_python/releases/download/0.22.0/rules_python-0.22.0.tar.gz",
)

load("@rules_python//python:repositories.bzl",
    "py_repositories", "python_register_toolchains")

py_repositories()

python_register_toolchains(
    name = "python3_11",
    python_version = "3.11",
)

load("@python3_11//:defs.bzl", "interpreter")

load("@rules_python//python:pip.bzl", "pip_parse")

# Create a central repo that knows about the dependencies needed from
# requirements_lock.txt.
pip_parse(
   name = "requirements",
   requirements_lock = "//ari_backup:requirements_lock.txt",
   python_interpreter_target = interpreter,
)

# Load the starlark macro which will define your dependencies.
load("@requirements//:requirements.bzl", "install_deps")
# Call it to define repos for your requirements.
install_deps()


# Create a central repo that knows about the dependencies needed from
# test_requirements_lock.txt.
pip_parse(
   name = "test_requirements",
   requirements_lock = "//ari_backup:test_requirements_lock.txt",
   python_interpreter_target = interpreter,
)

# Load the starlark macro which will define your dependencies.
load("@test_requirements//:requirements.bzl", "install_deps")
# Call it to define repos for your requirements.
install_deps()
