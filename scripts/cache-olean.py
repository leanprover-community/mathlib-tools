#!/usr/bin/env python3
import os.path
import os
import sys
import tarfile
import configparser
import urllib3
import certifi
import signal
from git import Repo, InvalidGitRepositoryError
from github import Github
from delayed_interrupt import DelayedInterrupt
from auth_github import auth_github


def make_cache(fn):
    if os.path.exists(fn):
        os.remove(fn)

    with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
        ar = tarfile.open(fn, 'w|bz2')
        if os.path.exists('src/'): ar.add('src/')
        if os.path.exists('test/'): ar.add('test/')
        ar.close()
        print('... successfully made olean cache.')

def mathlib_asset(repo, rev):
    if not any(['leanprover' in r.url and 'mathlib' in r.url
                for r in repo.remotes]):
        return None

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
        return None

    try:
        asset = next(x for x in release.get_assets()
                       if x.name.startswith('mathlib-olean-nightly-'))
    except StopIteration:
        print("Error: Release " + release.tag_name + " does not contains a olean "
              "archive (this shouldn't happen...)")
        return None
    return asset

class PushDir:
    def __init__(self, new):
        self.__cd = os.getcwd()
        os.chdir(new)
    def __enter__(self):
        return self
    def __exit__(self):
        os.chdir(self.__cd)

def query_remote_cache(root, rev):
    print ('Querying remote Mathlib cache...')
    name = 'olean-%s.bz2' % rev
    url = 'https://tqft.net/lean/mathlib/%s' % name
    to_file =  os.path.join(root, '_cache', name)
    http = urllib3.PoolManager(
        cert_reqs='CERT_REQUIRED',
        ca_certs=certifi.where())
    try:
        req = http.request('GET', url)
        if req.status != 200:
            print ('Error: revision not found')
            return False
    except:
        print ('Error: revision not found')
        return False

    with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
        with open(to_file, 'wb') as f:
            f.write(req.data)

    print('using remote Mathlib cache...')
    with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
        ar = tarfile.open(to_file)
        ar.extractall(root)
        print("... successfully extracted olean archive.")
    return True

def fetch_mathlib(asset):
    mathlib_dir = os.path.join(os.environ['HOME'], '.mathlib')
    if not os.path.isdir(mathlib_dir):
        os.mkdir(mathlib_dir)

    if not os.path.isfile(os.path.join(mathlib_dir, asset.name)):
        print("Downloading nightly...")
        with PushDir(mathlib_dir):
            http = urllib3.PoolManager(
                cert_reqs='CERT_REQUIRED',
                ca_certs=certifi.where())
            req = http.request('GET', asset.browser_download_url)
            with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
                with open(asset.name, 'wb') as f:
                    f.write(req.data)
    else:
        print("Reusing cached olean archive")

    with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
        ar = tarfile.open(os.path.join(mathlib_dir, asset.name))
        ar.extractall('.')
        print("... successfully extracted olean archive.")


if __name__ == "__main__":
    try:
        repo = Repo('.', search_parent_directories=True)
    except InvalidGitRepositoryError:
        print('This does not seem to be a git repository.')
        sys.exit(-1)

    if repo.bare:
        print('Repository not initialized')
        sys.exit(-1)

    root_dir = repo.working_tree_dir
    os.chdir(root_dir)
    rev = repo.commit().hexsha

    cache_dir = os.path.join(root_dir, "_cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    fn = os.path.join(cache_dir, 'olean-' + rev + ".bz2")

    if sys.argv[1:] == ['--fetch']:
        if os.path.exists(fn):
            ar = tarfile.open(fn, 'r')
            ar.extractall(root_dir)
            ar.close()
            print('... successfully fetched local cache.')
        elif query_remote_cache(root_dir, rev):
            pass
        else:
            asset = mathlib_asset(repo, rev)
            if asset:
                fetch_mathlib(asset)
            else:
                print('no cache found')
    elif sys.argv[1:] == ['--build']:
        os.system('leanpkg build')
        make_cache(fn)  # we make the cache even if the build failed
    elif sys.argv[1:] == ['--build-all']:
        for b in repo.branches:
            print("Switching to branch " + b.name)
            try:
                b.checkout()
            except Exception as e:
                print("Failed to switch branch:")
                print(repr(e))
                continue
            rev = repo.commit().hexsha
            fn = os.path.join(cache_dir, 'olean-' + rev + ".bz2")
            os.system('leanpkg build')
            make_cache(fn) # we make the cache even if the build failed
    elif sys.argv[1:] == ['--build-new']:
        for b in repo.branches:
            rev = b.commit.hexsha
            fn = os.path.join(cache_dir, 'olean-' + rev + ".bz2")
            if os.path.exists(fn):
                print("Branch already built: " + b.name)
            else:
                print("Building branch: " + b.name)
                try:
                    b.checkout()
                except Exception as e:
                    print("Failed to switch branch:")
                    print(repr(e))
                    continue
                os.system('leanpkg build')
                make_cache(fn) # we make the cache even if the build failed
    elif sys.argv[1:] == ['--delete']:
        if os.path.exists(fn):
            print('Deleting %s...' % ('_cache/olean-' + rev + ".bz2"))
            os.remove(fn)
        else:
            print('Error: %s does not exist' % ('_cache/olean-' + rev + ".bz2"))
    elif sys.argv[1:] == []:
        make_cache(fn)
    else:
        print('usage: cache-olean [--fetch | --build | --build-all | --build-new]')
