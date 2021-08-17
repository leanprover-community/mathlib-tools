from typing import Optional, Sequence, List, Any, Iterable, Union
from pathlib import Path

from git import BadName

class FakeCommit:
    def __init__(self, repo: 'FakeRepo', sha:str, parents: Optional[Sequence['FakeCommit']] = None ) -> None:
        self.repo = repo
        self.hexsha = sha

class FakeFetchInfo:
    pass

class FakeRemote:
    def __init__(self, repo: 'FakeRepo', name: str, urls: List[str]):
        self.repo = repo
        self.name = name
        self.urls = urls

    def fetch(self, refspec: Union[str, List[str], None] = None, **kwargs: Any) -> List[FakeFetchInfo]:
        return []

    def pull(self, branch: str):
        pass

class FakeHead:
    def __init__(self, repo: 'FakeRepo', name: str, commit: FakeCommit):
        self.repo = repo
        self.name = name
        self.commit = commit

    def reset(self, working_tree: bool = False):
        pass

    def __eq__(self, other: str) -> bool:
        # TODO: fix this mess
        return self.commit.hexsha == other

class FakeGit:
    def __init__(self, path: Path):
        self.path = path

    def checkout(self, *args, **kwargs):
        pass

    def rebase(self, branch: str):
        pass

    def rev_list(self, *args, **kwargs):
        pass

    def rev_parse(self, sha, *args, **kwargs):
        return sha

class FakeRepo:
    def __init__(self, path: Optional[Path] = None, search_parent_directories: bool = False):
        self.working_dir = path or Path()
        self.git_dir = self.working_dir/'.git'
        self.commits: List[FakeCommit] = []
        self.remotes: List[FakeRemote] = []
        self.heads: List[FakeHead] = []
        self.active_branch = 'master'
        self.bare = False
        self.dirty = False
        self.git = FakeGit(path or Path())

    @classmethod
    def clone_from(cls, url: Path, to_path, **kwargs: Any) -> 'FakeRepo':
        return cls(to_path)

    def commit(self):
        if self.commits:
            return self.commits[-1]
        else:
            raise ValueError('No commit')

    @property
    def branches(self):
        return self.heads

    @property
    def head(self):
        return FakeHead(self, self.active_branch, self.commits[-1])

    def is_dirty(self):
        return self.dirty

    def rev_parse(self, rev: str) -> FakeCommit:
        try:
            return next(commit for commit in self.commits if commit.hexsha == rev)
        except StopIteration:
            raise BadName(rev)
