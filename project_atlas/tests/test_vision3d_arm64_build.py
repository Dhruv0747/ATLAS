"""PC-only cross-compiler verification. This is NOT an Astra-driver build test."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class CrossCompilerTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('aarch64-linux-gnu-g++'),'ARM64 cross-compiler unavailable')
    def test_actual_arm64_shared_object(self):
        with tempfile.TemporaryDirectory(prefix='atlas-arm64-probe-') as d:
            out=Path(d)/'probe.so'
            subprocess.run(['aarch64-linux-gnu-g++','-shared','-fPIC','-x','c++','-',
                            '-o',str(out)],input='extern "C" int atlas_build_probe(){return 29;}\n',
                           text=True,check=True,capture_output=True)
            header=subprocess.check_output(['aarch64-linux-gnu-readelf','-h',str(out)],text=True)
            self.assertIn('AArch64',header);self.assertIn('ELF64',header)
            self.assertNotIn('X86-64',header)

    def test_toolchain_rejects_implicit_host_libraries(self):
        source=(Path(__file__).resolve().parents[1]/'tools/vision3d/arm64_toolchain.cmake').read_text()
        for kind in ('LIBRARY','INCLUDE','PACKAGE'):
            self.assertIn('CMAKE_FIND_ROOT_PATH_MODE_'+kind+' ONLY',source)
        self.assertIn('ATLAS_ARM64_SYSROOT required',source)
