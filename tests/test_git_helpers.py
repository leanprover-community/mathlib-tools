import pytest
from types import SimpleNamespace
import git
from mathlibtools.git_helpers import visit_ancestors


@pytest.fixture
def dummy_repo(tmp_path):
    r"""
    A -- B -- E -- I -- J -- L
          \       /    /
           C --- F -- H
            \        /
             D ---- G --- K
    """
    d = tmp_path / "repo"
    d.mkdir()
    repo = git.Repo.init(d)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "pytest")
        cw.set_value("user", "email", "<>")

    A = repo.index.commit("A")
    B = repo.index.commit("B", parent_commits=(A,))
    C = repo.index.commit("C", parent_commits=(B,))
    D = repo.index.commit("D", parent_commits=(C,))
    E = repo.index.commit("E", parent_commits=(B,))
    F = repo.index.commit("F", parent_commits=(C,))
    G = repo.index.commit("G", parent_commits=(D,))
    I = repo.index.commit("I", parent_commits=(E, F))
    H = repo.index.commit("H", parent_commits=(F, G))
    J = repo.index.commit("J", parent_commits=(I, H))
    K = repo.index.commit("K", parent_commits=(G,))
    L = repo.index.commit("L", parent_commits=(J,))
    return repo


@pytest.mark.parametrize(['match', 'exp_found', 'exp_visited'], [
    ('L', 'L', ''),           # finding the root prunes everything else
    ('BFG', 'GF', 'LJHIE'),   # B is pruned
    ('K', '', 'LJHGDIFCEBA'),  # no match, all iterated
])
def test_visit_ancestors(dummy_repo, match, exp_found, exp_visited):
    assert dummy_repo.head.commit.message == 'L'
    found = []
    visited = []
    for c, prune in visit_ancestors(dummy_repo.head.commit):
        if c.message in list(match):
            prune()
            found.append(c.message)
        else:
            visited.append(c.message)
    assert visited == list(exp_visited)
    assert found == list(exp_found)
