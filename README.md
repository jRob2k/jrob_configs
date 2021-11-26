# Customization-Scripts
Various scripts and documentation to help me customize my devices

# To get started....
Install Github cli (not required but hey, it's fun.)

# Official instructions from Githubs.... uh... Github repo. --> https://github.com/cli/cli/blob/trunk/docs/install_linux.md

# TL:DR;
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh
