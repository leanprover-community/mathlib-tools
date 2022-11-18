import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Union

import requests
import yaml


@dataclass()
class FileStatus:

    ported: bool = False
    mathlib4_pr: Optional[int] = None
    mathlib3_hash: Optional[str] = None
    comments: Optional[str] = None

    @classmethod
    def parse_old(cls, message: str) -> "FileStatus":
        ported = False
        mathlib4_pr: Optional[int] = None
        mathlib3_hash: Optional[str] = None
        if message.startswith("Yes"):
            ported = True
            if len(message.split()) > 2:
                mathlib3_hash = message.split()[2]
        if "mathlib4#" in message:
            mathlib4_pr = int(re.findall(r"[0-9]+", message.replace("mathlib4#", ""))[0])
        return cls(
            ported=ported,
            mathlib4_pr=mathlib4_pr,
            mathlib3_hash=mathlib3_hash,
        )

    def asdict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}



@dataclass
class PortStatus:

    file_statuses: Dict[str, FileStatus]

    @classmethod
    def old_yaml(cls, url: Optional[str] = None) -> Dict[str, str]:
        if url is None:
            url = "https://raw.githubusercontent.com/wiki/leanprover-community/mathlib/mathlib4-port-status.md"
        def yaml_md_load(wikicontent: bytes):
            return yaml.safe_load(wikicontent.replace(b"```", b""))

        return yaml_md_load(requests.get(url).content)

    @classmethod
    def deserialize_old(cls, yaml: Optional[Dict[str, str]] = None) -> "PortStatus":
        if yaml is None:
            yaml = cls.old_yaml()
        return cls(file_statuses={k: FileStatus.parse_old(v) for k, v in yaml.items()})

    def serialize(self) -> Dict[str, Dict[str, Union[int, str, None]]]:
        return yaml.dump({k: v.asdict() for k, v in self.file_statuses.items()})
