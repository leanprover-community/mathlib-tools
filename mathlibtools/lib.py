from pathlib import Path
import logging
import tempfile
import shutil
import tarfile
import signal
import re
import os
import subprocess
from datetime import datetime
from typing import Iterable, Union, List, Tuple
from tempfile import TemporaryDirectory

import requests
from tqdm import tqdm # type: ignore
import toml
from git import Repo, InvalidGitRepositoryError, GitCommandError # type: ignore

from mathlibtools.delayed_interrupt import DelayedInterrupt
from mathlibtools.auth_github import auth_github

log = logging.getLogger("Mathlib tools")
log.setLevel(logging.INFO)
if (log.hasHandlers()):
    log.handlers.clear()
log.addHandler(logging.StreamHandler())


class InvalidLeanProject(Exception):
    pass

class InvalidMathlibProject(Exception):
    """A mathlib project is a Lean project depending on mathlib"""
    pass

class LeanDownloadError(Exception):
    pass

class LeanDirtyRepo(Exception):
    pass

class InvalidLeanVersion(Exception):
    pass

def nightly_url(rev: str) -> str:
    """From a git rev, try to find an asset name and url."""
    g = auth_github()
    repo = g.get_repo("leanprover-community/mathlib-nightly")
    tags = {tag.name: tag.commit.sha for tag in repo.get_tags()}
    try:
        release = next(r for r in repo.get_releases()
                           if r.tag_name.startswith('nightly-') and
                           tags[r.tag_name] == rev)
    except StopIteration:
        raise LeanDownloadError('Error: no nightly archive found')

    try:
        asset = next(x for x in release.get_assets()
                     if x.name.startswith('mathlib-olean-nightly-'))
    except StopIteration:
        raise LeanDownloadError("Error: Release " + release.tag_name + 
               " does not contains a olean archive (this shouldn't happen...)")
    return asset.browser_download_url


DOT_MATHLIB = Path.home()/'.mathlib'
AZURE_URL = 'https://oleanstorage.azureedge.net/mathlib/'

DOT_MATHLIB.mkdir(parents=True, exist_ok=True)
DOWNLOAD_URL_FILE = DOT_MATHLIB/'url'

MATHLIB_URL = 'https://github.com/leanprover-community/mathlib.git'
LEAN_VERSION_RE = re.compile(r'(.*)\t.*refs/heads/lean-(.*)')

VersionTuple = Tuple[int, int, int]

def mathlib_lean_version() -> VersionTuple:
    """Return the latest Lean release supported by mathlib"""
    out = subprocess.run(['git', 'ls-remote', '--heads', MATHLIB_URL],
            stdout=subprocess.PIPE).stdout.decode()
    version = (3, 4, 1)
    for branch in out.split('\n'):
        m = LEAN_VERSION_RE.match(branch)
        if m:
            version = max(version, parse_version(m.group(2)))
    return version

def set_download_url(url: str = AZURE_URL) -> None:
    """Store the download url in .mathlib."""
    DOWNLOAD_URL_FILE.write_text(url)

def get_download_url() -> str:
    """Get the download url from .mathlib."""
    return DOWNLOAD_URL_FILE.read_text().strip('/\n')+'/'

if not DOWNLOAD_URL_FILE.exists():
    set_download_url()

def pack(root: Path, srcs: Iterable[Path], target: Path) -> None:
    """Creates, as target, a tar.bz2 archive containing all paths from src,
    relative to the folder root"""
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    cur_dir = Path.cwd()
    with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
        os.chdir(str(root))
        ar = tarfile.open(str(target), 'w|bz2')
        for src in srcs:
            ar.add(str(src.relative_to(root)))
        ar.close()
    os.chdir(str(cur_dir))

def unpack_archive(fname: Union[str, Path], tgt_dir: Union[str, Path]) -> None:
    """Unpack archive. This is needed for python < 3.7."""
    shutil.unpack_archive(str(fname), str(tgt_dir))


def download(url: str, target: Path) -> None:
    """Download from url into target"""
    log.info('Trying to download {} to {}'.format(url, target))
    try:
        req = requests.get(url, stream=True)
        req.raise_for_status()
    except ConnectionError:
        raise LeanDownloadError("Can't connect to " + url)
    except requests.HTTPError:
        raise LeanDownloadError('Failed to download ' + url)
    total_size = int(req.headers.get('content-length', 0))
    BLOCK_SIZE = 1024
    progress = tqdm(total=total_size, unit='iB', unit_scale=True)
    with target.open('wb') as tgt:
        for data in req.iter_content(BLOCK_SIZE):
            progress.update(len(data))
            tgt.write(data)
    progress.close()
    if total_size != 0 and progress.n != total_size:
        raise LeanDownloadError('Failed to download ' + url)


