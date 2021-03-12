FROM registry.myidealis.be/docker/ubuntu-odoo:14.0 AS sources
# Arguments
ARG SSH_KEY
ARG SSH_KEY_PASSPHRASE
# Path
ENV ODOO_BASE_PATH       /opt/odoo
# Change user and workspace
USER odoo
WORKDIR ${ODOO_BASE_PATH}
# Copy project sources and buildout files
COPY --chown=odoo:odoo project_addons           "${ODOO_BASE_PATH}/project_addons"
COPY --chown=odoo:odoo scripts                  "${ODOO_BASE_PATH}/scripts"
COPY --chown=odoo:odoo buildout.cfg.example     "${ODOO_BASE_PATH}/buildout.cfg.example"
COPY --chown=odoo:odoo buildout.cfg.template    "${ODOO_BASE_PATH}/buildout.cfg.template"
COPY --chown=odoo:odoo bootstrap.py             "${ODOO_BASE_PATH}/bootstrap.py"
COPY --chown=odoo:odoo install.sh               "${ODOO_BASE_PATH}/install.sh"
COPY --chown=odoo:odoo entrypoint.sh            "${ODOO_BASE_PATH}/entrypoint.sh"
COPY --chown=odoo:odoo requirements.txt         "${ODOO_BASE_PATH}/requirements.txt"
# Prepare SSH, then change lang to UTF8, then install Odoo, and finally, remove ssh keys
RUN mkdir -p $HOME/.ssh && \
    chmod 0700 $HOME/.ssh && \
    echo "${SSH_KEY}" > $HOME/.ssh/id_rsa && \
    chmod 600 $HOME/.ssh/id_rsa && \
    eval "$(ssh-agent -s)" && \
    printf "${SSH_KEY_PASSPHRASE}\n" | ssh-add $HOME/.ssh/id_rsa && \
    ssh-keyscan -t rsa git.myidealis.be >> $HOME/.ssh/known_hosts && \
    ssh-keyscan -t rsa github.com >> $HOME/.ssh/known_hosts && \
    echo "Host git@git.myidealis.be\n\tStrictHostKeyChecking no\n" >> $HOME/.ssh/config && \
    echo "Host git@github.com\n\tStrictHostKeyChecking no\n" >> $HOME/.ssh/config && \
    export LANG="en_US.utf8" && \
    export LANGUAGE="en_US.utf8" && \
    export LC_ALL="en_US.utf8" && \
    ./install.sh odoo && \
    rm -rf $HOME/.ssh/ && \
    find ${ODOO_BASE_PATH}/ -name ".git*" | xargs rm -rf
# Check if file bin/start_odoo exists, or raise an error when build docker image
RUN stat ${ODOO_BASE_PATH}/bin/start_odoo


FROM registry.myidealis.be/docker/ubuntu-odoo:14.0
# Path
ENV ODOO_BASE_PATH       /opt/odoo
# Change user and workspace
USER odoo
WORKDIR ${ODOO_BASE_PATH}
# Copy project sources and buildout files
COPY --from=sources --chown=odoo:odoo "${ODOO_BASE_PATH}/" "${ODOO_BASE_PATH}/"
# Install project requirements (with pip) from requirements.txt files
RUN find ${ODOO_BASE_PATH}/ -name requirements.txt -exec venv/bin/pip3 install --quiet --no-cache-dir --requirement {} \;
# Check if file bin/start_odoo exists, or raise an error when build docker image
RUN stat ${ODOO_BASE_PATH}/bin/start_odoo
# Export ports and run entrypoint
EXPOSE 8069 8072
CMD ["./entrypoint.sh"]
