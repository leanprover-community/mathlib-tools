from git import Commit   # type: ignore
from typing import Callable, Iterator, Tuple, List


def short_sha(rev: Commit) -> str:
    """ Truncate `rev.hexsha` without ambiguity """
    return rev.repo.git.rev_parse(rev.hexsha, short=True)


def visit_ancestors(rev: Commit) -> Iterator[Tuple[Commit, Callable]]:
    r"""
    Iterate over history, optionally pruning all ancestors of a given commit.

    This iterates backwards over history starting at `rev` and traversing the
    commit graph in topological (as opposed to date) order, ensuring that child
    commits are always visited before any of their parent commits. In this
    sense, this function is like ``repo.iter_commits(rev, topo_order=True)``.

    The key difference from ``iter_commits`` is that this version yields
    ``commit, prune`` pairs, where ``prune`` is a function accepting no
    arguments. If ``prune()`` is called, then the iterator will not visit any
    of the commits which are ancestors of ``commit``; that is, the history
    "tree" from that point backwards is pruned.

    As an example, consider a repository with the commit graph below, where
    ``A`` is the root commit and ``K`` and ``L`` are tips of branches::

        A -- B -- E -- I -- J -- L
              \       /    /
               C --- F -- H
                \        /
                 D ---- G --- K

    The following code runs against this commit graph, and calls ``prune``
    if it finds commits ``B``, ``F``, or ``G``::

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
        found   G
        found   F
        visited E

    As a result of calling ``prune()`` on commit ``G``, the ancestors of ``G``
    (``D``, ``C``, ``B``, and ``A``) are pruned from the graph and never
    visited. The exact order that these commits appear in depends on the order
    of parents in merge commits, but since ``B`` is an ancestor of both ``F``
    and ``G``, it will always be pruned before it is visited.
    """
    repo = rev.repo
    pruned_commits : List[Commit] = []  # the commits to ignore along with their ancestors
    skip_n = 0  # the index to resume the iteration
    while True:
        args = [rev] + ['--not'] + pruned_commits
        proc = repo.git.rev_list(*args, as_process=True, skip=skip_n, topo_order=True)
        for c in Commit._iter_from_process_or_stream(repo, proc):
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
