from dataclasses import dataclass
from typing import Optional, Set

@dataclass(frozen=True)
class FileStatus:
  """Capture the file status descriptions in the wiki yaml.

  `string_match` are the substrings that must be found, lowercase match
  `color` is how the node should be colored if it has the status
  """

  string_match: Set[str]
  # colors from X11
  color: str

  @classmethod
  def yes(cls) -> "FileStatus":
    return cls({"yes"}, "green")

  @classmethod
  def pr(cls) -> "FileStatus":
    return cls({"no", "pr"}, "lightskyblue")

  @classmethod
  def wip(cls) -> "FileStatus":
    return cls({"no", "wip"}, "lightpink")

  @classmethod
  def no(cls) -> "FileStatus":
    return cls({"no"}, "orange")

  @classmethod
  def missing(cls) -> "FileStatus":
    return cls(set(), "orchid1")

  @classmethod
  def ready(cls) -> "FileStatus":
    return cls(set(), "turquoise1")

  def matches(self, comment: str) -> bool:
    return all(substring.lower() in comment.lower() for substring in self.string_match)

  @classmethod
  def assign(cls, comment: str) -> Optional["FileStatus"]:
    for status in [cls.yes(), cls.pr(), cls.wip()]:
      if status.matches(comment):
        return status
    # "No" but other comments
    if cls.no().matches(comment) and len(comment) > 2:
      return cls.no()
    return None
