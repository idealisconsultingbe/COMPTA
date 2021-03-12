#!/bin/bash

if [ -z "$BASH_VERSION" ]; then
    echo -e "Error: BASH shell is required !"
    exit 1
fi

if [[ -z "$1" || "$1" == "--help" || "$1" == "-h" ]]; then
    echo
    echo "docker_build.sh - Build docker image"
    echo "(c) 2019 @Idealis Consulting - Yves HOYOS"

    echo "Usage:"
    echo "  ./docker_build.sh <template_name>     Store the image with given name. Format: <name>:<tag>."
    echo "                                        Example: idealis:11.0"
    echo "  ./docker_build.sh -h                  Prints this message."
    echo "  ./docker_build.sh --help              Prints this message."
    echo
    if [[ "$1" == "--help" || "$1" == "-h" ]]; then
        exit
    else
        exit 1
    fi
fi

echo "Run docker build: docker build --no-cache -t $1 --build-arg "'SSH_KEY="$(cat ~/.ssh/id_rsa)" .'
docker build --no-cache -t $1 --build-arg SSH_KEY="$(cat ~/.ssh/id_rsa)" .
