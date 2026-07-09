#!/bin/bash

# Source this file in your ".bashrc" to add the scripts to your environment.
GIT_ROOT=$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel) 
if [ -z $GIT_ROOT/.git ]; then 
    echo "Error: no .git found for util project!"
fi 
alias archive="uv --directory "$GIT_ROOT" run bin/archive" 
alias unarchive="uv --directory "$GIT_ROOT" run bin/unarchive" 
alias telegram-message="uv --directory "$GIT_ROOT" run bin/telegram-message" 
alias lint="uv --directory "$GIT_ROOT" run bin/lint"
