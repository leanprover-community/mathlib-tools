import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Set, Union

import requests
import yaml
from dataclasses_json import config, dataclass_json


class Ported(Enum):

    yes = "Yes"
    no = "No"


class PRStatus(Enum):

    pr = "PR"
    wip = "WIP"


@dataclass_json
@dataclass(frozen=True)
class FileStatusNew:

    ported: Ported = field(
        default=Ported.no, metadata=config(encoder=lambda x: str(x.value))
    )
    pr_status: Optional[PRStatus] = field(
        default=None, metadata=config(encoder=lambda x: x if x is None else str(x))
    )
    mathlib4_pr: Optional[int] = None
    mathlib_hash: Optional[str] = None

    @classmethod
    def parse_old(cls, message: str) -> "FileStatusNew":
        ported = Ported.no
        pr_status: Optional[PRStatus] = None
        mathlib4_pr: Optional[int] = None
        mathlib_hash: Optional[str] = None
        for pr_val in PRStatus:
            if str(pr_val.value) in message:
                pr_status = pr_val
        if pr_status == PRStatus.pr:
            mathlib4_pr = int(
                re.findall(r"[0-9]+", message.replace("mathlib4#", ""))[0]
            )
        if message.startswith(str(Ported.yes.value)):
            ported = Ported.yes
            if len(message.split()) > 2:
                mathlib_hash = message.split()[2]
            if pr_status == PRStatus.wip:
                raise ValueError("The merged file is still labeled as WIP")
            mathlib4_pr = int(
                re.findall(r"[0-9]+", message.replace("mathlib4#", ""))[0]
            )
        return cls(
            ported=ported,
            pr_status=pr_status,
            mathlib4_pr=mathlib4_pr,
            mathlib_hash=mathlib_hash,
        )


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
        return (self.prefix is None or comment.startswith(self.prefix)) and all(
            substring.lower() in comment.lower() for substring in self.string_match
        )

    @classmethod
    def assign(cls, comment: str) -> Optional["FileStatus"]:
        for status in [cls.yes(), cls.pr(), cls.wip()]:
            if status.matches(comment):
                return status
        # "No" but other comments
        if cls.no().matches(comment) and len(comment) > 2:
            return cls.no()
        return None


@dataclass_json
@dataclass
class PortStatus:

    file_statuses: Dict[str, FileStatusNew]

    @classmethod
    def old_yaml(
        cls,
        url="https://raw.githubusercontent.com/wiki/leanprover-community/mathlib/mathlib4-port-status.md",
    ) -> Dict[str, str]:
        def yaml_md_load(wikicontent: bytes):
            return yaml.safe_load(wikicontent.replace(b"```", b""))

        return yaml_md_load(requests.get(url).content)

    @classmethod
    def deserialize_old(cls, yaml: Dict[str, str]) -> "PortStatus":
        return cls(file_statuses={k: FileStatus.parse_old(v) for k, v in yaml.items()})

    def serialize(self) -> Dict[str, Dict[str, Union[int, str, None]]]:
        return yaml.dump(self.to_dict()["file_statuses"])
