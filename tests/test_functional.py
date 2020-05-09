import os
import re
import subprocess
from pathlib import Path

def chdir(path):
    # Fighting old pythons...
    os.chdir(str(path))

LEAN_VERSION_RE = re.compile(r'.*lean_version = "(3.[5-9][^"]*).*"', re.DOTALL)

MATHLIB_REV_RE = re.compile(r".*mathlib.* = 'rev': '([^']*)'.*", re.DOTALL)

def fix_leanpkg_bug():
    """Fix the leanpkg toolchain bug in current folder."""
    leanpkg = Path('leanpkg.toml')
    conf = leanpkg.read_text()
    m = LEAN_VERSION_RE.match(conf)
    if m:
        ver = m.group(1)
        leanpkg.write_text(conf.replace(ver, 'leanprover-community/lean:'+ver))

# The next helper is currently unused, but could be used in later tests.
def change_mathlib_rev(rev):
    """Change the mathlib SHA in current folder."""
    leanpkg = Path('leanpkg.toml')
    conf = leanpkg.read_text()
    m = MATHLIB_REV_RE.match(conf)
    if m:
        old_rev = m.group(1)
        leanpkg.write_text(conf.replace(old_rev, rev))

def test_new(tmpdir):
    """Create a new package and check mathlib oleans are there."""
    chdir(tmpdir)
    subprocess.run(['leanproject', 'new'])
    assert (tmpdir/'leanpkg.path').exists()
    assert (tmpdir/'_target'/'deps'/'mathlib'/'src'/'algebra'/'default.olean').exists()

def test_add(tmpdir):
    """Add mathlib to a project and check mathlib oleans are there."""
    chdir(tmpdir)
    subprocess.run(['leanpkg', 'init', 'project'])
    fix_leanpkg_bug()
    subprocess.run(['leanproject', 'add-mathlib'])
    assert (tmpdir/'_target'/'deps'/'mathlib'/'src'/'algebra'/'default.olean').exists()

def test_upgrade_project(tmpdir):
    chdir(tmpdir)
    subprocess.run(['leanpkg', 'init', 'project'])
    fix_leanpkg_bug()
    leanpkg = Path('leanpkg.toml')
    leanpkg.write_text(leanpkg.read_text() +
            'mathlib = {git = "https://github.com/leanprover-community/mathlib",'
            'rev = "a9ed54ca0329771deab21d7574d7d19b417bf4a3"}')
    subprocess.run(['leanproject', 'upgrade-mathlib'])
    assert (tmpdir/'_target'/'deps'/'mathlib'/'src'/'algebra'/'default.olean').exists()

def test_upgrade_mathlib(tmpdir):
    chdir(tmpdir)
    subprocess.run(['git', 'clone', 'https://github.com/leanprover-community/mathlib'])
    chdir(tmpdir/'mathlib')
    subprocess.run(['git', 'checkout', 'lean-3.5.1'])
    subprocess.run(['git', 'reset', '--hard', 'a9ed54ca0329771deab21d7574d7d19b417bf4a3'])
    subprocess.run(['leanproject', 'upgrade-mathlib'])
    assert (tmpdir/'mathlib'/'src'/'algebra'/'default.olean').exists()

def test_get_tutorials(tmpdir):
    chdir(tmpdir)
    subprocess.run(['leanproject', 'get', 'tutorials'])
    assert (tmpdir/'tutorials'/'src').exists()
    assert (tmpdir/'tutorials'/'_target'/'deps'/'mathlib'/'src'/'algebra'/'default.olean').exists()
