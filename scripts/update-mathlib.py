#!/usr/bin/env python3

import os.path
import os
import sys
from github import Github
from git import Repo, InvalidGitRepositoryError
import toml
import urllib3
import certifi
import configparser
import tarfile
import signal
from delayed_interrupt import DelayedInterrupt
from auth_github import auth_github

self_update = '--self-update' in sys.argv

if self_update:
    mathlib_url = 'https://raw.githubusercontent.com/leanprover-community/mathlib-tools'
    branch  = 'master'
    installer_path = 'scripts/remote-install-update-mathlib.sh'
    os.system("curl {%s}/{%s}/{%s} -sSf | sh" % (mathlib_url,branch,installer_path))
else:
    # find root of project and leanpkg.toml
    cwd = os.getcwd()
    while not os.path.isfile('leanpkg.toml') and os.getcwd() != '/':
        os.chdir(os.path.dirname(os.getcwd()))

    # parse leanpkg.toml
    try:
        leanpkg = toml.load('leanpkg.toml')
    except FileNotFoundError:
        print('Error: No leanpkg.toml found')
        sys.exit(1)


    try:
        lib = leanpkg['dependencies']['mathlib']
    except KeyError:
        print('Error: Project does not depend on mathlib')
        sys.exit(1)

    try:
        git_url = lib['git']
        rev = lib['rev']
    except KeyError:
        print('Error: Project seems to refer to a local copy of mathlib '
              'instead of a GitHub repository')
        sys.exit(1)

    # some leanpkg files might contain urls ending in '/'
    git_url = git_url.rstrip('/')
    
    if git_url not in ['https://github.com/leanprover/mathlib',
                       'https://github.com/leanprover-community/mathlib']:
        print('Error: mathlib reference is a fork')
        sys.exit(1)

    # download archive
    g = auth_github()
    print("Querying GitHub...")
    repo = g.get_repo("leanprover-community/mathlib-nightly")
    tags = {tag.name: tag.commit.sha for tag in repo.get_tags()}
    try:
        release = next(r for r in repo.get_releases()
                       if r.tag_name.startswith('nightly-') and
                       tags[r.tag_name] == rev)
    except StopIteration:
        print('Error: no nightly archive found')
        sys.exit(1)

    try:
        asset = next(x for x in release.get_assets()
                     if x.name.startswith('mathlib-olean-nightly-'))
    except StopIteration:
        print("Error: Release " + release.tag_name + " does not contains a olean "
              "archive (this shouldn't happen...)")
        sys.exit(1)

    # Get archive if needed
    mathlib_dir = os.path.join(os.environ['HOME'], '.mathlib')
    if not os.path.isdir(mathlib_dir):
        os.mkdir(mathlib_dir)

    if not os.path.isfile(os.path.join(mathlib_dir, asset.name)):
        print("Downloading nightly...")
        cd = os.getcwd()
        os.chdir(mathlib_dir)
        http = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED',
            ca_certs=certifi.where())
        req = http.request('GET', asset.browser_download_url)
        with open(asset.name, 'wb') as f:
            f.write(req.data)
        os.chdir(cd)
    else:
        print("Reusing cached olean archive")

    # Extract archive
    print("Extracting nightly...")
    with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
        ar = tarfile.open(os.path.join(mathlib_dir, asset.name))
        ar.extractall('_target/deps/mathlib')
