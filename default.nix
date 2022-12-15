{ pkgs ? import <nixpkgs> {} }:

with pkgs.python3Packages;
buildPythonApplication {
  pname = "mathlib-tools";
  version = "1.3.2";
  src = ./.;

  doCheck = false;

  propagatedBuildInputs = [
    PyGithub GitPython toml click tqdm paramiko networkx pydot pyyaml atomicwrites
  ];
}
