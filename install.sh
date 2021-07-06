#!/bin/bash
PYPI_INDEX=""
BUILDOUT_INDEX=""
HELP=0

#
# We need bash
#
if [ -z "$BASH_VERSION" ]; then
    echo -e "Error: BASH shell is required !"
    exit 1
fi

#
# Create buildout.cfg
#
function check_and_create_buildout_cfg {
    dbuser=$1
    if [[ -z $dbuser ]]; then
        dbuser="dbuser"
    fi
    dbpassword=$2
    if [[ -z $dbpassword ]]; then
        dbpassword="dbpassword"
    fi
    # create a basic buildout.cfg if none is found
    if [ ! -f buildout.cfg ]; then
        if [ -f buildout.cfg.example ]; then
            cp buildout.cfg.example buildout.cfg
        else
            cat >> buildout.cfg <<EOT
[buildout]
extends = buildout.cfg.template

[odoo]
options.admin_passwd = admin
options.db_user = $dbuser
options.db_password = $dbpassword
options.db_host = 127.0.0.1
options.pg_path = /usr/bin
options.limit_memory_hard = 5368709120
options.limit_memory_soft = 4294967296
options.limit_time_cpu = 300
options.limit_time_real = 600
options.workers = 2
options.proxy_mode = True
EOT
        fi
    fi
}

#
# install_odoo
#
function install_odoo {
    # create a basic buildout.cfg if none is found
    check_and_create_buildout_cfg

    osname=`awk -F= '/^NAME/{print $2}' /etc/os-release`
    if [[ $osname == *"CentOS"* ]]; then
        if [ -f /usr/bin/virtualenv-3.7 ]; then
            virtualenv-3.7 -p python37 venv
        else
            virtualenv-3.6 -p python36 venv
        fi
    else
        if [ -f /usr/bin/python3.9 ]; then
            virtualenv -p python3.9 venv
        elif [ -f /usr/bin/python3.8 ]; then
            virtualenv -p python3.8 venv
        elif [ -f /usr/bin/python3.7 ]; then
            virtualenv -p python3.7 venv
        elif [ -f /usr/bin/python3.6 ]; then
            virtualenv -p python3.6 venv
        else
            virtualenv -p python3 venv
        fi
    fi
    venv/bin/pip3 install zc.buildout
    venv/bin/buildout

    # if [ -f parts/odoo/requirements.txt ]; then
    #     echo "Installing PIP requirements"
    #     venv/bin/pip3 install -r parts/odoo/requirements.txt
    # fi
    echo "Installing PIP requirements"
    find parts/ -name requirements.txt -exec venv/bin/pip3 install --quiet --no-cache-dir --requirement {} \;

    if [ -f bin/start_odoo ]; then
        echo
        echo "Your commands are now available in ./bin"
        echo "Python is in ./venv. Don't forget to launch 'source venv/bin/activate'."
        echo
    else
        echo
        echo "ODOO INSTALLATION FAILED !!!"
        echo
    fi
}

function remove_buildout_files {
    echo "Removing all buidout generated items..."
    echo "    Not removing downloads/ and eggs/ for performance reason."
    rm -rf .installed.cfg
    rm -rf bin/
    rm -rf develop-eggs/
    rm -rf develop-src/
    rm -rf etc/
    rm -rf venv/
    echo "    Done."
}

#
# Process command line options
#
while getopts "i:h" opt; do
    case $opt in
        i)
            PYPI_INDEX="-i ${OPTARG}"
            BUILDOUT_INDEX="index = ${OPTARG}"
            ;;
        h)
            HELP=1
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
            ;;
        :)
            echo "Option -$OPTARG requires an argument." >&2
            exit 1
            ;;
    esac
done

COMMAND=${@:$OPTIND:1}

echo
echo "install.sh - Odoo Installer"
echo "(c) 2019 @IdealisConsulting - Yves HOYOS"

if [[ $COMMAND == "help"  ||  $HELP == 1 ]]; then
    echo "Available commands:"
    echo "  ./install.sh help           Prints this message."
    echo "  ./install.sh [-i ...] odoo  Install Odoo using buildout (prerequisites must be installed)."
    echo "  ./install.sh reset          Remove all buildout installed files."
    echo
    echo "Available options:"
    echo "  -i   Pypi Index to use (default=""). See pip install --help"
    echo "  -h   Prints this message"
    echo
    exit
fi

if [[ $COMMAND == "reset" ]]; then
    remove_buildout_files
    exit
elif [[ $COMMAND == "odoo" ]]; then
    install_odoo
    exit
fi

echo "use ./install.sh -h for usage instructions."
