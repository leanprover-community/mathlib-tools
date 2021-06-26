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
from datetime import datetime
from typing import Iterable, Union, List, Tuple, Optional, Dict, TYPE_CHECKING
from tempfile import TemporaryDirectory

import requests
from tqdm import tqdm # type: ignore
import toml
import yaml
from git import Repo, InvalidGitRepositoryError, GitCommandError # type: ignore

if TYPE_CHECKING:
    from mathlibtools.import_graph import ImportGraph

from mathlibtools.delayed_interrupt import DelayedInterrupt
from mathlibtools.auth_github import auth_github, Github

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

    fname = rev + '.tar.xz'
    path = DOT_MATHLIB/fname
    if not force:
        log.info('Looking for local mathlib oleans')
        if path.exists():
            log.info('Found local mathlib oleans')
            return path
    log.info('Looking for remote mathlib oleans')
    base_url = url or get_download_url()
    download(base_url + fname, path)
    log.info('Found mathlib oleans at ' + base_url)
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
        try:
            repo = Repo(path, search_parent_directories=True)
        except InvalidGitRepositoryError:
            repo = None
            is_dirty = False
            rev = ''
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

    def get_mathlib_olean(self, rev: Optional[str] = None) -> None:
        """Get precompiled mathlib oleans for this project, at a specific
        commit if rev is provided."""
        # Just in case the user broke the workflow (for instance git clone
        # mathlib by hand and then run `leanproject get-cache`)
        if self.is_mathlib and rev:
            assert self.repo
            rev = self.repo.rev_parse(rev).hexsha
        if not (self.directory/'leanpkg.path').exists():
            self.run(['leanpkg', 'configure'])
        try:
            archive = get_mathlib_archive(rev or self.mathlib_rev,
                                          self.cache_url, self.force_download)
        except (EOFError, shutil.ReadError):
            log.info('Something wrong happened with the olean archive. '
                     'I will now retry downloading.')
            archive = get_mathlib_archive(rev or self.mathlib_rev,
                                          self.cache_url, True)
        self.clean_mathlib()
        self.mathlib_folder.mkdir(parents=True, exist_ok=True)
        unpack_archive(archive, self.mathlib_folder)
        if rev:
            self.delete_zombies()
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
        archive = tgt_folder/(str(self.rev) + '.tar.xz')
        if archive.exists() and not force:
            log.info('Cache for revision {} already exists'.format(self.rev))
            return
        pack(self.directory, filter(Path.exists, [self.src_directory, self.directory/'test']),
             archive)

    def get_cache(self, rev: Optional[str] = None, force: bool = False) -> None:
        """Tries to get olean cache.

        Will raise LeanDownloadError or FileNotFoundError if no archive exists.
        """
        if not self.repo:
            raise LeanProjectError('This project has no git repository.')
        if self.is_dirty and not force:
            raise LeanDirtyRepo('Cannot get cache for a dirty repository.')
        if self.is_mathlib:
            self.get_mathlib_olean(rev)
        else:
            if rev:
                rev = self.repo.rev_parse(rev).hexsha
            unpack_archive(self.directory/'_cache'/(rev or str(self.rev)+'.tar.xz'),
                           self.directory)

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
                repo.git.checkout('HEAD', b=branch)
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
        self.clean_mathlib()
        self.run_echo(['leanpkg', 'build'])

    def clean_mathlib(self, force: bool = False) -> None:
        """Restore git sanity in mathlib"""
        if self.is_mathlib:
            if not self.is_dirty or force:
                assert self.repo
                self.repo.head.reset(working_tree=True)
        elif self.mathlib_folder.exists():
            mathlib = Repo(self.mathlib_folder)
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
            self.clean_mathlib()
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
        log.info('This script will copy post-commit and post-checkout scripts to ', hook_dir)
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
        for node in G:
            G.nodes[node]['label'] = node
        self._import_graph = G
        return G

    def make_all(self) -> None:
        """Creates all.lean importing everything from the project"""
        with (self.src_directory/'all.lean').open('w') as all_file:
            for path in self.src_directory.glob('**/*.lean'):
                rel = str(path.relative_to(self.src_directory).with_suffix(''))
                if rel == 'all':
                    continue
                all_file.write('import ' + rel.replace(os.path.sep, '.') + '\n')

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
        if branch_name in self.repo.branches:
            raise LeanProjectError(f'The branch {branch_name} already exists, '
                                    'please choose another name.')
        log.info('Checking out master...')
        self.repo.git.checkout('master')
        self.upgrade_mathlib()
        log.info('Checking out new branch...')
        self.repo.git.checkout('-b', branch_name)
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
