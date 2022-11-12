from pathlib import Path
import logging
import tempfile
import shutil
import tarfile
import signal
import re
import os
import stat
import platform
import subprocess
import pickle
import contextlib
import enum
from datetime import datetime
import concurrent.futures
import tarfile
from typing import Iterable, Union, List, Tuple, Optional, Dict, TYPE_CHECKING
from tempfile import TemporaryDirectory
import shutil

import requests
from tqdm import tqdm # type: ignore
import toml
import yaml
from git import (Repo, Commit, InvalidGitRepositoryError,  # type: ignore
                 GitCommandError, BadName, RemoteReference) # type: ignore
from atomicwrites import atomic_write

from mathlibtools.file_status import FileStatus

if TYPE_CHECKING:
    from mathlibtools.import_graph import ImportGraph

from mathlibtools.delayed_interrupt import DelayedInterrupt
from mathlibtools.auth_github import auth_github, Github
from mathlibtools.git_helpers import visit_ancestors, short_sha

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

class LeanProjectError(Exception):
    pass

DOT_MATHLIB = Path(os.environ.get("MATHLIB_CACHE_DIR") or
                   Path.home()/'.mathlib')

AZURE_URL = 'https://oleanstorage.azureedge.net/mathlib/'

DOT_MATHLIB.mkdir(parents=True, exist_ok=True)
DOWNLOAD_URL_FILE = DOT_MATHLIB/'url'

MATHLIB_URL = 'https://github.com/leanprover-community/mathlib.git'
LEAN_VERSION_RE = re.compile(r'(.*)\t.*refs/heads/lean-(.*)')
# This regex is from [1] and implements the logic at [2].
# [1]: https://github.com/leanprover/vscode-lean/blob/2b43982c4c6305a0f20f156152a60613a6f1a683/syntaxes/lean.json#L193
# [2]: https://github.com/leanprover-community/lean/blob/65ad4ffdb3abac75be748554e3cbe990fb1c6500/src/util/name.cpp#L65-L83
LEAN_UNESCAPED_IDENTIFIER_RE = re.compile(
    r"(?![λΠΣ])[_a-zA-Zα-ωΑ-Ωϊ-ϻἀ-῾℀-⅏𝒜-𝖟](?:(?![λΠΣ])[_a-zA-Zα-ωΑ-Ωϊ-ϻἀ-῾℀-⅏𝒜-𝖟0-9'ⁿ-₉ₐ-ₜᵢ-ᵪ])*")

VersionTuple = Tuple[int, int, int]

def mathlib_lean_version() -> VersionTuple:
    """Return the latest Lean release supported by mathlib"""
    resp = requests.get("https://raw.githubusercontent.com/leanprover-community/mathlib/master/leanpkg.toml")
    assert resp.status_code == 200
    conf = toml.loads(resp.text)
    return parse_version(conf['package']['lean_version'])

def set_download_url(url: str = AZURE_URL) -> None:
    """Store the download url in .mathlib."""
    DOWNLOAD_URL_FILE.write_text(url)

def get_download_url() -> str:
    """Get the download url from .mathlib."""
    return DOWNLOAD_URL_FILE.read_text().strip('/\n')+'/'

if not DOWNLOAD_URL_FILE.exists():
    set_download_url()

def pack(root: Path, srcs: Iterable[Path], target: Path) -> None:
    """Creates, as target, a tar.xz archive containing all paths from src,
    relative to the folder root"""
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    cur_dir = Path.cwd()
    with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
        os.chdir(str(root))
        ar = tarfile.open(str(target), 'w|xz')
        for src in srcs:
            ar.add(str(src.relative_to(root)))
        ar.close()
    os.chdir(str(cur_dir))

def unpack_archive(fname: Union[str, Path], tgt_dir: Union[str, Path],
                   oleans_only: bool) -> None:
    """ Alternative to `shutil.unpack_archive` that shows progress"""
    with tarfile.open(fname) as tarobj:
        if oleans_only:
            members : Iterable[tarfile.TarInfo] = (f for f in tarobj if Path(f.name).suffix == '.olean')
        else:
            members = tarobj
        tarobj.extractall(
            str(tgt_dir), members=tqdm(members, desc='  files extracted', unit=''))

