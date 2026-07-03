#!/bin/bash

# Source this file in your ".bashrc" to add the scripts to your environment.
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
if [ -z $SCRIPT_DIR/.git ]; then 
    echo "Error: no .git found for util project!"
fi 
alias archive="uv --directory "$SCRIPT_DIR" run bin/archive" 
alias unarchive="uv --directory "$SCRIPT_DIR" run bin/unarchive" 
alias telegram-message="uv --directory "$SCRIPT_DIR" run bin/telegram-message" 
