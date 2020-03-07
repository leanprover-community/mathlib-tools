from mathlibtools.leanproject import parse_project_name as P

def test_name():
    name, url, branch = P('tutorials')
    assert name == 'tutorials'
    assert url == 'https://github.com/leanprover-community/tutorials.git'
    assert branch == ''

def test_org_name():
    name, url, branch = P('leanprover-community/tutorials')
    assert name == 'tutorials'
    assert url == 'https://github.com/leanprover-community/tutorials.git'
    assert branch == ''

def test_https():
    name, url, branch = P('https://github.com/leanprover-community/tutorials.git')
    assert name == 'tutorials'
    assert url == 'https://github.com/leanprover-community/tutorials.git'
    assert branch == ''

def test_ssh():
    name, url, branch = P('git@github.com:leanprover-community/tutorials.git')
    assert name == 'tutorials'
    assert url == 'git@github.com:leanprover-community/tutorials.git'
    assert branch == ''

def test_name_branch():
    name, url, branch = P('tutorials:foo')
    assert name == 'tutorials'
    assert url == 'https://github.com/leanprover-community/tutorials.git'
    assert branch == 'foo'

def test_org_name_branch():
    name, url, branch = P('leanprover-community/tutorials:foo')
    assert name == 'tutorials'
    assert url == 'https://github.com/leanprover-community/tutorials.git'
    assert branch == 'foo'

def test_https_branch():
    name, url, branch = P('https://github.com/leanprover-community/tutorials.git:foo')
    assert name == 'tutorials'
    assert url == 'https://github.com/leanprover-community/tutorials.git'
    assert branch == 'foo'

def test_ssh_branch():
    name, url, branch = P('git@github.com:leanprover-community/tutorials.git:foo')
    assert name == 'tutorials'
    assert url == 'git@github.com:leanprover-community/tutorials.git'
    assert branch == 'foo'
