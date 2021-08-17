import os
from pathlib import Path

import git

from mocks import FakeRepo, FakeCommit

import mathlibtools
from mathlibtools.lib import LeanProject
"""
Pour les tests hors création de projet, il vaut mieux appeler le constructeur de LeanProject (c'est fait pour ça).
Ensuite on peut modifier directement proj.repo et proj.mathlib_repo de l'object proj obtenu
(pour mathlib_repo c'est plus compliqué car c'est une propriété, cf. ci-dessous).
"""

def test_un(mocker):
    path = Path('proj')
    mocked_subprocess_run = mocker.patch('subprocess.run')
    mocked_git = mocker.patch('mathlibtools.lib.Repo', new=FakeRepo)
    mocker.patch('mathlibtools.lib.find_root').return_value = path
    mocker.patch('toml.load').return_value = {
			 'package': {'name': 'tata',
			  'version': '0.1',
			  'lean_version': 'leanprover-community/lean:3.31.0',
			  'path': 'src'},
			 'dependencies': {'mathlib': {'git': 'https://github.com/leanprover-community/mathlib',
			   'rev': '7b5c60db3324a7bbb708482743db8efa36ba52ef'}}}
    mocker.patch('mathlibtools.lib.LeanProject.write_config')

    fake_mathlib = FakeRepo(path/'_target'/'deps'/'mathlib')
    mocker.patch('mathlibtools.lib.LeanProject.mathlib_repo', new_callable=mocker.PropertyMock,
            return_value=fake_mathlib)

    proj = LeanProject.from_path(path)
    assert False

def test_deux(mocker):
    repo = FakeRepo()

    mocker.patch('requests.get')
    mocked_download = mocker.patch.object(mathlibtools.lib.RemoteOleanCache,'make_local')
    mocked_download.return_value = None

    fake_mathlib = FakeRepo(Path()/'_target'/'deps'/'mathlib')
    fake_commit = FakeCommit(fake_mathlib, '7b5c60db3324a7bbb708482743db8efa36ba52ef')
    fake_mathlib.commits = [fake_commit]
    mocker.patch('mathlibtools.lib.LeanProject.mathlib_repo', new_callable=mocker.PropertyMock,
            return_value=fake_mathlib)

    mocker.patch('mathlibtools.lib.LeanProject.mathlib_folder', new_callable=mocker.PropertyMock)

    mocked_run_echo = mocker.patch.object(mathlibtools.lib.LeanProject,'run_echo')

    mocked_clean_mathlib = mocker.patch.object(mathlibtools.lib.LeanProject,'clean_mathlib')

    mocker.patch('mathlibtools.lib.unpack_archive')

    mocked_iter = mocker.patch.object(git.Commit, '_iter_from_process_or_stream')
    mocked_iter.return_value = iter([fake_commit])

    proj = LeanProject(repo, is_dirty=False, rev="abcd", directory=Path(),
            pkg_config={'name': 'tata', 'version': '0.1', 'lean_version': 'leanprover-community/lean:3.31.0', 'path': 'src'}
            , deps= {'mathlib': {'git': 'https://github.com/leanprover-community/mathlib', 'rev': '7b5c60db3324a7bbb708482743db8efa36ba52ef'}})
    def exists(path):
        if '.tar.xz' in str(path):
            return False
        else:
            return os.path.exists(str(path))

    mocked_exists = mocker.patch.object(mathlibtools.lib.Path,'exists', new=exists)
    proj.get_mathlib_olean()
