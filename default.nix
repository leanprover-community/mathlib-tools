{ pkgs ? import <nixpkgs> {} }:

with pkgs.python3Packages;
buildPythonApplication {
  pname = "mathlib-tools";
  version = "0.0.2";
  src = ./.;

  propagatedBuildInputs = [
    PyGithub GitPython toml
  ];
}
