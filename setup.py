import errno
import os
import os.path
import platform
import subprocess
import sys

from setuptools import setup, Extension
from setuptools import Distribution as _Distribution
from setuptools.command.build_clib import build_clib as _build_clib
from setuptools.command.build_ext import build_ext as _build_ext


sys.path.append(os.path.abspath(os.path.dirname(__file__)))  # FIXME xxxxx

MAKE = 'gmake' if platform.system() in ['FreeBSD', 'OpenBSD'] else 'make'


def absolute(*paths):
    op = os.path
    return op.realpath(op.abspath(op.join(op.dirname(__file__), *paths)))


def build_flags(library, type_, path):
    """Return separated build flags from pkg-config output"""

    pkg_config_path = [path]
    if 'PKG_CONFIG_PATH' in os.environ:
        pkg_config_path.append(os.environ['PKG_CONFIG_PATH'])
    if 'LIB_DIR' in os.environ:
        pkg_config_path.append(os.environ['LIB_DIR'])
        pkg_config_path.append(os.path.join(os.environ['LIB_DIR'], 'pkgconfig'))

    #options = ['--static', {'I': '--cflags-only-I', 'L': '--libs-only-L', 'l': '--libs-only-l'}[type_]]
    options = ['--shared', ]

    return [
        flag.strip('-{}'.format(type_))
        for flag in subprocess.check_output(
            ['pkg-config'] + options + [library], env=dict(os.environ, PKG_CONFIG_PATH=':'.join(pkg_config_path))
        )
        .decode('UTF-8')
        .split()
    ]


class build_clib(_build_clib):
    def initialize_options(self):
        _build_clib.initialize_options(self)
        self.build_flags = None

    def finalize_options(self):
        _build_clib.finalize_options(self)
        if self.build_flags is None:
            self.build_flags = {'include_dirs': [], 'library_dirs': [], 'define': []}

    def get_source_files(self):
        return [
            os.path.join(root, filename)
            for root, _, filenames in os.walk('libsecp256k1')
            for filename in filenames
        ]

    def build_libraries(self, libraries):
        raise Exception('build_libraries')

    def check_library_list(self, libraries):
        raise Exception('check_library_list')

    def get_library_names(self):
        return build_flags('libsecp256k1', 'l', os.path.abspath(self.build_temp))

    def run(self):
        build_temp = os.path.abspath(self.build_temp)

        try:
            os.makedirs(build_temp)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

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
            os.path.abspath(self.build_clib),
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

        print('Running configure: {}'.format(' '.join(cmd)))  # FIXME xxxxx
        subprocess.check_call(cmd, cwd=build_temp)

        subprocess.check_call([MAKE], cwd=build_temp)
        subprocess.check_call([MAKE, 'install'], cwd=build_temp)

        self.build_flags['include_dirs'].extend(build_flags('libsecp256k1', 'I', build_temp))
        self.build_flags['library_dirs'].extend(build_flags('libsecp256k1', 'L', build_temp))


class build_ext(_build_ext):
    def run(self):
        _build_clib = self.get_finalized_command('build_clib')
        self.include_dirs.append(os.path.join(_build_clib.build_clib, 'include'))
        self.include_dirs.extend(_build_clib.build_flags['include_dirs'])

        self.library_dirs.insert(0, os.path.join(_build_clib.build_clib, 'lib'))
        self.library_dirs.extend(_build_clib.build_flags['library_dirs'])

        self.define = _build_clib.build_flags['define']

        return _build_ext.run(self)


class MyExtension(Extension):

    def __init__(self, name):
        # don't invoke the original build_ext for this special extension
        super().__init__(name, sources=[])


class Distribution(_Distribution):
    def has_c_libraries(self):
        return True


setup(
    distclass=Distribution,
    ext_modules=[MyExtension('libsecp256k1')],
    cmdclass={
        'build_clib': build_clib,
        'build_ext': build_ext,
    },
)
