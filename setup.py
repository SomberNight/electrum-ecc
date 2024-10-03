import errno
import os
import os.path
import platform
import shutil
import subprocess

from setuptools import setup
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel  # TODO declare dependence on wheel?
from wheel.bdist_wheel import safer_name


MAKE = 'gmake' if platform.system() in ['FreeBSD', 'OpenBSD'] else 'make'


def absolute(*paths):
    op = os.path
    return op.realpath(op.abspath(op.join(op.dirname(__file__), *paths)))


def compile_secp(build_dir: str) -> None:
    if not os.path.exists(absolute('libsecp256k1')):
        raise Exception("missing git submodule secp256k1")

    if not os.path.exists(absolute('libsecp256k1/configure')):
        # configure script hasn't been generated yet
        autogen = absolute('libsecp256k1/autogen.sh')
        os.chmod(absolute(autogen), 0o755)
        subprocess.check_call([autogen], cwd=absolute('libsecp256k1'))

    for filename in [
        'libsecp256k1/configure',
        'libsecp256k1/build-aux/compile',
        'libsecp256k1/build-aux/config.guess',
        'libsecp256k1/build-aux/config.sub',
        'libsecp256k1/build-aux/depcomp',
        'libsecp256k1/build-aux/install-sh',
        'libsecp256k1/build-aux/missing',
        'libsecp256k1/build-aux/test-driver',
    ]:
        try:
            os.chmod(absolute(filename), 0o755)
        except OSError as e:
            # some of these files might not exist depending on autoconf version
            if e.errno != errno.ENOENT:
                # If the error isn't 'No such file or directory' something
                # else is wrong and we want to know about it
                raise

    cmd = [
        absolute('libsecp256k1/configure'),
        '--enable-shared',
        '--disable-static',
        '--disable-dependency-tracking',
        '--with-pic',
        '--prefix',
        os.path.abspath(build_dir),
        '--enable-module-recovery',
        '--enable-module-extrakeys',
        '--enable-module-schnorrsig',
        '--enable-experimental',
        '--enable-module-ecdh',
        '--enable-benchmark=no',
        '--enable-tests=no',
        '--enable-openssl-tests=no',
        '--enable-exhaustive-tests=no',
    ]

    print('Running configure: {}'.format(' '.join(cmd)))  # FIXME use logger?
    subprocess.check_call(cmd, cwd=build_dir)

    subprocess.check_call([MAKE], cwd=build_dir)
    subprocess.check_call([MAKE, 'install'], cwd=build_dir)


class bdist_wheel(_bdist_wheel):
    def run(self):
        _build_cmd = self.get_finalized_command('build')
        build_dir = os.path.join(_build_cmd.build_base, "temp_libsecp")
        target_dir = os.path.join(self.bdist_dir, safer_name(self.distribution.get_name()))
        for dir_ in (build_dir, target_dir):
            try:
                os.makedirs(dir_)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

        compile_secp(build_dir)

        build_temp_libs = os.path.join(build_dir, "lib")
        for fname in os.listdir(build_temp_libs):
            if (
                    fname.endswith(".so") or fname.endswith(".dll") or fname.endswith(".dylib")
                    or ".so." in fname  # FIXME symlink duplication
            ):
                shutil.copy(os.path.join(build_temp_libs, fname), target_dir)

        _bdist_wheel.run(self)


setup(
    cmdclass={
        'bdist_wheel': bdist_wheel,
    },
)