def escape_identifier(s : str) -> str:
    """ Helper function to wrap _pieces_ of identifiers in double french quotes
    if they need to be wrapped by lean, we use this for file paths so we also escape
    strings of the form `a.a` even though they are valid identifiers.
    By escaping strings we ensure that lean accepts them as imports"""
    if re.fullmatch(LEAN_UNESCAPED_IDENTIFIER_RE, s):
        return s
    return "«" + s + "»"

def blocks(files, size=65536):
    """Help function to count file lines"""
    while True:
        b = files.read(size)
        if not b: break
        yield b

class OleanCache:
    """ A reference to a cache of oleans for a single commit.

    This is a context manager so that references to caches which hold onto resources
    can clean up when those resources are no longer needed.
    """
    def __init__(self, locator: 'CacheLocator', rev: Commit):
        self.locator = locator
        self.rev = rev
        self.path = self.locator.cache_dir / self.fname

    @property
    def fname(self) -> str:
        return self.rev.hexsha + '.tar.xz'

    def make_local(self) -> 'LocalOleanCache':
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self) -> 'OleanCache':
        return self

    def __exit__(self, *args) -> None:
        self.close()


class LocalOleanCache(OleanCache):
    """ A cache of oleans that lives on the local filesystem.

    Any cache can be converted into a local cache via `OleanCache.download`."""
    def __init__(self, locator: 'CacheLocator', rev):
        super().__init__(locator, rev)
        if not self.path.exists():
            raise LookupError("Local cache not found")

    def make_local(self) -> 'LocalOleanCache':
        return self  # already downloaded


class RemoteOleanCache(OleanCache):
    """ A cache of oleans that lives on a remove server.

    This holds an open HTTP connection to the server from which the cache can be downloaded."""
    def __init__(self, locator: 'CacheLocator', rev):
        super().__init__(locator, rev)
        assert self.locator.cache_url is not None
        self.req = requests.get(self.locator.cache_url + self.fname, stream=True)
        self.req.raise_for_status()

    def close(self):
        self.req.close()

    def make_local(self):
        # download the cache atomically from the already-open connection
        with atomic_write(self.path, mode='wb', overwrite=True) as tgt:
            total_size = int(self.req.headers.get('content-length', 0))
            with tqdm.wrapattr(self.req.raw, "read", total=total_size,
                               desc='  ' + short_sha(self.rev)) as src:
                shutil.copyfileobj(src, tgt)
        self.req.close()
        return LocalOleanCache(self.locator, self.rev)


class CacheFallback(enum.Enum):
    """ Specifies the fallback to use when an exactly matching cache is not available """
    NONE = 'none'
    DOWNLOAD_FIRST = 'download-first'
    DOWNLOAD_ALL = 'download-all'
    SHOW = 'show'