def get_mathlib_archive(rev: str, url:str = '', force: bool = False) -> Path:
    """Download a mathlib archive for revision rev into .mathlib

    Return the archive Path. Will raise LeanDownloadError if nothing works.
    """

    fname = rev + '.tar.gz'
    path = DOT_MATHLIB/fname
    if not force:
        log.info('Looking for local mathlib oleans')
        if path.exists():
            log.info('Found local mathlib oleans')
            return path
    log.info('Looking for remote mathlib oleans')
    try:
        base_url = url or get_download_url()
        download(base_url+fname, path)
        log.info('Found mathlib oleans at '+base_url)
        return path
    except LeanDownloadError:
        pass
    log.info('Looking for GitHub mathlib oleans')
    download(nightly_url(rev), path)
    log.info('Found GitHub mathlib oleans')
    return path

def parse_version(version: str) -> VersionTuple:
    """Turn a lean version string into a tuple of integers or raise
    InvalidLeanVersion"""
    #Something that could be in a branch name or modern leanpkg.toml
    m = re.match(r'.*lean[-:](.*)\.(.*)\.(.*).*', version)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # The output of `lean -- version`
    m = re.match(r'.*version (.*)\.(.*)\.(.*),.*', version)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # Only a version string
    m = re.match(r'(.*)\.(.*)\.(.*)', version)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    raise InvalidLeanVersion(version)

def lean_version_toml(version: VersionTuple) -> str:
    """Turn a Lean version tuple into the string expected in leanpkg.toml."""
    ver_str = '{:d}.{:d}.{:d}'.format(*version)
    if version < (3, 5, 0):
        return ver_str
    else:
        return 'leanprover-community/lean:' + ver_str
    
def check_core_timestamps(toolchain: str) -> bool:
    """Check that oleans are more recent than their source in core lib"""
    
    toolchain_path = Path.home()/'.elan'/'toolchains'/toolchain
    try:
        return all(p.stat().st_mtime < p.with_suffix('.olean').stat().st_mtime 
               for p in toolchain_path.glob('**/*.lean'))
    except FileNotFoundError:
        return False

def touch_oleans(path: Path) -> None:
    """Set modification time for oleans in path and its subfolders to now"""
    now = datetime.now().timestamp()
    for p in path.glob('**/*.olean'):
        os.utime(str(p), (now, now))

