from dataclasses import dataclass, field
from typing import Optional, Set

@dataclass(frozen=True)
class FileStatus:
  """Capture the file status descriptions in the wiki yaml.

  `string_match` are the substrings that must be found, lowercase match
  `color` is how the node should be colored if it has the status
  """

  color: str
  prefix: Optional[str] = None
  string_match: Set[str] = field(default_factory=set)
  # colors from X11

  @classmethod
  def yes(cls) -> "FileStatus":
    return cls("green", "Yes")

  @classmethod
  def pr(cls) -> "FileStatus":
    return cls("lightskyblue", "No", {"pr"})

  @classmethod
  def wip(cls) -> "FileStatus":
    return cls("lightskyblue", "No", {"wip"})

  @classmethod
  def no(cls) -> "FileStatus":
    return cls("orange", "No")

  # @classmethod
  # def missing(cls) -> "FileStatus":
  #   return cls("orchid1")

  @classmethod
  def ready(cls) -> "FileStatus":
    return cls("turquoise1")

  def matches(self, comment: str) -> bool:
    return (self.prefix is None or comment.startswith(self.prefix)) and \
        all(substring.lower() in comment.lower() for substring in self.string_match)

  @classmethod
  def assign(cls, comment: str) -> Optional["FileStatus"]:
    for status in [cls.yes(), cls.pr(), cls.wip()]:
      if status.matches(comment):
        return status
    # "No" but other comments
    if cls.no().matches(comment) and len(comment) > 2:
      return cls.no()
    return None
