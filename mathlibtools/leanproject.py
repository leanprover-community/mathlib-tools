import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Tuple

from git.exc import GitCommandError # type: ignore
import paramiko # type: ignore
from paramiko.ssh_exception import AuthenticationException, SSHException # type: ignore
import click

from mathlibtools.lib import (LeanProject, log, LeanDirtyRepo,
    InvalidLeanProject, LeanDownloadError, set_download_url, touch_oleans)

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
            else:
                _args = args
            cmd = super(CustomMultiCommand, self).command(
                *_args, **kwargs)(f)
            return cmd

        return decorator

def proj() -> LeanProject:
    return LeanProject.from_path(Path('.'), cache_url, force_download,
                                 lean_upgrade)

# The following are global state variables. This is a lazy way of propagating
# the global options.
cache_url = ''
force_download = False
lean_upgrade = True

@click.group(cls=CustomMultiCommand, context_settings={ 'help_option_names':['-h', '--help']})
@click.option('--from-url', '-u', default='', nargs=1,
              help='Override base url for olean cache.')
@click.option('--force-download', '-f', 'force', default=False, is_flag=True,
              help='Download olean cache without looking for a local version.')
@click.option('--no-lean-upgrade', 'noleanup', default=False, is_flag=True,
              help='Do not upgrade Lean version when upgrading mathlib.')
def cli(from_url: str, force: bool, noleanup: bool) -> None:
    """Command line client to manage Lean projects depending on mathlib.
    Use leanproject COMMAND --help to get more help on any specific command."""
    global cache_url, force_download, lean_upgrade
    cache_url = from_url
    force_download = force
    lean_upgrade = not noleanup

@cli.command()
@click.argument('path', default='.')
def new(path: str = '.') -> None:
    """Create a new Lean project and prepare mathlib.

    If no directory name is given, the current directory is used.
    """
    try:
        LeanProject.new(Path(path), cache_url, force_download)
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
def add_mathlib() -> None:
    """Add mathlib to the current project."""
    try:
        proj().add_mathlib()
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command(['upgrade-mathlib', 'update-mathlib', 'up'])
def upgrade_mathlib() -> None:
    """Upgrade mathlib (as a dependency or as the main project)."""
    try:
        proj().upgrade_mathlib()
    except LeanDownloadError:
        log.error('Failed to fetch mathlib oleans')
        sys.exit(-1)
    except InvalidLeanProject:
        project = LeanProject.user_wide(cache_url, force_download)
        project.upgrade_mathlib()
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
def build() -> None:
    """Build the current project."""
    try:
        proj().build()
    except Exception as err:
        log.error(err)
        sys.exit(-1)

def parse_project_name(name: str, ssh: bool = True) -> Tuple[str, str, str]:
    """Parse the name argument for get_project
    Returns (name, url, branch).
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
    else:
        url = name
        name = name.split('/')[-1].replace('.git', '')

    return name, url, branch

@cli.command(name='get')
@click.argument('name')
@click.argument('directory', default='')
def get_project(name: str, directory: str = '') -> None:
    """Clone a project from a GitHub name or git url.
    
    Put it in dir if this argument is given.
    A GitHub name without / will be considered as
    a leanprover-community project.
    If the name ends with ':foo' then foo will be interpreted
    as a branch name, and that branch will be checked out."""

    # check whether we can ssh into GitHub
    try:
        client = paramiko.client.SSHClient()
        client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy) 
        client.connect('github.com', username='git')
        client.close()
        ssh = True
    except (AuthenticationException, SSHException):
        ssh = False

    name, url, branch = parse_project_name(name, ssh)
    if branch:
        name = name + '_' + branch
    directory = directory or name
    if directory and Path(directory).exists():
        log.error(directory + ' already exists')
        sys.exit(-1)
    try:
        LeanProject.from_git_url(url, directory, branch, 
                                 cache_url, force_download)
    except GitCommandError:
        log.error('Git command failed')
        sys.exit(-1)
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
@click.option('--force', default=False, is_flag=True,
              help='Make cache even if the repository is dirty or cache exists.')
def mk_cache(force: bool = False) -> None:
    """Cache olean files."""
    try:
        proj().mk_cache(force)
    except LeanDirtyRepo:
        log.error('The repository is dirty, please commit changes before '
                 'making cache, or run this command with option --force.')
        sys.exit(-1)
    except Exception as err:
        log.error(err)
        sys.exit(-1)


@cli.command()
@click.option('--force', default=False, is_flag=True,
              help='Get cache even if the repository is dirty.')
def get_cache(force: bool = False) -> None:
    """Restore cached olean files."""
    try:
        proj().get_cache(force)
    except LeanDirtyRepo:
        log.error('The repository is dirty, please commit changes before '
                  'fetching cache, or run this command with option --force.')
        sys.exit(-1)
    except (LeanDownloadError, FileNotFoundError):
        log.error('Failed to fetch mathlib oleans')
        sys.exit(-1)
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
def hooks() -> None:
    """Setup git hooks for the current project."""
    try:
        proj().setup_git_hooks()
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
@click.argument('url')
def set_url(url: str) -> None:
    """Set the default url where oleans should be fetched."""
    set_download_url(url)

@cli.command()
def check() -> None:
    """Check mathlib oleans are more recent than their sources"""
    try:
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
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
def global_install() -> None:
    """Install mathlib user-wide."""
    try:
        proj = LeanProject.user_wide(cache_url, force_download)
        proj.add_mathlib()
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
def global_upgrade() -> None:
    """Upgrade user-wide mathlib"""
    try:
        proj = LeanProject.user_wide(cache_url, force_download)
        proj.upgrade_mathlib()
    except Exception as err:
        log.error(err)
        sys.exit(-1)