class LeanProject:
    def __init__(self, repo: Repo, is_dirty: bool, rev: str, directory: Path,
            pkg_config: dict, deps: dict,
            cache_url: str = '', force_download: bool = False,
            upgrade_lean: bool = True) -> None:
        """A Lean project."""
        self.repo = repo
        self.is_dirty = is_dirty
        self.rev = rev
        self.directory = directory
        self.pkg_config = pkg_config
        self.deps = deps
        self.cache_url = cache_url or get_download_url()
        self.force_download = force_download
        self.upgrade_lean = upgrade_lean

    @classmethod
    def from_path(cls, path: Path, cache_url: str = '',
                  force_download: bool = False, 
                  upgrade_lean: bool = True) -> 'LeanProject':
        """Builds a LeanProject from a Path object"""
        try:
            repo = Repo(path, search_parent_directories=True)
        except InvalidGitRepositoryError:
            raise InvalidLeanProject('Invalid git repository') 
        if repo.bare:
            raise InvalidLeanProject('Git repository is not initialized')
        is_dirty = repo.is_dirty()
        try:
            rev = repo.commit().hexsha
        except ValueError:
            rev = ''
        directory = Path(repo.working_dir)
        try:
            config = toml.load(directory/'leanpkg.toml')
        except FileNotFoundError:
            raise InvalidLeanProject('Missing leanpkg.toml')

        return cls(repo, is_dirty, rev, directory,
                   config['package'], config['dependencies'],
                   cache_url, force_download, upgrade_lean)
    
    @classmethod
    def user_wide(cls, cache_url: str = '', 
                  force_download: bool = False) -> 'LeanProject':
        """Return the user-wide LeanProject (living in ~/.lean) 

        If the project does not exist, it will be created, using the latest
        version of Lean supported by mathlib."""
        directory = Path.home()/'.lean'
        try:
            config = toml.load(directory/'leanpkg.toml')
        except FileNotFoundError:
            directory.mkdir(exist_ok=True)
            version = mathlib_lean_version()
            if version <= (3, 4, 2):
                version_str = '.'.join(map(str, version))
            else:
                version_str = 'leanprover-community/lean:' +\
                              '.'.join(map(str, version))

            pkg = { 'name': '_user_local_packages', 
                    'version': '1',
                    'lean_version': version_str }
            with (directory/'leanpkg.toml').open('w') as pkgtoml:
                toml.dump({'package': pkg}, pkgtoml)
            config = { 'package': pkg, 'dependencies': dict() }

        return cls(None, False, '', directory,
                   config['package'], config['dependencies'],
                   cache_url, force_download)

    @property
    def name(self) -> str:
        return self.pkg_config['name']
    
    @property
    def lean_version(self) -> VersionTuple:
        return parse_version(self.pkg_config['lean_version'])

    @lean_version.setter
    def lean_version(self, version: VersionTuple) -> None:
        self.pkg_config['lean_version'] = lean_version_toml(version)


    @property
    def is_mathlib(self) -> bool:
        return self.name == 'mathlib'

    @property
    def toolchain(self) -> str:
        ver_str = '{:d}.{:d}.{:d}'.format(*self.lean_version)
        return ver_str if self.lean_version < (3, 5, 0) \
                       else 'leanprover-community-lean-' + ver_str

    @property
    def mathlib_rev(self) -> str:
        if self.is_mathlib:
            return self.rev
        if 'mathlib' not in self.deps:
            raise InvalidMathlibProject('This project does not depend on mathlib')
        try:
            rev = self.deps['mathlib']['rev']
        except KeyError:
            raise InvalidMathlibProject(
                'Project seems to refer to a local copy of mathlib '
                'instead of a GitHub repository')
        return rev

    @property
    def mathlib_folder(self) -> Path:
        if self.is_mathlib:
            return self.directory
        else:
            return self.directory/'_target'/'deps'/'mathlib'

    def read_config(self) -> None:
        try:
            config = toml.load(self.directory/'leanpkg.toml')
        except FileNotFoundError:
            raise InvalidLeanProject('Missing leanpkg.toml')

        self.deps = config['dependencies']
        self.pkg_config = config['package']

    def write_config(self) -> None:
        """Write leanpkg.toml for this project."""
        # Fix leanpkg lean_version bug if needed (the lean_version property
        # setter is working here, hence the weird line).
        self.lean_version = self.lean_version

        # Note we can't blindly use toml.dump because we need dict as values
        # for dependencies.
        with (self.directory/'leanpkg.toml').open('w') as cfg:
            cfg.write('[package]\n')
            cfg.write(toml.dumps(self.pkg_config))
            cfg.write('\n[dependencies]\n')
            for dep, val in self.deps.items():
                nval = str(val).replace("'git':", 'git =').replace(
                        "'rev':", 'rev =').replace("'", '"')
                cfg.write('{} = {}\n'.format(dep, nval))

    def get_mathlib_olean(self) -> None:
        """Get precompiled mathlib oleans for this project."""
        # Just in case the user broke the workflow (for instance git clone
        # mathlib by hand and then run `leanproject get-cache`)
        if not (self.directory/'leanpkg.path').exists():
            self.run(['leanpkg', 'configure'])
        self.mathlib_folder.mkdir(parents=True, exist_ok=True)
        try:
            unpack_archive(get_mathlib_archive(self.mathlib_rev, self.cache_url,
                                           self.force_download), 
                       self.mathlib_folder)
        except (EOFError, shutil.ReadError):
            log.info('Something wrong happened with the olean archive. '
                     'I will now retry downloading.')
            unpack_archive(
                    get_mathlib_archive(self.mathlib_rev, self.cache_url, True), 
                    self.mathlib_folder)
        # Let's now touch oleans, just in case
        touch_oleans(self.mathlib_folder)

    def mk_cache(self, force: bool = False) -> None:
        """Cache oleans for this project."""
        if self.is_dirty and not force:
            raise LeanDirtyRepo
        if not self.rev:
            raise ValueError('This project has no git commit.')
        tgt_folder = DOT_MATHLIB if self.is_mathlib else self.directory/'_cache'
        tgt_folder.mkdir(exist_ok=True)
        archive = tgt_folder/(str(self.rev) + '.tar.bz2')
        if archive.exists() and not force:
            log.info('Cache for revision {} already exists'.format(self.rev))
            return
        pack(self.directory, filter(Path.exists, [self.directory/'src', self.directory/'test']), 
             archive)

    def get_cache(self, force: bool = False, url:str = '') -> None:
        """Tries to get olean cache.

        Will raise LeanDownloadError or FileNotFoundError if no archive exists.
        """
        if self.is_dirty and not force:
            raise LeanDirtyRepo
        if self.is_mathlib:
            self.get_mathlib_olean()
        else:
            unpack_archive(self.directory/'_cache'/(str(self.rev)+'.tar.bz2'),
                           self.directory)

    @classmethod
    def from_git_url(cls, url: str, target: str = '', branch: str = '',
                     cache_url: str = '', 
                     force_download: bool = False) -> 'LeanProject':
        """Download a Lean project using git and prepare mathlib if needed."""
        log.info('Cloning from ' + url)
        target = target or url.split('/')[-1].split('.')[0]
        repo = Repo.clone_from(url, target)
        if branch:
            try:
                repo.remote('origin').fetch(branch)
                repo.git.checkout(branch)
            except (IndexError, GitCommandError) as err:
                log.error('Invalid git branch')
                raise err
        proj = cls.from_path(Path(repo.working_dir), cache_url, force_download)
        proj.run(['leanpkg', 'configure'])
        if 'mathlib' in proj.deps or proj.is_mathlib:
            proj.get_mathlib_olean()
        return proj
    
    @classmethod
    def new(cls, path: Path = Path('.'), cache_url: str = '',
            force_download: bool = False) -> 'LeanProject':
        """Create a new Lean project and prepare mathlib."""
        if path == Path('.'):
            subprocess.run(['leanpkg', 'init', path.absolute().name])
        else:
            subprocess.run(['leanpkg', 'new', str(path)])

        proj = cls.from_path(path, cache_url, force_download)
        proj.lean_version = mathlib_lean_version()
        proj.write_config()
        proj.add_mathlib()
        proj.repo.git.checkout('-b', 'master')
        return proj

    def run(self, args: List[str]) -> None:
        """Run a command in the project directory.
           
           args is a list as in subprocess.run"""
        subprocess.run(args, cwd=str(self.directory))

    def build(self) -> None:
        log.info('Building project '+self.name)
        self.run(['leanpkg', 'build'])

    def upgrade_mathlib(self) -> None:
        """Upgrade mathlib in the project.

        In case this project is mathlib, we assume we are already on the branch
        we want.
        """
        if self.is_mathlib:
            try:
                rem = next(remote for remote in self.repo.remotes 
                           if any('leanprover' in url 
                                  for url in remote.urls))
                rem.pull(self.repo.active_branch)
            except (StopIteration, GitCommandError):
                log.info("Couldn't pull from a relevant git remote. "
                         "You may try to git pull manually and then "
                         "run `leanproject get-cache`")
                return
            self.rev = self.repo.commit().hexsha
        else:
            try:
                shutil.rmtree(str(self.mathlib_folder))
            except FileNotFoundError:
                pass
            if self.upgrade_lean:
                mathlib_lean = mathlib_lean_version()

                if mathlib_lean > self.lean_version:
                    self.lean_version = mathlib_lean
                    self.write_config()
            self.run(['leanpkg', 'upgrade'])
            self.read_config()
        self.get_mathlib_olean()

    def add_mathlib(self) -> None:
        """Add mathlib to the project."""
        if 'mathlib' in self.deps:
            log.info('This project already depends on  mathlib')
            return
        log.info('Adding mathlib')
        if self.upgrade_lean:
            self.lean_version = mathlib_lean_version()
        self.write_config()
        log.info('Adding mathlib')
        self.run(['leanpkg', 'add', 'leanprover-community/mathlib'])
        log.debug('Configuring') 
        self.run(['leanpkg', 'configure'])
        self.read_config()
        self.get_mathlib_olean()

    def setup_git_hooks(self) -> None:
        hook_dir = Path(self.repo.git_dir)/'hooks'
        src = Path(__file__).parent
        print('This script will copy post-commit and post-checkout scripts to ', hook_dir)
        rep = input("Do you want to proceed (y/n)? ")
        if rep in ['y', 'Y']:
            shutil.copy(str(src/'post-commit'), str(hook_dir))
            shutil.copy(str(src/'post-checkout'), str(hook_dir))
            print("Successfully copied scripts")
        else:
                print("Cancelled...")

    def check_timestamps(self) -> Tuple[bool, bool]:
        """Check that core and mathlib oleans are more recent than their
        sources. Return a tuple (core_ok, mathlib_ok)"""
        try:
            mathlib_ok = all(p.stat().st_mtime < p.with_suffix('.olean').stat().st_mtime 
                             for p in (self.mathlib_folder/'src').glob('**/*.lean'))
        except FileNotFoundError:
            mathlib_ok = False

        return (check_core_timestamps(self.toolchain), mathlib_ok)
