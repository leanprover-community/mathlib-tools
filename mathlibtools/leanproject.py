import sys
from pathlib import Path

from git.exc import GitCommandError # type: ignore
import click

from mathlibtools.lib import (LeanProject, log, LeanDirtyRepo,
    InvalidLeanProject, LeanDownloadError, set_download_url)

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

def proj():
    return LeanProject.from_path(Path('.'))

# The following is a global state variable. This is a lazy way of propagating
# the global url option.
url = ''

@click.group(cls=CustomMultiCommand, context_settings={ 'help_option_names':['-h', '--help']})
@click.option('--from-url', '-u', default='',
              help='Override base url for olean cache.')
def cli(from_url):
    """Command line client to manage Lean projects depending on mathlib.
    Use leanproject COMMAND --help to get more help on any specific command."""
    global url 
    url = from_url

@cli.command()
@click.argument('path', default='.')
def new(path: str = '.'):
    """Create a new Lean project and prepare mathlib.

    If no directory name is given, the current directory is used.
    """
    LeanProject.new(Path(path), url)

@cli.command()
def add_mathlib():
    """Add mathlib to the current project."""
    proj().add_mathlib(url)

@cli.command(['upgrade-mathlib', 'update-mathlib', 'up'])
def upgrade_mathlib():
    """Upgrade mathlib (as a dependency or as the main project)."""
    try:
        proj().upgrade_mathlib(url)
    except LeanDownloadError:
        log.error('Failed to fetch mathlib oleans')
        sys.exit(-1)
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
def build():
    """Build the current project."""
    proj().build()

@cli.command(name='get')
@click.argument('name')
@click.argument('dir', default='')
def get_project(name: str, target: str = ''):
    """Clone a project from a GitHub name or git url.
    
    Put it in dir if this argument is given.
    A GitHub name without / will be considered as
    a leanprover-community project."""
    if not name.startswith(('git@', 'http')):
        if '/' not in name:
            name = 'leanprover-community/'+url
        name = 'https://github.com/'+url+'.git'
    try:
        LeanProject.from_git_url(name, target, url)
    except GitCommandError:
        log.error('Git command failed')
        sys.exit(-1)
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
@click.option('--force', default=False,
              help='Make cache even if the repository is dirty.')
def mk_cache(force: bool = False):
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
@click.option('--force', default=False,
              help='Get cache even if the repository is dirty.')
def get_cache(force: bool = False):
    """Restore cached olean files."""
    try:
        proj().get_cache(force, url)
    except LeanDirtyRepo:
        log.error('The repository is dirty, please commit changes before '
                  'fetching cache, or run this command with option --force.')
        sys.exit(-1)
    except LeanDownloadError:
        log.error('Failed to fetch mathlib oleans')
        sys.exit(-1)
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
def hooks():
    """Setup git hooks for the current project."""
    try:
        proj().setup_git_hooks()
    except Exception as err:
        log.error(err)
        sys.exit(-1)

@cli.command()
@click.argument('url')
def set_url(url: str):
    """Set the default url where oleans should be fetched."""
    set_download_url(url)
