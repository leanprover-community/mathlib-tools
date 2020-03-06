import os.path
import os
import tarfile
import urllib3
import certifi
import signal

from mathlibtools.auth_github import auth_github
from mathlibtools.delayed_interrupt import DelayedInterrupt

def mathlib_asset(rev):
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


def fetch_mathlib(asset, target='.'):
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
        with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
            with open(asset.name, 'wb') as f:
                f.write(req.data)
        os.chdir(cd)
    else:
        print("Reusing cached olean archive")

    with DelayedInterrupt([signal.SIGTERM, signal.SIGINT]):
        ar = tarfile.open(os.path.join(mathlib_dir, asset.name))
        ar.extractall(target)
        print("... successfully extracted olean archive.")
