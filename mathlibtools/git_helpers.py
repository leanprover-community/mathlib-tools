import git   # type: ignore
from typing import Callable, Iterator, Tuple, List


def visit_ancestors(rev: git.Commit) -> Iterator[Tuple[git.Commit, Callable]]:
    r"""
    Iterate over the ancestors of the commit `rev` in topological order, with
    the option to prune parents of visited commits.

    Consider the commit graph::

        A -- B -- E -- I -- J -- L
              \       /    /
               C --- F -- H
                \        /
                 D ---- G --- K

    where ``A`` is the root commit and ``K`` and ``L`` are tips of branches.
    The following code runs against this commit graph

    >>> for c, prune in visit_ancestors(L):
    ...     if c in {B, F, G}:
    ...         prune()
    ...         print('found  ', c)
    ...     else:
    ...         print('visited', c)
    visited L
    visited J
    visited H
    visited I
    found   F
    found   G
    visited E

    The exact order these commits appear in depends on the order of parents in
    merge commits, but independent of this ``B`` will never be visited as it is
    a parent of ``F`` and ``G``, and the sort order is topological.
    """
    repo = rev.repo
    pruned_commits : List[git.Commit] = []  # the commits to ignore along with their ancestors
    skip_n = 0  # the index to resume the iteration
    while True:
        args = [rev] + ['--not'] + pruned_commits
        proc = repo.git.rev_list(*args, as_process=True, skip=skip_n, topo_order=True)
        for c in git.Commit._iter_from_process_or_stream(repo, proc):
            # build a temporary function to hand back to the user
            do_prune = False
            def prune():
                nonlocal do_prune
                do_prune = True
            yield c, prune
            if do_prune:
                pruned_commits.append(c)
                break
            else:
                # start after this commit next time we restart the search
                skip_n += 1
        else:
            # all ancestors found
            return
