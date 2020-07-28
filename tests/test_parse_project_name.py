from mathlibtools.leanproject import parse_project_name as P

def test_name():
    name, url, branch, is_url = P('tutorials')
    assert name == 'tutorials'
    assert url == 'git@github.com:leanprover-community/tutorials.git'
    assert branch == ''
    assert not is_url

def test_org_name():
    name, url, branch, is_url = P('leanprover-community/tutorials')
    assert name == 'tutorials'
    assert url == 'git@github.com:leanprover-community/tutorials.git'
    assert branch == ''
    assert not is_url

def test_https():
    name, url, branch, is_url = P('https://github.com/leanprover-community/tutorials.git')
    assert name == 'tutorials'
    assert url == 'https://github.com/leanprover-community/tutorials.git'
    assert branch == ''
    assert is_url

def test_ssh():
    name, url, branch, is_url = P('git@github.com:leanprover-community/tutorials.git')
    assert name == 'tutorials'
    assert url == 'git@github.com:leanprover-community/tutorials.git'
    assert branch == ''
    assert is_url

def test_name_branch():
    name, url, branch, is_url = P('tutorials:foo')
    assert name == 'tutorials'
    assert url == 'git@github.com:leanprover-community/tutorials.git'
    assert branch == 'foo'
    assert not is_url

def test_org_name_branch():
    name, url, branch, is_url = P('leanprover-community/tutorials:foo')
    assert name == 'tutorials'
    assert url == 'git@github.com:leanprover-community/tutorials.git'
    assert branch == 'foo'
    assert not is_url

def test_https_branch():
    name, url, branch, is_url = P('https://github.com/leanprover-community/tutorials.git:foo')
    assert name == 'tutorials'
    assert url == 'https://github.com/leanprover-community/tutorials.git'
    assert branch == 'foo'
    assert is_url

def test_ssh_branch():
    name, url, branch, is_url = P('git@github.com:leanprover-community/tutorials.git:foo')
    assert name == 'tutorials'
    assert url == 'git@github.com:leanprover-community/tutorials.git'
    assert branch == 'foo'
    assert is_url