class CacheLocator:
    """ A helper class to locate and download caches for a given repo and remote URL """
    def __init__(self, name: str, repo: Repo, cache_url: Optional[str], cache_dir: Path, *, force_download=False):
        self.name = name
        self.repo = repo
        self.cache_url = cache_url
        self.cache_dir = cache_dir
        self.force_download = force_download

    def find_exact(self, rev: Commit) -> Optional[OleanCache]:
        """ Find a cache that is for `rev` exactly """
        log.info(f"Looking for {self.name} oleans for {short_sha(rev)}")
        if not self.force_download:
            log.info(f'  locally...')
            try:
                local_c = LocalOleanCache(self, rev)
            except LookupError:
                pass
            else:
                log.info(f'  Found local {self.name} oleans')
                return local_c

        if self.cache_url is not None:
            log.info('  remotely...')
            try:
                remote_c = RemoteOleanCache(self, rev)
            except requests.HTTPError:
                pass
            else:
                log.info(f'  Found remote {self.name} oleans')
                return remote_c

        return None

    def find_all(self, rev: Commit) -> Tuple[contextlib.ExitStack, List[OleanCache]]:
        """
        Find all closest ancestors that have a cache. Returns a tuple where the
        first result is a contextmanager that will close any unused http requests
        """
        caches = []
        with contextlib.ExitStack() as stack:
            for parent_commit, prune in visit_ancestors(rev):
                cache = self.find_exact(parent_commit)
                if cache is None:
                    log.info(f"No cache available for revision {short_sha(parent_commit)}")
                else:
                    stack.enter_context(cache)  # ensure we do not leak requests
                    caches.append(cache)
                    prune()  # do not visit the ancestors of this commit
            return stack.pop_all(), caches

        # https://github.com/python/mypy/issues/7726
        assert False

    def find_local_with_fallback(self, rev: Commit, fallback: CacheFallback) -> LocalOleanCache:
        """
        Find (or download) a local cache for `rev` using the provided fallback strategy.
        """
        # if fallback is `NONE`, do not even attempt a search (to conserve network access)
        if fallback == CacheFallback.NONE:
            cache = self.find_exact(rev)
            if not cache:
                raise LeanDownloadError(f"No cache was available for {short_sha(rev)}.\n")
            with cache:
                log.info("Located matching cache")
                return cache.make_local()

        # Otherwise, do a search. This will open as many HTTP connections as
        # necessary, which the `with` statement cleans up.
        ctx, caches = self.find_all(rev)
        with ctx:
            if not caches:
                # this should never happen unless azure goes down
                raise LeanProjectError('No archives available for any commits!')

            cache = caches[0]

            if cache.rev == rev:
                assert len(caches) == 1
                log.info("Using matching cache")
                return caches[0].make_local()

            if len(caches) > 1:
                archive_items = ''.join([f'\n * {short_sha(c.rev)}' for c in caches])
                commit_args = ''.join([f' {short_sha(c.rev)}^!' for c in caches])
                log.warning(
                    f"No cache was available for {short_sha(rev)}.\n"
                    f"There are multiple viable caches from parent commits:{archive_items}\n"
                    f"To see the commits in question, run:\n"
                    f"  git log --graph {short_sha(rev)}{commit_args}")
            else:
                log.warning(
                    f"No cache was available for {short_sha(rev)}. "
                    f"A cache was found for the ancestor {short_sha(cache.rev)}.\n"
                    f"To see the intermediate commits, run:\n"
                    f"  git log --graph {short_sha(rev)} {short_sha(cache.rev)}^!")

            if fallback == CacheFallback.DOWNLOAD_ALL:
                log.info("Preparing all caches, using the first")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    local_caches = list(executor.map(lambda c: c.make_local(), caches))
                return local_caches[0]
            elif fallback == CacheFallback.DOWNLOAD_FIRST:
                log.info("Using first cache")
                return caches[0].make_local()
            elif fallback == CacheFallback.SHOW:
                log.info(f"Run `leanproject get-cache --rev` on one of the available commits above.")
                raise LeanDownloadError
            else:
                raise RuntimeError('Invalid fallback argument')

        # https://github.com/python/mypy/issues/7726
        assert False

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

def clean(dir: Path) -> None:
    log.info('cleaning {} ...'.format(str(dir)))
    for path in dir.glob('**/*.olean'):
        path.unlink()

def delete_zombies(dir: Path) -> None:
    for path in dir.glob('**/*.olean'):
        if not path.with_suffix('.lean').exists():
            log.info('deleting zombie {} ...'.format(str(path)))
            path.unlink()

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

def find_root(path: Path) -> Path:
    """
    Find a Lean project root in path by searching for leanpkg.toml in path and
    its ancestors.
    """
    if (path/'leanpkg.toml').exists():
        return path
    parent = path.absolute().parent
    if parent != path:
        return find_root(parent)
    else:
        raise InvalidLeanProject('Could not find a leanpkg.toml')


class DeclInfo:
    def __init__(self, origin: str, filepath: Path, line: int):
        """Implementation information for a declaration.
        The origin argument is meant to be either 'core' or a project name,
        including mathlib."""
        self.origin = origin
        self.filepath = filepath
        self.line = line

    def __repr__(self) -> str:
        return "DeclInfo('{}', '{}', {})".format(self.origin, self.filepath, self.line)


