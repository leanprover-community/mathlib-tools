import sys
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional
from getpass import getpass

from git.exc import GitCommandError # type: ignore

import click

from mathlibtools.lib import (LeanProject, log,
    InvalidLeanProject, LeanDownloadError, set_download_url, touch_oleans,
    CacheFallback)

# Click aliases from Stephen Rauch at
# https://stackoverflow.com/questions/46641928
class CustomMultiCommand(click.Group):
    def command(self, *args, **kwargs):
        """Behaves the same as `click.Group.command()` except if passed
        a list of names, all after the first will be aliases for the first.
        """
        def decorator(f):
            if args and isinstance(args[0], list):
                _args = [args[0][0]] + list(args[1:])
                for alias in args[0][1:]:
                    cmd = super(CustomMultiCommand, self).command(
                        alias, *args[1:], **kwargs)(f)
                    cmd.short_help = "Alias for '{}'".format(_args[0])
                    cmd.hidden = True
            else:
                _args = args
            cmd = super(CustomMultiCommand, self).command(
                *_args, **kwargs)(f)
            return cmd

        return decorator

    """Allows the user to shorten commands to a (unique) prefix."""
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        matches = [x for x in self.list_commands(ctx)
                   if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail('Too many matches: %s' % ', '.join(sorted(matches)))

def proj() -> LeanProject:
    return LeanProject.from_path(Path('.'), cache_url, force_download,
                                 lean_upgrade)

# The following are global state variables. This is a lazy way of propagating
# the global options.
cache_url = ''
force_download = False
lean_upgrade = True
debug = False

def handle_exception(exc, msg):
    if debug:
        raise exc
    else:
        log.error(msg)
        sys.exit(-1)

@click.group(cls=CustomMultiCommand, context_settings={ 'help_option_names':['-h', '--help']})
@click.option('--from-url', '-u', default='', nargs=1,
              help='Override base url for olean cache.')
@click.option('--force-download', '-f', 'force', default=False, is_flag=True,
              help='Download olean cache without looking for a local version.')
@click.option('--no-lean-upgrade', 'noleanup', default=False, is_flag=True,
              help='Do not upgrade Lean version when upgrading mathlib.')
@click.option('--debug', 'python_debug', default=False, is_flag=True,
              help='Display python tracebacks in case of error.')
@click.version_option()
def cli(from_url: str, force: bool, noleanup: bool, python_debug: bool) -> None:
    """Command line client to manage Lean projects depending on mathlib.
    Use leanproject COMMAND --help to get more help on any specific command."""
    global cache_url, force_download, lean_upgrade, debug
    cache_url = from_url
    force_download = force
    lean_upgrade = not noleanup
    debug = python_debug

@cli.command()
@click.argument('path', default='.')
def new(path: str = '.') -> None:
    """Create a new Lean project and prepare mathlib.

    If no directory name is given, the current directory is used.
    """
    LeanProject.new(Path(path), cache_url, force_download)

@cli.command()
def add_mathlib() -> None:
    """Add mathlib to the current project."""
    proj().add_mathlib()

@cli.command(['upgrade-mathlib', 'update-mathlib', 'up'])
def upgrade_mathlib() -> None:
    """Upgrade mathlib (as a dependency or as the main project)."""
    try:
        proj().upgrade_mathlib()
    except LeanDownloadError as err:
        handle_exception(err, 'Failed to fetch mathlib oleans')
    except InvalidLeanProject:
        project = LeanProject.user_wide(cache_url, force_download)
        project.upgrade_mathlib()

@cli.command()
def build() -> None:
    """Build the current project."""
    proj().build()

def parse_project_name(name: str, ssh: bool = True) -> Tuple[str, str, str, bool]:
    """Parse the name argument for get_project
    Returns (name, url, branch, is_url).
    If name is not a full url, the returned url will be a https or ssh
    url depending on the boolean argument ssh.
    """
    # This is split off the actual command function for
    # unit testing purposes
    if ':' in name:
        pieces = name.split(':')
        if len(pieces) >= 3:
            name = ':'.join(pieces[:-1])
            branch = pieces[-1]
        elif 'http' in pieces[0] or '@' in pieces[0]:
            branch = ''
        else:
            name, branch = pieces
    else:
        branch = ''

    if not name.startswith(('git@', 'http')):
        if '/' not in name:
            org_name = 'leanprover-community/'+name
        else:
            org_name, name = name, name.split('/')[1]
        if ssh:
            url = 'git@github.com:'+org_name+'.git'
        else:
            url = 'https://github.com/'+org_name+'.git'
        is_url = False
    else:
        url = name
        name = name.split('/')[-1].replace('.git', '')
        is_url = True

    return name, url, branch, is_url

@cli.command(name='get')
@click.argument('name')
@click.argument('directory', default='')
@click.option('--new-branch', '-b', default=False, is_flag=True,
              help='Create a new branch.')
def get_project(name: str, new_branch: bool, directory: str = '') -> None:
    """Clone a project from a GitHub name or git url.

    Put it in dir if this argument is given.
    A GitHub name without / will be considered as
    a leanprover-community project.
    If the name ends with ':foo' then foo will be interpreted
    as a branch name, and that branch will be checked out.

    This will fail if the branch does not exist. If you want to create a new
    branch, pass the `-b` option."""

    original_name = name
    name, url, branch, is_url = parse_project_name(original_name)
    if branch:
        name = name + '_' + branch
    directory = directory or name
    if directory and Path(directory).exists():
        raise FileExistsError('Directory ' + directory + ' already exists')
    try:
        LeanProject.from_git_url(url, directory, branch, new_branch,
                                 cache_url, force_download)
    except GitCommandError as err:
        # if full url is provided, do not retry with HTTPS
        if not is_url:
            log.info('Error cloning via SSH, trying HTTPS...')
            try:
                name, url, branch, is_url = parse_project_name(original_name, ssh=False)
                LeanProject.from_git_url(url, directory, branch, new_branch,
                                 cache_url, force_download)
            except GitCommandError as e:
                handle_exception(e, e.stderr)
        else:
            handle_exception(err, err.stderr)

@cli.command()
@click.option('--force', default=False, is_flag=True,
              help='Make cache even if the cache already exists.')
def mk_cache(force: bool = False) -> None:
    """Cache olean files.

    The repository must be clean in order to ensure there is a suitable git
    commit to associate the hash with."""
    proj().mk_cache(force)

@cli.command()
@click.option('--rev', default=None, help='A git sha.')
@click.option('--fallback', type=click.Choice(['none', 'show', 'download-first', 'download-all']),
              default='show', help="Behavior if no matching cache is available.")
def get_cache(rev: Optional[str], fallback: str) -> None:
    """Restore olean files from a cache.

    \b
    The fallback parameter is interpreted as follows:
      none: fail without trying anything else
      show: show but do not download possible fallback caches
      download-first: show all fallback caches, download and apply the first
      download-all: show and download all fallback caches, apply the first.
    """
    fallback_enum = CacheFallback(fallback)
    try:
        proj().get_cache(rev, fallback_enum)
    except (LeanDownloadError, FileNotFoundError) as err:
        handle_exception(err, 'Failed to fetch cached oleans')

@cli.command()
def get_mathlib_cache() -> None:
    """Get mathlib .lean and .olean files in a project depending on mathlib,
    without upgrading."""
    project = proj()
    try:
        project.get_mathlib_olean()
    except (LeanDownloadError, FileNotFoundError) as err:
        handle_exception(err, 'Failed to fetch mathlib oleans')

@cli.command()
def delete_zombies() -> None:
    """Delete zombie oleans, .olean files with no matching .lean files"""
    proj().delete_zombies()

@cli.command()
def clean() -> None:
    """Delete all olean files"""
    proj().clean()

@cli.command()
def hooks() -> None:
    """Setup git hooks for the current project."""
    proj().setup_git_hooks()

@cli.command()
@click.argument('url')
def set_url(url: str) -> None:
    """Set the default url where oleans should be fetched."""
    set_download_url(url)

@cli.command()
def check() -> None:
    """Check mathlib oleans are more recent than their sources"""
    project = proj()
    core_ok, mathlib_ok = project.check_timestamps()
    toolchain = project.toolchain
    toolchain_path = Path.home()/'.elan'/'toolchains'/toolchain
    if not core_ok:
        print('Some core oleans files in toolchain {} seem older than '
              'their source.'.format(toolchain))
        touch = input('Do you want to set their modification time to now (y/n) ? ')
        if touch.lower() in ['y', 'yes']:
            touch_oleans(toolchain_path)
    if not mathlib_ok:
        print('Some mathlib oleans files seem older than their source.')
        touch = input('Do you want to set their modification time to now (y/n) ? ')
        if touch.lower() in ['y', 'yes']:
            touch_oleans(project.mathlib_folder/'src')
    if core_ok and mathlib_ok:
        log.info('Everything looks fine.')

@cli.command()
def mk_all() -> None:
    """Creates all.lean importing everything from the project."""
    proj().make_all()

@cli.command()
def global_install() -> None:
    """Install mathlib user-wide."""
    proj = LeanProject.user_wide(cache_url, force_download)
    proj.add_mathlib()

@cli.command()
def global_upgrade() -> None:
    """Upgrade user-wide mathlib"""
    proj = LeanProject.user_wide(cache_url, force_download)
    proj.upgrade_mathlib()

@cli.command()
@click.option('--to', 'to', default=None,
              help='Return only imports leading to this file.')
@click.option('--from', 'from_', default=None,
              help='Return only imports starting from this file.')
@click.option('--exclude-tactics', 'exclude', default=False, is_flag=True,
              help='Excludes tactics and meta, adding edges for transitive dependencies.')
@click.option('--port-status', default=False, is_flag=True,
              help='Color by mathlib4 porting status')
@click.option('--port-status-url', default=None,
              help='URL of yaml with mathlib4 port status')
@click.option('--reduce', 'reduce', default=False, is_flag=True,
              help='Omit transitive imports.')
@click.argument('output', default='import_graph.dot')
def import_graph(
    to: Optional[str],
    from_: Optional[str],
    exclude : bool,
    port_status: bool,
    port_status_url: Optional[str],
    reduce: bool,
    output: str
) -> None:
    """Write an import graph for this project.

    Arguments for '--to' and '--from' should be specified as
    Lean imports (e.g. 'data.mv_polynomial') rather than file names.

    You may specify an output filename, and the suffix will determine the output format.
    By default the graph will be written to 'import_graph.dot'.
    For .dot, .pdf, .svg, or .png output you will need to install 'graphviz' first.
    """
    project = proj()
    graph = project.import_graph
    if exclude:
        graph = graph.exclude_tactics()
        project._import_graph = graph
    if port_status or port_status_url:
        project.port_status(port_status_url)
    if to and from_:
        G = graph.path(start=from_, end=to)
    elif to:
        G = graph.ancestors(to)
    elif from_:
        G = graph.descendants(from_)
    else:
        G = graph
    if reduce or exclude:
        G = G.transitive_reduction()
    G.write(Path(output))


@cli.command()
def port_progress() -> None:
    """Print progress report for the Lean 4 port."""
    project = proj()
    project.port_status()
    graph = project.import_graph
    graph = graph.exclude_tactics()
    graph = graph.transitive_reduction()
    nb_files = graph.size()
    nb_lines = sum(node.get("nb_lines", 0) for name, node in graph.nodes(data=True))
    print(f"Total files in mathlib:            {nb_files}")
    print(f"Longest import chain in mathlib:   {graph.longest_path_length()}")
    graph = graph.delete_ported()
    nb_ported_files = nb_files - graph.size()
    proportion_files = round(nb_ported_files/nb_files*100, 1)
    nb_ported_lines = nb_lines - sum(node.get("nb_lines", 0) for name, node in graph.nodes(data=True))
    proportion_lines = round(nb_ported_lines/nb_lines*100, 1)
    print(f"Ported files in mathlib:           {nb_ported_files} ({proportion_files}% of total)")
    print(f"Ported lines in mathlib:           {nb_ported_lines} ({proportion_lines}% of total)")
    print(f"Longest unported chain in mathlib: {graph.longest_path_length()}")
    print(graph.longest_path())


@cli.command()
@click.option('--sed', 'sed', default=False, is_flag=True,
              help='Instead of printing a list of removable imports, print a sed script that can be run to remove the imports.')
@click.argument('file', default=None, required=False)
def reduce_imports(file: str, sed: bool = False) -> None:
    """List imports that can be removed in the project in the format
    `("source.file", ["removable.import", "another.removable.import"])`.

    Argument '--file' should be specified as a
    Lean import (e.g. 'data.mv_polynomial') rather than a file name.
    """
    project = proj()
    if sed:
        print("# on mac use gsed instead of sed")
        for l in project.reduce_imports_sed(file=file):
            print(l)
    else:
        for t in project.reduce_imports(file=file):
            print(t)


@cli.command()
@click.argument('path', default='')
def decls(path: str = '') -> None:
    """List declarations seen from this project

    If no file name is given, the result will be in decls.yaml
    in the project root.
    """
    project = proj()
    decls = project.list_decls()
    outpath = Path(path) if path else project.directory/'decls.yaml'
    with outpath.open('w') as outfile:
        for name, info in decls.items():
            outfile.write('{}:\n  origin: {}\n  path: {}\n  line: {}\n'.format(
                name, info.origin, info.filepath, info.line))


@cli.command()
@click.argument('branch_name')
@click.option('--force', default=False, is_flag=True,
              help='Update master and create branch even if the repository is dirty.')
def pr(branch_name: str, force: bool = False) -> None:
    """Prepare to work on a mathlib pull-request on a new branch."""
    proj().pr(branch_name, force)


@cli.command()
@click.option('--force', default=False, is_flag=True,
              help='Rebase on master even if the repository is dirty.')
def rebase(force: bool = False) -> None:
    """
    On mathlib, update master, get oleans and rebase current branch.
    """
    proj().rebase(force)


@cli.command()
@click.argument('remote', default='origin')
def pull(remote: str = '') -> None:
    """
    Pull and get mathlib oleans. Default remote is 'origin'.
    """
    proj().pull(remote)


def safe_cli():
    try:
        cli() # pylint: disable=no-value-for-parameter
    except Exception as err:
        handle_exception(err, str(err))

if __name__ == "__main__":
    # This allows `python3 -m mathlibtools.leanproject`.
    # This is useful for when python is on the path but its installed scripts are not
    # It also allows pyinstaller to create leanproject.exe standalone executable for Windows
    safe_cli()
