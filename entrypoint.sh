#!/bin/bash

set -e;

: ${ODOO_FOLDER:='/opt/odoo'}
: ${ODOO_CONFIG_FILE:="${ODOO_FOLDER}/etc/odoo.cfg"}
: ${MASTER_PASSWORD:=${ODOO_MASTER_PASSWORD:=${CONFIG_MASTER_PASSWORD:='admin'}}}
: ${DB_HOST:=${ODOO_DB_HOST:=${POSTGRES_HOST:='db'}}}
: ${DB_PORT:=${ODOO_DB_PORT:=${POSTGRES_PORT:='5432'}}}
: ${DB_USER:=${ODOO_DB_USER:=${POSTGRES_USER:='odoo'}}}
: ${DB_PASSWORD:=${ODOO_DB_PASSWORD:=${POSTGRES_PASSWORD:='odoo'}}}
: ${DB_DATABASE:=${ODOO_DB_DATABASE:=${POSTGRES_DATABASE:=''}}}
: ${DB_SSL_MODE:=${ODOO_DB_SSL_MODE:=${POSTGRES_SSL_MODE:='prefer'}}}
: ${CONF_WORKERS:=${ODOO_CONF_WORKERS:=${CONFIG_WORKERS:=''}}}
: ${CONF_MEM_HARD:=${ODOO_CONF_MEM_HARD:=${CONFIG_MEM_HARD:=''}}}
: ${CONF_MEM_SOFT:=${ODOO_CONF_MEM_SOFT:=${CONFIG_MEM_SOFT:=''}}}
: ${CONF_TIME_CPU:=${ODOO_CONF_TIME_CPU:=${CONFIG_TIME_CPU:=''}}}
: ${CONF_TIME_REAL:=${ODOO_CONF_TIME_REAL:=${CONFIG_TIME_REAL:=''}}}
: ${CONF_SERVER_WIDE_MODULES:=${ODOO_CONF_SERVER_WIDE_MODULES:=${CONFIG_SERVER_WIDE_MODULES:=''}}}
: ${CONF_QUEUE_CHANNELS:=${ODOO_CONF_CHANNELS:=${CONFIG_CHANNELS:=''}}}
: ${ARGS_DEMO_DATA:=${ODOO_ENV_DEMO_DATA:=${ODOO_DEMO_DATA:=''}}}
: ${ARGS_INSTALL:=${ODOO_ENV_INSTALL:=${ODOO_INSTALL:='0'}}}
: ${ARGS_UPDATE:=${ODOO_ENV_UPDATE:=${ODOO_UPDATE:=''}}}
: ${ARGS_EXTRA_ARGS:=${ODOO_ENV_EXTRA_ARGS:=${ODOO_EXTRA_ARGS:=''}}}

function update_config_file() {
    key="$1"
    value="$2"
    if [ ! -z "$value" ]; then
        if grep -q "${key}" ${ODOO_CONFIG_FILE}; then
            sed -i -e "s/^${key} =[^\n]*$/${key} = ${value}/" ${ODOO_CONFIG_FILE}
        else
            if grep -q "\[queue_job\]" ${ODOO_CONFIG_FILE}; then
                if [ "$key" = 'channels' ]; then
                    sed -i -e "s/^\[queue_job\]$/[queue_job]\n${key} = ${value}/" ${ODOO_CONFIG_FILE}
                else
                    sed -i -e "s/^\[queue_job\]$/${key} = ${value}\n\n[queue_job]/" ${ODOO_CONFIG_FILE}
                fi;
            else
                if [ "$key" = 'channels' ]; then
                    echo '[queue_job]' >> ${ODOO_CONFIG_FILE}
                    echo "${key} = ${value}" >> ${ODOO_CONFIG_FILE}
                else
                    echo "${key} = ${value}" >> ${ODOO_CONFIG_FILE}
                fi;
            fi;
        fi;
    fi;
}

function update_buildout() {
    update_config_file "admin_passwd" "${MASTER_PASSWORD}"
    update_config_file "db_host" "${DB_HOST}"
    update_config_file "db_port" "${DB_PORT}"
    update_config_file "db_user" "${DB_USER}"
    update_config_file "db_password" "${DB_PASSWORD}"
    update_config_file "db_sslmode" "${DB_SSL_MODE}"
    update_config_file "db_name" "${DB_DATABASE}"
    update_config_file "dbfilter" "${DB_DATABASE}"
    update_config_file "workers" "${CONF_WORKERS}"
    update_config_file "limit_memory_hard" "${CONF_MEM_HARD}"
    update_config_file "limit_memory_soft" "${CONF_MEM_SOFT}"
    update_config_file "limit_time_cpu" "${CONF_TIME_CPU}"
    update_config_file "limit_time_real" "${CONF_TIME_REAL}"
    update_config_file "server_wide_modules" "${CONF_SERVER_WIDE_MODULES}"
    update_config_file "channels" "${CONF_QUEUE_CHANNELS}"
}

cd ${ODOO_FOLDER};

echo "Updating config file (${ODOO_CONFIG_FILE})...";
update_buildout

ODOO_ARGS=()
if [ ! -z "${DB_DATABASE}" ]; then
    ODOO_ARGS+=("--database=${DB_DATABASE}")
fi
if [ -z "${ARGS_DEMO_DATA}" ] || [ "${ARGS_DEMO_DATA}" != "1" ]; then
    ODOO_ARGS+=("--without-demo=all")
fi
if [ -z "${ARGS_INSTALL}" ] && [ "${ARGS_INSTALL}" == "1" ]; then
    ODOO_ARGS+=("--init=base")
fi
if [ ! -z "${ARGS_EXTRA_ARGS}" ]; then
    ODOO_ARGS+=("${ARGS_EXTRA_ARGS}")
fi
if [ ! -z "${ARGS_UPDATE}" ]; then
    ODOO_ARGS+=("--update=${ARGS_UPDATE}")
fi

echo "Running Odoo, with command: bin/start_odoo ${ODOO_ARGS[@]}";

bin/start_odoo "${ODOO_ARGS[@]}"
exit $?
