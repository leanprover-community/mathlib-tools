#!/bin/bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"

# Install dependencies
brew install gmp coreutils python3 pipx

# Install Elan
curl https://raw.githubusercontent.com/Kha/elan/master/elan-init.sh -sSf | sh
source ~/.profile

# Install mathlib supporting tools
pipx ensurepath
source ~/.bash_profile
pipx install mathlibtools

# Install and configure VS Code
brew cask install visual-studio-code
code --install-extension jroesch.lean