class LeanProject:
    def __init__(self, repo: Optional[Repo], is_dirty: bool, rev: str, directory: Path,
            pkg_config: dict, deps: dict,
            cache_url: str = '', force_download: bool = False,
            upgrade_lean: bool = True) -> None:
        """A Lean project."""
        self.repo = repo
        self.is_dirty = is_dirty
        self.rev = rev
        self.directory = directory.absolute().resolve()
        self.pkg_config = pkg_config
        self.src_directory = self.directory/pkg_config.get('path', '')
        self.deps = deps
        self.cache_url = cache_url or get_download_url()
        self.force_download = force_download
        self.upgrade_lean = upgrade_lean
        self._import_graph = None # type: Optional[ImportGraph]

    @classmethod
    def from_path(cls, path: Path, cache_url: str = '',
                  force_download: bool = False,
                  upgrade_lean: bool = True) -> 'LeanProject':
        """Builds a LeanProject from a Path object"""
        repo: Optional[Repo] = None
        is_dirty = False
        rev = ''
        try:
            repo = Repo(path, search_parent_directories=True)
        except InvalidGitRepositoryError:
            pass
        if repo:
            if repo.bare:
                raise InvalidLeanProject('Git repository is not initialized')
            is_dirty = repo.is_dirty()
            try:
                rev = repo.commit().hexsha
            except ValueError:
                rev = ''
        directory = find_root(path)
        config = toml.load(directory/'leanpkg.toml')

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

    @property
    def mathlib_repo(self) -> Repo:
        if self.is_mathlib:
            assert self.repo
            return self.repo
        else:
            if not self.mathlib_folder.exists():
                self.run_echo(['leanpkg', 'configure'])
            return Repo(self.mathlib_folder)


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
        """Get precompiled mathlib oleans for this project (which depends on
        mathlib)"""
        if self.is_mathlib:
            # user should have run `get-cache` not `get-mathlib-cache
            log.warning(
                "`get-mathlib-cache` is for projects which depend on "
                "mathlib, not for mathlib itself. "
                "Running `get-cache` instead.")
            return self.get_cache()

        repo = self.mathlib_repo
        try:
            commit = repo.rev_parse(self.mathlib_rev)
        except (BadName, ValueError):
            # presumably the mathlib folder is outdated
            log.info("Can't find the required mathlib revision, will try to update "
                     "mathlib git repository")
            self.run_echo(['leanpkg', 'configure'])
            commit = repo.rev_parse(self.mathlib_rev)

        # Just in case the user broke the workflow (for instance git clone
        # mathlib by hand and then run `leanproject get-cache`)
        if not (self.directory/'leanpkg.path').exists():
            self.run(['leanpkg', 'configure'])

        cache_locator = CacheLocator('mathlib', repo, self.cache_url, DOT_MATHLIB,
                                     force_download=self.force_download)

        # We want an exact match here; if we can't find one, then the user should
        # just point their config file at a version of mathlib with a cache.
        cache = cache_locator.find_local_with_fallback(commit, fallback=CacheFallback.NONE)
        log.info("Applying cache")
        self.clean_mathlib_dep()
        self.mathlib_folder.mkdir(parents=True, exist_ok=True)
        unpack_archive(cache.path, self.mathlib_folder, oleans_only=False)
        if cache.rev != repo.head.commit:
            # If the commit we unpacked isn't HEAD, then there might be some
            # zombie olean files around. It is probably safe, but slower, to do
            # this unconditionally.
            self.delete_zombies()
        # Let's now touch oleans, just in case
        touch_oleans(self.mathlib_folder)

    def mk_cache(self, force: bool = False) -> None:
        """Cache oleans for this project."""
        if not self.rev:
            raise ValueError('This project has no git commit.')
        if not self.repo:
            raise LeanProjectError('This project has no git repository.')
        rev = self.rev
        if self.is_dirty:
            raise LeanProjectError('Unable to make a cache for a dirty '
                'repository. Commit or stash first.')
        tgt_folder = DOT_MATHLIB if self.is_mathlib else self.directory/'_cache'
        tgt_folder.mkdir(exist_ok=True)
        archive = tgt_folder/(str(self.rev) + '.tar.xz')
        if archive.exists() and not force:
            log.info('Cache for revision {} already exists, use --force to replace it.'.format(self.rev))
            return
        pack(self.directory, filter(Path.exists, [self.src_directory, self.directory/'test']),
             archive)

    def get_cache(self, rev: Optional[str] = None,
                  fallback: CacheFallback = CacheFallback.SHOW) -> None:
        """Tries to get olean cache for the current project.

        Will raise LeanDownloadError or FileNotFoundError if no archive exists.
        """
        if not self.repo:
            raise LeanProjectError('This project has no git repository.')

        if self.is_mathlib:
            cache_locator = CacheLocator(self.name, self.repo, self.cache_url, DOT_MATHLIB,
                                         force_download=self.force_download)
        else:
            # TODO: support remote caches for non-mathlib projects
            cache_locator = CacheLocator(self.name, self.repo, None, self.directory/'_cache',
                                         force_download=self.force_download)

        commit = self.repo.rev_parse(rev) if rev is not None else self.repo.head.commit
        cache = cache_locator.find_local_with_fallback(commit, fallback)
        log.info("Applying cache")
        unpack_archive(cache.path, self.directory, oleans_only=True)
        if cache.rev != self.repo.head.commit:
            # If the commit we unpacked isn't HEAD, then there might be some
            # zombie olean files around. It is probably safe, but slower, to do
            # this unconditionally.
            self.delete_zombies()
        # Let's now touch oleans, just in case
        touch_oleans(self.directory)

    @classmethod
    def from_git_url(cls, url: str, target: str = '',
                     branch: str = '', create_branch: bool = False,
                     cache_url: str = '',
                     force_download: bool = False) -> 'LeanProject':
        """Download a Lean project using git and prepare mathlib if needed."""
        log.info('Cloning from ' + url)
        target = target or url.split('/')[-1].split('.')[0]
        repo = Repo.clone_from(url, target)
        if create_branch and branch:
            try:
                repo.git.checkout('HEAD', '-b', branch)
            except (IndexError, GitCommandError):
                log.error('Cannot create new git branch')
                shutil.rmtree(target)
                raise
        elif branch:
            try:
                repo.remote('origin').fetch(branch)
                repo.git.checkout(branch)
            except (IndexError, GitCommandError) as err:
                log.error('Invalid git branch')
                shutil.rmtree(target)
                raise err
        assert repo.working_dir is not None
        proj = cls.from_path(Path(repo.working_dir), cache_url, force_download)
        proj.run_echo(['leanpkg', 'configure'])
        if 'mathlib' in proj.deps or proj.is_mathlib:
            proj.get_mathlib_olean()
        return proj

    @classmethod
    def new(cls, path: Path = Path('.'), cache_url: str = '',
            force_download: bool = False) -> 'LeanProject':
        """Create a new Lean project and prepare mathlib."""
        if path == Path('.'):
            subprocess.run(['leanpkg', 'init', path.absolute().name], check=True)
        else:
            if path.exists():
                raise FileExistsError('Directory ' + str(path) + ' already exists')
            subprocess.run(['leanpkg', 'new', str(path)], check=True)

        proj = cls.from_path(path, cache_url, force_download)
        proj.lean_version = mathlib_lean_version()
        proj.write_config()
        proj.add_mathlib()
        assert proj.repo
        proj.repo.git.checkout('-b', 'master')
        return proj

    def run(self, args: List[str]) -> str:
        """Run a command in the project directory, and returns stdout + stderr.

           args is a list as in subprocess.run"""
        return subprocess.run(args, cwd=str(self.directory),
                              stderr=subprocess.STDOUT,
                              stdout=subprocess.PIPE,
                              check=True).stdout.decode()

    def run_echo(self, args: List[str]) -> None:
        """Run a command in the project directory, letting stdin and stdout
        flow.

           args is a list as in subprocess.run"""
        subprocess.run(args, cwd=str(self.directory), check=True)

    def clean(self) -> None:
        src_dir = self.directory/self.pkg_config['path']
        test_dir = self.directory/'test'
        if src_dir.exists():
            clean(src_dir)
        else:
            raise InvalidLeanProject(
                "Directory {} specified by 'path' does not exist".format(src_dir))
        if test_dir.exists():
            clean(test_dir)

    def delete_zombies(self) -> None:
        src_dir = self.directory/self.pkg_config['path']
        test_dir = self.directory/'test'
        if src_dir.exists():
            delete_zombies(src_dir)
        else:
            raise InvalidLeanProject(
                "Directory {} specified by 'path' does not exist".format(src_dir))
        if test_dir.exists():
            delete_zombies(test_dir)

    def build(self) -> None:
        log.info('Building project ' + self.name)
        if not self.is_mathlib:
            self.clean_mathlib_dep()
        self.run_echo(['leanpkg', 'build'])

    def clean_mathlib_dep(self) -> None:
        """Restore git sanity in a mathlib dependency"""
        assert not self.is_mathlib
        if self.mathlib_folder.exists():
            mathlib = self.mathlib_repo
            mathlib.head.reset(working_tree=True)
            mathlib.git.clean('-fd')
        else:
            self.run_echo(['leanpkg', 'configure'])

    def upgrade_mathlib(self) -> None:
        """Upgrade mathlib in the project.

        In case this project is mathlib, we assume we are already on the branch
        we want.
        """
        if self.is_mathlib:
            assert self.repo
            try:
                rem = next(remote for remote in self.repo.remotes
                           if any('leanprover' in url
                                  for url in remote.urls))
                log.info('Pulling...')
                rem.pull(self.repo.active_branch)
            except (StopIteration, GitCommandError):
                log.info("Couldn't pull from a relevant git remote. "
                         "You may try to git pull manually and then "
                         "run `leanproject get-cache`")
                return
            self.rev = self.repo.commit().hexsha
        else:
            self.clean_mathlib_dep()
            if self.upgrade_lean:
                mathlib_lean = mathlib_lean_version()

                if mathlib_lean > self.lean_version:
                    self.lean_version = mathlib_lean
                    self.write_config()
            self.run_echo(['leanpkg', 'upgrade'])
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
        self.run_echo(['leanpkg', 'add', 'leanprover-community/mathlib'])
        self.read_config()
        self.get_mathlib_olean()

    def setup_git_hooks(self) -> None:
        if self.repo is None:
            raise LeanProjectError('This project has no git repository.')
        hook_dir = Path(self.repo.git_dir)/'hooks'
        src = Path(__file__).parent
        log.info('This script will copy post-commit and post-checkout scripts to %s', hook_dir)
        rep = input("Do you want to proceed (y/n)? ")
        if rep in ['y', 'Y']:
            shutil.copy(str(src/'post-commit'), str(hook_dir))
            mode = (hook_dir/'post-commit').stat().st_mode
            (hook_dir/'post-commit').chmod(mode | stat.S_IXUSR)
            shutil.copy(str(src/'post-checkout'), str(hook_dir))
            mode = (hook_dir/'post-checkout').stat().st_mode
            (hook_dir/'post-checkout').chmod(mode | stat.S_IXUSR)
            log.info("Successfully copied scripts")
        else:
            log.info("Cancelled...")

    def check_timestamps(self) -> Tuple[bool, bool]:
        """Check that core and mathlib oleans are more recent than their
        sources. Return a tuple (core_ok, mathlib_ok)"""
        try:
            mathlib_ok = all(p.stat().st_mtime < p.with_suffix('.olean').stat().st_mtime
                             for p in (self.mathlib_folder/'src').glob('**/*.lean'))
        except FileNotFoundError:
            mathlib_ok = False

        return (check_core_timestamps(self.toolchain), mathlib_ok)

    @property
    def import_graph(self) -> 'ImportGraph':
        # Importing networkx + numpy is slow, so don't do it until this function
        # is called.
        from mathlibtools.import_graph import ImportGraph

        if self._import_graph:
            return self._import_graph
        G = ImportGraph(self.directory)
        for path in self.src_directory.glob('**/*.lean'):
            rel = path.relative_to(self.src_directory)
            label = str(rel.with_suffix('')).replace(os.sep, '.')
            G.add_node(label)
            imports = self.run(['lean', '--deps', str(path)])
            for imp in map(Path, imports.split()):
                try:
                    imp_rel = imp.relative_to(self.src_directory.resolve())
                except ValueError:
                    # This import is not from the project
                    continue
                imp_label = str(imp_rel.with_suffix('')).replace(os.sep, '.')
                G.add_edge(imp_label, label)
        self._import_graph = G
        return G

    def reduce_imports(self, file: str) -> Iterable[Tuple[str, List[str]]]:
        """
        An iterator over files with removable imports, for each file yielding
        a list of removable imports in the format
        `("source.file", ["removable.import", "another.removable.import"])`.
        """
        # Importing networkx is slow, so don't do it until this function
        # is called.
        import networkx as nx # type: ignore
        G = self.import_graph
        if file:
            G = G.ancestors(file)
        H = nx.transitive_reduction(G)
        if file:
            fs = [file]
        else:
            fs = G.nodes
        for f in fs:
            if f == "all":
                continue
            Gf = [e for e in G.edges if e[1] == f]
            Hf = [e for e in H.edges if e[1] == f]
            o = [e[0] for e in Gf if e not in Hf]
            if o:
                yield (f, o)

    def reduce_imports_sed(self, file: str) -> Iterable[str]:
        for src, removable in self.reduce_imports(file):
            for r in removable:
                # probably not the right command on osx
                yield "sed -i '/^import {line}$/d' src/{file}.lean".format(file=src.replace(".","/"), line=r)

    def make_all(self) -> None:
        """Creates all.lean importing everything from the project"""

        with (self.src_directory/'all.lean').open('w') as all_file:
            for path in self.src_directory.glob('**/*.lean'):
                rel = path.relative_to(self.src_directory).with_suffix('')
                if rel == Path('all'):
                    continue
                all_file.write('import ' + ".".join(map(escape_identifier, rel.parts)) + '\n')

    def list_decls(self) -> Dict[str, DeclInfo]:
        """Collect declarations seen from this project, as a dictionary of
        DeclInfo"""
        all_exists = (self.src_directory/'all.lean').exists()
        list_decls_lean = self.src_directory/'list_decls.lean'
        try:
            list_decls_lean.unlink()
        except FileNotFoundError:
            pass

        log.info('Gathering imports')
        self.make_all()
        imports = (self.src_directory/'all.lean').read_text()
        decls_lean = (Path(__file__).parent/'decls.lean').read_text()
        list_decls_lean.write_text(imports+decls_lean)
        log.info('Collecting declarations')
        self.run_echo(['lean', '--run', str(list_decls_lean)])
        data = yaml.safe_load((self.directory/'decls.yaml').open())
        list_decls_lean.unlink()
        if not all_exists:
            (self.src_directory/'all.lean').unlink()
        decls = dict()
        for name, val in data.items():
            fname = val['File']
            line = val['Line']
            if fname is None or line is None:
                continue
            path = Path(fname).absolute().resolve()
            if '_target' in fname:
                path = path.relative_to(self.directory/'_target'/'deps')
                origin = path.parts[0]
                path = path.relative_to(Path(origin)/'src')
            elif '.elan' in fname:
                origin = 'core'
                parts = path.parts
                path = Path('/'.join(parts[parts.index('.elan')+7:]))
            else:
                origin = self.name
                path = path.relative_to(self.src_directory)
            decls[name] = DeclInfo(origin, path, int(val['Line']))

        return decls

    def pickle_decls(self, target: Path) -> None:
        """Safe declaration into a pickle file target"""
        with target.open('wb') as f:
            pickle.dump(self.list_decls(), f, pickle.HIGHEST_PROTOCOL)

    def pr(self, branch_name: str, force: bool = False) -> None:
        """
        Prepare to work on a mathlib pull-request on a new branch.
        This will check for a clean working copy unless force is True.
        """
        if self.is_dirty and not force:
            raise LeanDirtyRepo
        if not self.is_mathlib:
            raise LeanProjectError('This operation is for mathlib only.')
        if not self.repo:
            raise LeanProjectError('This project has no git repository.')
        if branch_name in self.repo.branches: # type: ignore
            raise LeanProjectError(f'The branch {branch_name} already exists, '
                                    'please choose another name.')
        log.info('Checking out master...')
        self.repo.git.checkout('master')
        origin = self.repo.remote().name
        self.upgrade_mathlib()
        log.info('Checking out new branch...')
        self.repo.git.checkout('-b', branch_name)
        log.info(f'Setting remote tracking to {origin}...')
        rem_ref = RemoteReference(self.repo,
                                  f"refs/remotes/{origin}/{branch_name}")
        self.repo.head.reference.set_tracking_branch(rem_ref)
        log.info('Done.')

    def rebase(self, force: bool = False) -> None:
        """
        On mathlib, update master, get oleans and rebase current branch.
        This will check for a clean working copy unless force is True.
        """
        if self.is_dirty and not force:
            raise LeanDirtyRepo('Cannot rebase because repository is dirty')
        if not self.is_mathlib:
            raise LeanProjectError('This operation is for mathlib only.')
        if not self.repo:
            raise LeanProjectError('This project has no git repository.')
        branch = self.repo.active_branch
        if branch.name == 'master':
            raise LeanProjectError('This does not make sense now '
                                   'since you are on master.')
        log.info('Checking out master...')
        self.repo.git.checkout('master')
        self.upgrade_mathlib()
        log.info(f'Checking out {branch}...')
        self.repo.git.checkout(branch)
        log.info('Rebasing...')
        self.repo.git.rebase('master')
        log.info('Done')

    def pull(self, remote: str='origin') -> None:
        """
        Pull from the given remote and get mathlib oleans.
        """
        if self.is_dirty:
            raise LeanDirtyRepo('Cannot pull because repository is dirty')
        old_mathlib = self.mathlib_rev
        assert self.repo
        log.info(f"Pulling from {remote}")
        self.repo.remote(remote).pull(self.repo.active_branch)
        self.read_config()
        if self.is_mathlib:
            self.get_cache()
        else:
            if self.mathlib_rev != old_mathlib:
                log.info("Updating mathlib")
                self.run_echo(['leanpkg', 'configure'])
            self.get_mathlib_olean()

    def port_status(self, url: Optional[str] = None) -> None:
        """
        Color nodes on the graph based on port status. Done in place to the graph nodes.

        Args:
            url: md or yaml file with "file: label" content, by default, from the wiki
        """
        if url is None:
            url = 'https://raw.githubusercontent.com/wiki/leanprover-community/mathlib/mathlib4-port-status.md'
        def yaml_md_load(wikicontent: bytes):
            return yaml.safe_load(wikicontent.replace(b"```", b""))

        port_labels: Dict[str, str] = yaml_md_load(requests.get(url).content)

        for filename, status in port_labels.items():
            if filename not in self.import_graph.nodes:
                continue
            node = self.import_graph.nodes[filename]
            node_path = self.src_directory.joinpath(*filename.split(".")).with_suffix(".lean")
            with open(node_path, "r",encoding="utf-8",errors='ignore') as f:
                node["nb_lines"] = sum(bl.count("\n") for bl in blocks(f))
            node["status"] = FileStatus.assign(status)
        # somehow missing from yaml
        # for node_name, node in self.import_graph.nodes(data=True):
        #     if node_name not in port_labels:
        #         node["status"] = FileStatus.missing()
        finished_nodes = {node for node, attrs in self.import_graph.nodes(data=True)
                          if attrs.get("status") == FileStatus.yes()}
        # tag nodes that have finished parents, depth of 1
        for node in finished_nodes:
            # does not get root nodes because they are not at end of an out_edge
            for _, target in self.import_graph.out_edges(node):
                # we don't need to redo a finished node
                if target in finished_nodes:
                    continue
                parents = {parent for parent, _ in self.import_graph.in_edges(target)}
                if parents.issubset(finished_nodes):
                    target_node = self.import_graph.nodes[target]
                    if not target_node.get("status"):
                        target_node["status"] = FileStatus.ready()
        # now to get root nodes
        for target, degree in self.import_graph.in_degree():
            target_node = self.import_graph.nodes[target]
            if degree > 0 or target_node.get("status"):
                continue
            target_node["status"] = FileStatus.ready()
        for _, node in self.import_graph.nodes(data=True):
            if not node.get("status"):
                continue
            node["style"] = "filled"
            node["fillcolor"] = node["status"].color
